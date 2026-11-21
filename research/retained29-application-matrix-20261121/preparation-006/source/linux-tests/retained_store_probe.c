/* Check the optional CPU-global retained full64B store ABI, not performance.
 * Submission and bounded status polling are separate, visible operations.
 * Busy covers UCE/client/backend ownership, not lower-L2/AXI/DRAM drain.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#if !defined(BP_RETAINED_PROBE_HOST_VERIFY) && (!defined(__riscv) || __riscv_xlen != 64)
#error "This probe requires RV64 Linux"
#endif
#ifdef BP_RETAINED_PROBE_HOST_VERIFY
#define LABEL(name) "RETAINED_STORE_PROBE_HOST_VERIFY_" name
#else
#define LABEL(name) "RETAINED_STORE_PROBE_" name
#endif

#define PR_BP_RETAINED_CONTROL 0x42505063
#define PR_BP_RETAINED_STATUS 0x42505064
#define SENTINEL UINT64_C(0x0123456789abcdef)
#define CAPABILITY (UINT64_C(1) << 63)
#define FULL64 (UINT64_C(1) << 56)
#define SET_KILL (UINT64_C(1) << 57)
#define GEOMETRY_MASK UINT64_C(0x03ffffffffff0000)
#define ALLOWED_MASK (CAPABILITY | GEOMETRY_MASK | UINT64_C(0x0f0f))
#define BUSY_MASK UINT64_C(0x0300)
#define POLL_LIMIT 4096U

static pid_t owner;
static unsigned cleanup_armed;
static uint64_t geometry;

static void die(const char *step)
{
	fprintf(stderr, LABEL("FAIL") " step=%s errno=%d (%s)\n", step, errno, strerror(errno));
	exit(1);
}

static int control(unsigned long mode)
{
	return prctl(PR_BP_RETAINED_CONTROL, mode, 0UL, 0UL, 0UL);
}

static int status_read(uint64_t *value)
{
	return prctl(PR_BP_RETAINED_STATUS, (unsigned long)value, 0UL, 0UL, 0UL);
}

static int valid_status(uint64_t raw)
{
	return (raw & (CAPABILITY | FULL64 | SET_KILL)) == (CAPABILITY | FULL64 | SET_KILL)
		&& !(raw & ~ALLOWED_MASK) && (raw & GEOMETRY_MASK) == geometry;
}

static unsigned effective_mode(unsigned mode)
{
	if (!((geometry >> 16) & 0xffff))
		mode &= ~9U;
	if (!((geometry >> 32) & 0xffff))
		mode &= ~6U;
	if (!(mode & 1))
		mode &= ~8U;
	if (!(mode & 2))
		mode &= ~4U;
	return mode;
}

/* No unbounded waits: a busy or wrong readback fails this functional probe.
 * The kernel does not poll. A later benchmark must price both calls itself.
 */
static int poll_mode(unsigned requested, uint64_t *result)
{
	unsigned n;
	for (n = 0; n < POLL_LIMIT; ++n) {
		uint64_t raw = SENTINEL;
		if (status_read(&raw))
			return -1;
		if (!valid_status(raw)) {
			errno = EPROTO;
			return -1;
		}
		if ((raw & 15) == effective_mode(requested) && !(raw & BUSY_MASK)) {
			*result = raw;
			return 0;
		}
	}
	errno = ETIMEDOUT;
	return -1;
}

static void cleanup(void)
{
	uint64_t raw;
	if (getpid() == owner && cleanup_armed && (control(0) || poll_mode(0, &raw))) {
		fprintf(stderr, LABEL("FAIL") " step=cleanup/reset errno=%d\n", errno);
		_Exit(1);
	}
}

static void expect_error(const char *step, int option, unsigned long a2,
			 unsigned long a3, unsigned long a4, unsigned long a5, int expected)
{
	int result;
	errno = 0;
	result = prctl(option, a2, a3, a4, a5);
	if (result != -1 || errno != expected) {
		fprintf(stderr, LABEL("FAIL") " step=%s result=%d errno=%d expected=%d\n",
			step, result, errno, expected);
		exit(1);
	}
}

