/* Validate the privileged retention prctl ABI on old or capable hardware.
 * This is a correctness/feature probe, with no address table or timing claim.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#if !defined(BP_RETENTION_PROBE_HOST_VERIFY) && (!defined(__riscv) || __riscv_xlen != 64)
#error "This probe requires RV64 Linux"
#endif
#ifdef BP_RETENTION_PROBE_HOST_VERIFY
#define LABEL(name) "ICACHE_RETENTION_PROBE_HOST_VERIFY_" name
#else
#define LABEL(name) "ICACHE_RETENTION_PROBE_" name
#endif

#define PR_BP_ICACHE_RETENTION_CONTROL 0x42505061
#define PR_BP_ICACHE_RETENTION_STATUS 0x42505062
#define SENTINEL UINT64_C(0x0123456789abcdef)

static pid_t owner;
static unsigned cleanup_armed;

static void die(const char *step)
{
	fprintf(stderr, LABEL("FAIL") " step=%s errno=%d (%s)\n", step, errno, strerror(errno));
	exit(1);
}

static int control(unsigned long mode)
{
	return prctl(PR_BP_ICACHE_RETENTION_CONTROL, mode, 0UL, 0UL, 0UL);
}

static int status_read(uint64_t *value)
{
	return prctl(PR_BP_ICACHE_RETENTION_STATUS, (unsigned long)value, 0UL, 0UL, 0UL);
}

static void cleanup(void)
{
	if (getpid() == owner && cleanup_armed && control(0)) {
		fprintf(stderr, LABEL("FAIL") " error cleanup/reset errno=%d\n", errno);
		_Exit(1);
	}
}

static void expect_error(const char *step, int option, unsigned long arg2,
			 unsigned long arg3, unsigned long arg4, unsigned long arg5,
			 int expected)
{
	int result;

	errno = 0;
	result = prctl(option, arg2, arg3, arg4, arg5);
	if (result != -1 || errno != expected) {
		fprintf(stderr, LABEL("FAIL") " step=%s result=%d errno=%d expected=%d\n",
			step, result, errno, expected);
		exit(1);
	}
}

static uint64_t expect_mode(unsigned mode)
{
	uint64_t status = SENTINEL;

	if (status_read(&status))
		die("capable status");
	if (!(status >> 63) || (status & 3) != mode) {
		fprintf(stderr, LABEL("FAIL") " mode readback raw=0x%016" PRIx64 " expected=%u\n",
			status, mode);
		exit(1);
	}
	return status;
}

static void validate_arguments(void)
{
	uint64_t status = SENTINEL;
	unsigned slot;

	expect_error("mode three", PR_BP_ICACHE_RETENTION_CONTROL, 3, 0, 0, 0, EINVAL);
	expect_error("null status", PR_BP_ICACHE_RETENTION_STATUS, 0, 0, 0, 0, EINVAL);
	for (slot = 0; slot < 3; ++slot) {
		unsigned long args[3] = { 0, 0, 0 };
		args[slot] = 1;
		expect_error("nonzero control argument", PR_BP_ICACHE_RETENTION_CONTROL,
			     0, args[0], args[1], args[2], EINVAL);
		expect_error("nonzero status argument", PR_BP_ICACHE_RETENTION_STATUS,
			     (unsigned long)&status, args[0], args[1], args[2], EINVAL);
		if (status != SENTINEL) {
			errno = EIO;
			die("invalid status modified output");
		}
	}
}

static void expect_absent_status(void)
{
	uint64_t status = SENTINEL;

	expect_error("absent status", PR_BP_ICACHE_RETENTION_STATUS,
		     (unsigned long)&status, 0, 0, 0, ENODEV);
	if (status != SENTINEL) {
		errno = EIO;
		die("absent status modified output");
	}
}

static void unprivileged_child(void)
{
	uint64_t status = SENTINEL;
	unsigned mode;

	if (setgid(65534) || setuid(65534))
		die("drop child credentials");
	if (geteuid() != 65534 || getegid() != 65534) {
		errno = EPERM;
		die("child credentials did not change");
	}
	for (mode = 0; mode <= 2; ++mode)
		expect_error("unprivileged control", PR_BP_ICACHE_RETENTION_CONTROL,
			     mode, 0, 0, 0, EPERM);
	expect_error("unprivileged status", PR_BP_ICACHE_RETENTION_STATUS,
		     (unsigned long)&status, 0, 0, 0, EPERM);
	if (status != SENTINEL) {
		errno = EIO;
		die("unprivileged status modified output");
	}
	_exit(0);
}

int main(int argc, char **argv)
{
	unsigned present, mode;
	pid_t child, waited;
	int status;

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
		uint64_t raw = SENTINEL;
		if (status_read(&raw))
			die("initial capability probe");
		if (!(raw >> 63)) {
			errno = ENODEV;
			die("capability bit absent");
		}
		cleanup_armed = 1;
		for (mode = 0; mode <= 2; ++mode) {
			if (control(mode))
				die("capable control");
			(void)expect_mode(mode);
		}
		/* Keep a nonzero parent policy while checking failed child writes.
		 * Publication/hit telemetry may change naturally during the fork;
		 * only the globally configured policy must remain unchanged.
		 */
		if (control(1))
			die("prepare parent policy");
		(void)expect_mode(1);
	} else {
		for (mode = 0; mode <= 2; ++mode)
			expect_error("absent control", PR_BP_ICACHE_RETENTION_CONTROL,
				     mode, 0, 0, 0, ENODEV);
		expect_absent_status();
	}
	child = fork();
	if (child < 0)
		die("fork privilege probe");
	if (!child)
		unprivileged_child();
	do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
	if (waited != child || !WIFEXITED(status) || WEXITSTATUS(status)) {
		errno = ECHILD;
		die("unprivileged child did not pass");
	}
	if (present) {
		(void)expect_mode(1);
		if (control(0))
			die("normal reset");
		(void)expect_mode(0);
		cleanup_armed = 0;
	} else {
		expect_absent_status();
	}
	printf(LABEL("PASS") " capability=%s\n", argv[1]);
	return 0;
}
