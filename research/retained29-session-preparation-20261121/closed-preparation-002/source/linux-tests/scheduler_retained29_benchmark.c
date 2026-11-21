/* SPDX-License-Identifier: GPL-2.0
 * Separate ABI29 matched-lifecycle experiment, not a legacy policy alias.
 * Work generators and the two-process pipe/futex protocol follow the maintained
 * scheduler_pipe_hint_benchmark; legacy sources and ELF flags remain untouched.
 * No advisory source is generated here. Ordinary-copy and advisory-only masks
 * are distinct; whole cells price control, polling and both process lifecycles.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <linux/futex.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include "resume_workload.h"

#if defined(BP_RESUME_ZLIB) && BP_RESUME_ZLIB
#error "The ABI29 natural-workload experiment does not include zlib"
#endif
#if !defined(BP_RETAINED29_HOST_VERIFY) && (!defined(__riscv) || __riscv_xlen != 64)
#error "This benchmark requires RV64 BlackParrot"
#endif
#ifdef BP_RETAINED29_HOST_VERIFY
#define LABEL(name) "RESUME_RETAINED29_HOST_VERIFY_" name
#else
#define LABEL(name) "RESUME_RETAINED29_" name
#endif
#define PR_BP_PREVIEW_ENABLE 0x4250505a
#define PR_BP_PREVIEW_ICACHE_STATUS 0x4250505e
#define PR_BP_PREVIEW_REPLAY_STATUS 0x4250505d
#define PR_BP_RETAINED_CONTROL 0x42505063
#define PR_BP_RETAINED_STATUS 0x42505064
#define POLL_LIMIT 4096U
#define GEOMETRY UINT64_C(0x03ffffffffff0000)
#define ALLOWED (GEOMETRY | (UINT64_C(1)<<63) | UINT64_C(0xf0f))
#define BUSY UINT64_C(0x300)
#define PREFIX_PENDING ((UINT64_C(1)<<54) | UINT64_C(14))
#define PREFIX_COUNTERS ((UINT64_C(0xffff)<<22) | (UINT64_C(0xff)<<38) | \
                         (UINT64_C(0xff)<<46) | (UINT64_C(0x1ff)<<55))
#define REPLAY_PENDING UINT64_C(0xf00000000000000f)
#define REPLAY_COUNTERS UINT64_C(0x03fffffffffffc00)

static pid_t owner, active_child;
static unsigned armed;
static uint64_t geometry;

static void fail(const char *message) { perror(message); exit(1); }

struct cell_resources {
	struct rusage self, children;
};

struct cell_resource_delta {
	uint64_t minor_faults, major_faults, user_us, system_us;
	uint64_t voluntary_switches, involuntary_switches;
};

static void resource_invalid(void)
{
	errno = EOVERFLOW;
	fail("cell resource accounting");
}

static uint64_t resource_sum(uint64_t a, uint64_t b)
{
	if (a > UINT64_MAX - b)
		resource_invalid();
	return a + b;
}

static uint64_t resource_counter_delta(long after, long before)
{
	if (before < 0 || after < before)
		resource_invalid();
	return (uint64_t)after - (uint64_t)before;
}

static uint64_t resource_time_delta(struct timeval after, struct timeval before)
{
	uint64_t seconds, microseconds;

	if (before.tv_sec < 0 || after.tv_sec < before.tv_sec
	    || before.tv_usec < 0 || before.tv_usec >= 1000000
	    || after.tv_usec < 0 || after.tv_usec >= 1000000)
		resource_invalid();
	seconds = (uint64_t)after.tv_sec - (uint64_t)before.tv_sec;
	if (after.tv_usec < before.tv_usec) {
		if (!seconds)
			resource_invalid();
		--seconds;
		microseconds = 1000000 + after.tv_usec - before.tv_usec;
	} else {
		microseconds = after.tv_usec - before.tv_usec;
	}
	if (seconds > (UINT64_MAX - microseconds) / 1000000)
		resource_invalid();
	return seconds * 1000000 + microseconds;
}

static struct cell_resources resource_snapshot(void)
{
	struct cell_resources usage;

	if (getrusage(RUSAGE_SELF, &usage.self))
		fail("cell resource self");
	if (getrusage(RUSAGE_CHILDREN, &usage.children))
		fail("cell resource children");
	return usage;
}

static struct cell_resource_delta resource_delta(struct cell_resources after,
						 struct cell_resources before)
{
	/* Children are reaped before the ending snapshot. Subtract each
	 * cumulative total before combining, so earlier cells are excluded.
	 */
	return (struct cell_resource_delta){
		.minor_faults = resource_sum(
			resource_counter_delta(after.self.ru_minflt, before.self.ru_minflt),
			resource_counter_delta(after.children.ru_minflt, before.children.ru_minflt)),
		.major_faults = resource_sum(
			resource_counter_delta(after.self.ru_majflt, before.self.ru_majflt),
			resource_counter_delta(after.children.ru_majflt, before.children.ru_majflt)),
		.user_us = resource_sum(
			resource_time_delta(after.self.ru_utime, before.self.ru_utime),
			resource_time_delta(after.children.ru_utime, before.children.ru_utime)),
		.system_us = resource_sum(
			resource_time_delta(after.self.ru_stime, before.self.ru_stime),
			resource_time_delta(after.children.ru_stime, before.children.ru_stime)),
		.voluntary_switches = resource_sum(
			resource_counter_delta(after.self.ru_nvcsw, before.self.ru_nvcsw),
			resource_counter_delta(after.children.ru_nvcsw, before.children.ru_nvcsw)),
		.involuntary_switches = resource_sum(
			resource_counter_delta(after.self.ru_nivcsw, before.self.ru_nivcsw),
			resource_counter_delta(after.children.ru_nivcsw, before.children.ru_nivcsw)),
	};
}