static void validate_arguments(void)
{
	uint64_t raw = SENTINEL;
	unsigned slot;
	expect_error("mask sixteen", PR_BP_RETAINED_CONTROL, 16, 0, 0, 0, EINVAL);
	expect_error("mask high bits", PR_BP_RETAINED_CONTROL, ULONG_MAX, 0, 0, 0, EINVAL);
	expect_error("null status", PR_BP_RETAINED_STATUS, 0, 0, 0, 0, EINVAL);
	for (slot = 0; slot < 3; ++slot) {
		unsigned long args[3] = {0, 0, 0};
		args[slot] = 1;
		expect_error("extra control argument", PR_BP_RETAINED_CONTROL,
			     0, args[0], args[1], args[2], EINVAL);
		expect_error("extra status argument", PR_BP_RETAINED_STATUS,
			     (unsigned long)&raw, args[0], args[1], args[2], EINVAL);
		if (raw != SENTINEL) {
			errno = EIO;
			die("invalid status modified output");
		}
	}
}

static void absent_status(void)
{
	uint64_t raw = SENTINEL;
	expect_error("absent status", PR_BP_RETAINED_STATUS, (unsigned long)&raw, 0, 0, 0, ENODEV);
	if (raw != SENTINEL) {
		errno = EIO;
		die("absent status modified output");
	}
}

static void unprivileged_child(void)
{
	uint64_t raw = SENTINEL;
	unsigned mode;
	if (setgid(65534) || setuid(65534))
		die("drop child credentials");
	if (geteuid() != 65534 || getegid() != 65534) {
		errno = EPERM;
		die("child credentials did not change");
	}
	for (mode = 0; mode < 16; ++mode)
		expect_error("unprivileged control", PR_BP_RETAINED_CONTROL, mode, 0, 0, 0, EPERM);
	expect_error("unprivileged status", PR_BP_RETAINED_STATUS, (unsigned long)&raw, 0, 0, 0, EPERM);
	if (raw != SENTINEL) {
		errno = EIO;
		die("unprivileged status modified output");
	}
	_exit(0);
}

int main(int argc, char **argv)
{
	unsigned present, mode;
	uint64_t raw = SENTINEL;
	pid_t child, waited;
	int child_status;
	if (argc != 2 || (strcmp(argv[1], "absent") && strcmp(argv[1], "present"))) {
		fprintf(stderr, "usage: %s absent|present\n", argv[0]);
		return 2;
	}
	if (geteuid() != 0) {
		errno = EPERM;
		die("root privileges required");
	}
	present = !strcmp(argv[1], "present");
	owner = getpid();
	if (atexit(cleanup))
		die("cleanup registration");
	validate_arguments();
	if (present) {
		/* Only the initial read establishes capability; no speculative write. */
		if (status_read(&raw))
			die("initial capability probe");
		geometry = raw & GEOMETRY_MASK;
		if (!valid_status(raw)) {
			errno = EPROTO;
			die("invalid capability/geometry descriptor");
		}
		cleanup_armed = 1;
		expect_error("bad status pointer", PR_BP_RETAINED_STATUS, 1, 0, 0, 0, EFAULT);
		for (mode = 0; mode < 16; ++mode) {
			if (control(mode) || poll_mode(mode, &raw))
				die("control/readback bounded poll");
		}
		if (control(15) || poll_mode(15, &raw))
			die("prepare parent controls");
	} else {
		for (mode = 0; mode < 16; ++mode)
			expect_error("absent control", PR_BP_RETAINED_CONTROL, mode, 0, 0, 0, ENODEV);
		absent_status();
		expect_error("absent bad pointer", PR_BP_RETAINED_STATUS, 1, 0, 0, 0, ENODEV);
	}
	child = fork();
	if (child < 0)
		die("fork privilege probe");
	if (!child)
		unprivileged_child();
	do { waited = waitpid(child, &child_status, 0); } while (waited < 0 && errno == EINTR);
	if (waited != child || !WIFEXITED(child_status) || WEXITSTATUS(child_status)) {
		errno = ECHILD;
		die("unprivileged child did not pass");
	}
	if (present) {
		if (poll_mode(15, &raw))
			die("failed child writes changed controls");
		if (control(0) || poll_mode(0, &raw))
			die("normal reset/readback bounded poll");
		cleanup_armed = 0;
		printf(LABEL("STATUS") " raw=0x%016" PRIx64
		       " i_lines=%u d_lines=%u set_log2=%u line_bytes=64 same_set_invalidation=1"
		       " busy_scope=uce_client_backend poll_limit=%u\n", raw,
		       (unsigned)((raw >> 16) & 0xffff), (unsigned)((raw >> 32) & 0xffff),
		       (unsigned)((raw >> 48) & 0xff), POLL_LIMIT);
	} else {
		absent_status();
	}
	printf(LABEL("PASS") " capability=%s\n", argv[1]);
	return 0;
}