static uint64_t cycle(void)
{
#ifdef BP_RETAINED29_HOST_VERIFY
	struct timespec now;
	if (clock_gettime(CLOCK_MONOTONIC, &now)) fail("host verification clock");
	return (uint64_t)now.tv_sec * 1000000000 + now.tv_nsec;
#else
	uint64_t value;
	__asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
	return value;
#endif
}

static void flush_instruction_state(void)
{
#ifdef BP_RETAINED29_HOST_VERIFY
	atomic_thread_fence(memory_order_seq_cst);
#else
	__asm__ volatile("fence.i" : : : "memory");
#endif
}

static int read_control(uint64_t *raw)
{
	if (prctl(PR_BP_RETAINED_STATUS, (unsigned long)raw, 0UL, 0UL, 0UL)) return -1;
	if ((*raw & ((UINT64_C(1)<<63) | (UINT64_C(3)<<56)))
	    != ((UINT64_C(1)<<63) | (UINT64_C(3)<<56)) || (*raw & ~ALLOWED)
	    || (*raw & GEOMETRY) != geometry) { errno = EPROTO; return -1; }
	return 0;
}

static int poll_control(unsigned mask, uint64_t *raw)
{
	for (unsigned n = 0; n < POLL_LIMIT; ++n) {
		if (read_control(raw)) return -1;
		if ((*raw & 15) == mask && !(*raw & BUSY)) return 0;
	}
	errno = ETIMEDOUT;
	return -1;
}

static int submit(unsigned mask)
{
	return prctl(PR_BP_RETAINED_CONTROL, (unsigned long)mask, 0UL, 0UL, 0UL);
}

static int source_off(void)
{
	return prctl(PR_BP_PREVIEW_ENABLE, 0UL, 0UL, 0UL, 0UL);
}

static int prefix_idle(uint64_t *raw)
{
	for (unsigned n = 0; n < POLL_LIMIT; ++n) {
		if (prctl(PR_BP_PREVIEW_ICACHE_STATUS, (unsigned long)raw, 0UL, 0UL, 0UL)) return -1;
		if (!(*raw & PREFIX_PENDING)) return 0;
	}
	errno = ETIMEDOUT;
	return -1;
}

static int replay_idle(uint64_t *raw)
{
	for (unsigned n = 0; n < POLL_LIMIT; ++n) {
		/* prctl() returns int and truncates this legacy status. The raw
		 * syscall preserves all64bits, including completed-reply bit63.
		 * A negative signed status alone is therefore not a syscall error.
		 */
		errno = 0;
#ifdef BP_RETAINED29_HOST_VERIFY
		extern long bp_retained29_host_replay_status(void);
		long status = bp_retained29_host_replay_status();
#else
		long status = syscall(SYS_prctl, PR_BP_PREVIEW_REPLAY_STATUS, 0UL, 0UL, 0UL, 0UL);
#endif
		if (status == -1 && errno) return -1;
		*raw = (uint64_t)status;
		if (!(*raw & REPLAY_PENDING)) return 0;
	}
	errno = ETIMEDOUT;
	return -1;
}

static void cleanup_error(int result, int *saved)
{
	if (result && !*saved) *saved = errno ? errno : EIO;
}

static void cleanup(void)
{
	uint64_t raw, replay;
	int status;
	pid_t waited;
	if (getpid() != owner) return;
	if (active_child > 0) {
		do { waited = waitpid(active_child, &status, WNOHANG); } while (waited < 0 && errno == EINTR);
		if (!waited) {
			(void)kill(active_child, SIGKILL);
			while (waitpid(active_child, &status, 0) < 0 && errno == EINTR) { }
		}
		active_child = 0;
	}
	if (armed) {
		int saved = 0;
		/* An auxiliary-source failure must not skip global reset. Attempt
		 * every bounded cleanup independently and retain the first error.
		 */
		cleanup_error(source_off(), &saved);
		cleanup_error(submit(0), &saved);
		cleanup_error(replay_idle(&replay), &saved);
		cleanup_error(prefix_idle(&raw), &saved);
		cleanup_error(poll_control(0, &raw), &saved);
		if (saved) {
			errno = saved;
			perror("retained29 cleanup/reset");
			_Exit(1);
		}
	}
}

static unsigned parse_number(const char *text, const char *label, unsigned minimum, unsigned maximum)
{
	char *end;
	errno = 0;
	unsigned long value = strtoul(text, &end, 0);
	if (errno || text == end || *end || *text == '-' || value < minimum || value > maximum) {
		fprintf(stderr, "%s must be in %u..%u\n", label, minimum, maximum);
		exit(2);
	}
	return (unsigned)value;
}

static unsigned policy_mask(const char *text)
{
	static const char *const names[] = {"ordinary-i", "ordinary-d", "ordinary-joint",
		"advisory-i", "advisory-d", "advisory-joint"};
	static const unsigned masks[] = {9, 6, 15, 1, 2, 3};
	for (unsigned n = 0; n < 6; ++n) if (!strcmp(text, names[n])) return masks[n];
	fputs("policy must be ordinary-i/d/joint or advisory-i/d/joint; legacy aliases are invalid\n", stderr);
	exit(2);
}

static void check_prefix_start(uint64_t raw)
{
	/* Saturated counters cannot establish a zero-new-advisory interval. */
	if (((raw >> 22) & 0xffff) == 0xffff || ((raw >> 38) & 0xff) == 0xff
	    || ((raw >> 46) & 0xff) == 0xff || ((raw >> 55) & 0x1ff) == 0x1ff) {
		errno = EOVERFLOW; fail("retained29 saturated prefix telemetry");
	}
}

static void check_replay_start(uint64_t raw)
{
	if (((raw >> 10) & 0xffff) == 0xffff || ((raw >> 26) & 0xffff) == 0xffff
	    || ((raw >> 42) & 0xff) == 0xff || ((raw >> 50) & 0xff) == 0xff) {
		errno = EOVERFLOW; fail("retained29 saturated data-replay telemetry");
	}
}

static void transfer(int fd, unsigned char *token, int writing)
{
	ssize_t result;
	do { result = writing ? write(fd, token, 1) : read(fd, token, 1); } while (result < 0 && errno == EINTR);
	if (result != 1) fail(writing ? "pipe write" : "pipe read");
}

struct shared {
	_Atomic uint32_t turn;
	uint32_t padding;
	volatile uint64_t parent_launch, child_launch, child_resume;
};
struct transport { int pipe_mode; int ready[2], to_child[2], to_parent[2]; struct shared *shared; };

static void wait_turn(struct transport *t, unsigned wanted)
{
	unsigned char token;
	if (t->pipe_mode) { transfer(wanted == 0 ? t->to_parent[0] : t->to_child[0], &token, 0); return; }
	for (;;) {
		uint32_t observed = atomic_load_explicit(&t->shared->turn, memory_order_acquire);
		if (observed == wanted) return;
		if (syscall(SYS_futex, (uint32_t *)&t->shared->turn, FUTEX_WAIT, observed, NULL, NULL, 0)
		    && errno != EAGAIN && errno != EINTR) fail("futex wait");
	}
}

static void send_turn(struct transport *t, unsigned value)
{
	unsigned char token = 0;
	if (t->pipe_mode) { transfer(value == 0 ? t->to_parent[1] : t->to_child[1], &token, 1); return; }
	atomic_store_explicit(&t->shared->turn, value, memory_order_release);
	if (syscall(SYS_futex, (uint32_t *)&t->shared->turn, FUTEX_WAKE, 1, NULL, NULL, 0) < 0) fail("futex wake");
}

static struct resume_workload allocate_work(unsigned kib, unsigned salt, const char *kind)
{
	struct resume_workload work;
	if (resume_workload_init(&work, kind, kib, salt)) fail("working-set allocation");
	return work;
}

static void check_free(struct resume_workload *work, uint64_t sum)
{
	if (!resume_workload_check_total(work, sum)) { errno = EIO; fail("working-set checksum"); }
	resume_workload_free(work);
}

struct result { uint64_t steady, child_resume, parent_resume; };

static struct result run_cell(unsigned loops, unsigned warmup, unsigned kib,
			      const char *kind, int pipe_mode, int legs)
{
	struct transport t = {.pipe_mode = pipe_mode};
	struct result result = {0};
	uint64_t checksum = 0, begin = 0;
	unsigned char token;
	int status;
	pid_t waited;
	if (pipe(t.ready)) fail("ready pipe");
	if (pipe_mode) {
		if (pipe(t.to_child) || pipe(t.to_parent)) fail("data pipe");
	} else {
		t.shared = mmap(NULL, sizeof(*t.shared), PROT_READ | PROT_WRITE,
				MAP_SHARED | MAP_ANONYMOUS, -1, 0);
		if (t.shared == MAP_FAILED) fail("futex mmap");
		atomic_init(&t.shared->turn, 0);
	}
	pid_t child = fork();
	if (child < 0) fail("fork");
	if (child) active_child = child;
	if (!child) {
		if (source_off()) fail("child preview disable");
		struct resume_workload work = allocate_work(kib, pipe_mode ? 0x5a : 0x3c, kind);
		close(t.ready[0]);
		if (pipe_mode) { close(t.to_child[1]); close(t.to_parent[0]); }
		flush_instruction_state();
		transfer(t.ready[1], &token, 1);
		uint64_t child_resume = 0;
		for (unsigned n = 0; n < warmup + loops; ++n) {
			wait_turn(&t, 1);
			if (legs && n >= warmup) child_resume += cycle() - t.shared->parent_launch;
			checksum += resume_workload_run(&work);
			if (legs && n >= warmup) t.shared->child_launch = cycle();
			send_turn(&t, 0);
		}
		if (!pipe_mode) t.shared->child_resume = child_resume;
		wait_turn(&t, 2); /* Parent samples steady end before releasing checks. */
		check_free(&work, checksum);
		if (source_off()) fail("child ending preview disable");
		_exit(0);
	}
	struct resume_workload work = allocate_work(kib, pipe_mode ? 0xa5 : 0xc3, kind);
	close(t.ready[1]);
	if (pipe_mode) { close(t.to_child[0]); close(t.to_parent[1]); }
	transfer(t.ready[0], &token, 0);
	flush_instruction_state();
	for (unsigned n = 0; n < warmup + loops; ++n) {
		if (n == warmup) begin = cycle();
		if (legs && n >= warmup) t.shared->parent_launch = cycle();
		send_turn(&t, 1);
		wait_turn(&t, 0);
		if (legs && n >= warmup) result.parent_resume += cycle() - t.shared->child_launch;
		checksum += resume_workload_run(&work);
	}
	result.steady = cycle() - begin;
	send_turn(&t, 2);
	do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
	if (waited != child || !WIFEXITED(status) || WEXITSTATUS(status)) { errno = ECHILD; fail("child failed"); }
	active_child = 0;
	close(t.ready[0]);
	if (pipe_mode) { close(t.to_child[1]); close(t.to_parent[0]); }
	else {
		result.child_resume = t.shared->child_resume;
		if (munmap(t.shared, sizeof(*t.shared))) fail("futex munmap");
	}
	check_free(&work, checksum);
	return result;
}

int main(int argc, char **argv)
{
	unsigned loops = 512, repeats = 8, warmup = 32, kib = 32;
	const char *policy = "ordinary-joint", *kind = "scan", *sync = "futex", *profile = "plain";
	if (argc > 10) {
		fprintf(stderr, "usage: %s [loops] [repeats] [ordinary-i|ordinary-d|ordinary-joint|advisory-i|advisory-d|advisory-joint] [warmup] [pipe|futex] [plain|legs] [corpus-kib] [scan|lookup|parse|chase] [none]\n", argv[0]);
		return 2;
	}
	if (argc > 1) loops = parse_number(argv[1], "loops", 1, 1000000);
	if (argc > 2) repeats = parse_number(argv[2], "repeats", 1, 1000000);
	if (argc > 3) policy = argv[3];
	if (argc > 4) warmup = parse_number(argv[4], "warmup", 1, 1000000);
	if (argc > 5) sync = argv[5];
	if (argc > 6) profile = argv[6];
	if (argc > 7) kib = parse_number(argv[7], "corpus-kib", 0, 65536);
	if (argc > 8) kind = argv[8];
	unsigned mask = policy_mask(policy);
	int pipe_mode = !strcmp(sync, "pipe"), legs = !strcmp(profile, "legs");
	if ((strcmp(sync, "pipe") && strcmp(sync, "futex"))
	    || (strcmp(profile, "plain") && strcmp(profile, "legs")) || (pipe_mode && legs)
	    || (strcmp(kind, "scan") && strcmp(kind, "lookup") && strcmp(kind, "parse") && strcmp(kind, "chase"))
	    || (argc > 9 && strcmp(argv[9], "none"))) {
		fputs("invalid synchronization/profile/workload/advisory source (only none is supported)\n", stderr);
		return 2;
	}
	owner = getpid();
	if (atexit(cleanup)) fail("cleanup registration");
	if (source_off()) fail("initial inherited preview disable");
	uint64_t raw = 0, prefix, replay;
	if (prctl(PR_BP_RETAINED_STATUS, (unsigned long)&raw, 0UL, 0UL, 0UL)) fail("initial ABI29 capability");
	geometry = raw & GEOMETRY;
	if (read_control(&raw)) fail("ABI29 capability/geometry descriptor");
	if ((raw & 15) != 0) { errno = EBUSY; fail("fresh global mode0 entry required"); }
	if (((mask & 1) && !((geometry >> 16) & 0xffff)) || ((mask & 2) && !((geometry >> 32) & 0xffff))) {
		errno = ENODEV; fail("requested retained lane has no configured payload slots");
	}
	armed = 1;
	if (replay_idle(&replay) || prefix_idle(&prefix) || poll_control(0, &raw)) fail("initial bounded mode0/source idle");
	check_prefix_start(prefix);
	check_replay_start(replay);
#ifdef BP_RETAINED29_HOST_VERIFY
	fputs("Software protocol verification only; host nanoseconds are not FPGA cycles.\n", stderr);
#endif
	printf(LABEL("CONFIG") " loops=%u repeats=%u warmup=%u policy=%s enabled_mask=%u sync=%s profile=%s corpus_kib=%u workload=%s advisory_source=none task_preview_mode=0 i_lines=%u d_lines=%u set_log2=%u line_bytes=64 same_set_invalidation=1 poll_limit=%u\n",
	       loops, repeats, warmup, policy, mask, sync, profile, kib, kind,
	       (unsigned)((geometry >> 16) & 0xffff), (unsigned)((geometry >> 32) & 0xffff),
	       (unsigned)((geometry >> 48) & 255), POLL_LIMIT);
	puts(LABEL("SCOPE") " version=29 mode=cell activation=before-allocation cleanup=mode0 busy=uce_client_backend matched_lifecycle=1 advisory_source=none");
	for (unsigned repeat = 0; repeat < repeats; ++repeat) for (unsigned order = 0; order < 2; ++order) {
		unsigned enabled = (repeat & 1) ^ order, selected = enabled ? mask : 0;
		uint64_t whole_begin = cycle(), prefix_before, prefix_after, replay_before, replay_after, active, reset;
		struct cell_resources before = resource_snapshot();
		if (source_off() || replay_idle(&replay_before) || prefix_idle(&prefix_before)) fail("cell source disable/idle");
		check_prefix_start(prefix_before);
		check_replay_start(replay_before);
		if (poll_control(0, &raw)) fail("cell mode0 entry");
		if (submit(selected) || poll_control(selected, &raw)) fail("cell control/readback before allocation");
		struct result result = run_cell(loops, warmup, kib, kind, pipe_mode, legs);
		if (read_control(&active)) fail("cell ending status");
		if ((active & 15) != selected) { errno = EIO; fail("cell control changed"); }
		if (source_off() || submit(0) || replay_idle(&replay_after) || prefix_idle(&prefix_after) || poll_control(0, &reset)) fail("cell normal reset/idle");
		if ((prefix_before & PREFIX_COUNTERS) != (prefix_after & PREFIX_COUNTERS)
		    || (replay_before & REPLAY_COUNTERS) != (replay_after & REPLAY_COUNTERS)) {
			errno = EIO; fail("unexpected advisory prefix activity");
		}
		struct cell_resource_delta usage = resource_delta(resource_snapshot(), before);
		uint64_t whole = cycle() - whole_begin;
		printf(LABEL("RESULT") " repeat=%u order=%u enabled=%u cycles=%" PRIu64 " loops=%u\n", repeat, order, enabled, result.steady, loops);
		if (legs) printf(LABEL("LEGS") " repeat=%u order=%u enabled=%u child_resume=%" PRIu64 " parent_resume=%" PRIu64 " loops=%u\n", repeat, order, enabled, result.child_resume, result.parent_resume, loops);
		printf(LABEL("WHOLE") " repeat=%u order=%u enabled=%u cycles=%" PRIu64 " loops=%u\n", repeat, order, enabled, whole, loops);
		printf(LABEL("CONTROL") " repeat=%u order=%u enabled=%u requested=%u active_raw=0x%016" PRIx64 " reset_raw=0x%016" PRIx64 " busy_scope=uce_client_backend\n", repeat, order, enabled, selected, active, reset);
		printf(LABEL("RESOURCE") " repeat=%u order=%u enabled=%u minor_faults=%" PRIu64 " major_faults=%" PRIu64 " user_us=%" PRIu64 " system_us=%" PRIu64 " voluntary_switches=%" PRIu64 " involuntary_switches=%" PRIu64 "\n", repeat, order, enabled, usage.minor_faults, usage.major_faults, usage.user_us, usage.system_us, usage.voluntary_switches, usage.involuntary_switches);
		printf(LABEL("PREFIX") " repeat=%u order=%u enabled=%u before=0x%016" PRIx64 " after=0x%016" PRIx64 " new_activity=0 advisory_source=none\n", repeat, order, enabled, prefix_before, prefix_after);
		printf(LABEL("REPLAY") " repeat=%u order=%u enabled=%u before=0x%016" PRIx64 " after=0x%016" PRIx64 " new_activity=0 advisory_source=none\n", repeat, order, enabled, replay_before, replay_after);
		fflush(stdout);
	}
	armed = 0;
	puts(LABEL("PASS"));
	return 0;
}
