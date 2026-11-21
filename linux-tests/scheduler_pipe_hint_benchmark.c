#define _GNU_SOURCE

/* SPDX-License-Identifier: GPL-2.0
 *
 * Measure sustained two-process pipe or futex ping-pong with either continuous
 * or one-time-seed instruction-prefix hints. The pipe loop is derived from
 * Linux perf's tools/perf/bench/sched-pipe.c, which in turn is based on Ingo
 * Molnar's pipe-test-1m.c. Setup and fork are outside timing. Continuous/seed
 * policies execute matched prctls before wakes; continuous-unmatched omits
 * the disabled-arm syscall to model deployment; preseed executes one matched
 * setup call after both fences and no hint syscall in either measured loop.
 */
#include <errno.h>
#include <linux/futex.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>
#include <time.h>
#include "resume_workload.h"
#if defined(BP_RESUME_RESOURCE_STATS) && BP_RESUME_RESOURCE_STATS
#include <sys/resource.h>
#endif
#if defined(BP_RESUME_COMPLETE_POLICY_SCOPE) && BP_RESUME_COMPLETE_POLICY_SCOPE
#if !defined(BP_RESUME_RESOURCE_STATS) || !BP_RESUME_RESOURCE_STATS
#error "Complete policy scope requires resource/whole-cell timing"
#endif
#define COMPLETE_SCOPE_DRAIN_POLLS 4096U
#endif
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
#include <signal.h>
#define PR_BP_ICACHE_RETENTION_CONTROL 0x42505061
#define PR_BP_ICACHE_RETENTION_STATUS 0x42505062
#endif

#if !defined(BP_RESUME_HOST_VERIFY) && (!defined(__riscv) || __riscv_xlen != 64)
#error "This benchmark requires RV64 BlackParrot"
#endif

#ifdef BP_RESUME_HOST_VERIFY
/* Software protocol verification only: never emit FPGA performance markers. */
#define PIPE_HINT_LABEL(name) "PIPE_HINT_HOST_VERIFY_" name
#else
#define PIPE_HINT_LABEL(name) "PIPE_HINT_" name
#endif

#define PR_BP_PREVIEW_ICACHE_STATUS 0x4250505e
#define PR_BP_PREVIEW_ICACHE_TRIGGER 0x4250505f
#define PR_BP_PREVIEW_ENABLE 0x4250505a

enum {
	default_loops = 512,
	default_repeats = 8,
	warmup_roundtrips = 32,
};

enum hint_policy {
	hint_continuous,
	hint_continuous_unmatched,
	hint_futex_early,
	hint_futex_early_both,
	hint_seed_once,
	hint_preseed,
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
	hint_retention_rr,
	hint_retention_first,
#endif
};

enum sync_policy {
	sync_pipe,
	sync_futex,
};

enum profile_policy {
	profile_plain,
	profile_legs,
};

struct cell_result {
	uint64_t elapsed;
	uint64_t child_resume;
	uint64_t parent_resume;
};

struct futex_shared {
	_Atomic uint32_t turn;
	uint32_t pad;
	volatile uint64_t parent_launch;
	volatile uint64_t child_launch;
	volatile uint64_t child_resume;
};

static void fail(const char *message)
{
	perror(message);
	exit(1);
}

#if defined(BP_RESUME_RESOURCE_STATS) && BP_RESUME_RESOURCE_STATS
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
#endif

static uint64_t cycle(void)
{
#ifdef BP_RESUME_HOST_VERIFY
	struct timespec now;
	if (clock_gettime(CLOCK_MONOTONIC, &now))
		fail("host verification clock");
	return (uint64_t)now.tv_sec * 1000000000 + now.tv_nsec;
#else
	uint64_t value;

	__asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
	return value;
#endif
}

static void flush_instruction_state(void)
{
#ifdef BP_RESUME_HOST_VERIFY
	atomic_thread_fence(memory_order_seq_cst);
#else
	__asm__ volatile("fence.i" : : : "memory");
#endif
}

static void transfer(int fd, unsigned char *token, int write_token)
{
	ssize_t result;

	do {
		result = write_token ? write(fd, token, 1) : read(fd, token, 1);
	} while (result < 0 && errno == EINTR);
	if (result != 1)
		fail(write_token ? "pipe write" : "pipe read");
}

static unsigned parse_positive(const char *text, const char *label)
{
	char *end = NULL;
	unsigned long value;

	errno = 0;
	value = strtoul(text, &end, 0);
	if (errno || !end || *end || value == 0 || value > 1000000UL) {
		fprintf(stderr, "%s must be in 1..1000000\n", label);
		exit(2);
	}
	return (unsigned)value;
}

static unsigned parse_working_set(const char *text)
{
	char *end = NULL;
	unsigned long value;

	errno = 0;
	value = strtoul(text, &end, 0);
	if (errno || !end || end == text || *end || text[0] == '-' || value > 65536UL) {
		fputs("working-set-kib must be in 0..65536\n", stderr);
		exit(2);
	}
	return (unsigned)value;
}

static struct resume_workload allocate_working_set(unsigned kib, unsigned salt,
						   const char *workload)
{
	struct resume_workload result;

	if (resume_workload_init(&result, workload, kib, salt))
		fail("working-set allocation");
	return result;
}

static void check_working_set(struct resume_workload *work, uint64_t checksum)
{
	if (!resume_workload_check_total(work, checksum)) {
		fputs("working-set checksum mismatch\n", stderr);
		exit(1);
	}
	resume_workload_free(work);
}

static enum hint_policy parse_policy(const char *text)
{
	if (!strcmp(text, "continuous"))
		return hint_continuous;
	if (!strcmp(text, "continuous-unmatched"))
		return hint_continuous_unmatched;
	if (!strcmp(text, "futex-early"))
		return hint_futex_early;
	if (!strcmp(text, "futex-early-both"))
		return hint_futex_early_both;
	if (!strcmp(text, "seed"))
		return hint_seed_once;
	if (!strcmp(text, "preseed"))
		return hint_preseed;
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
	if (!strcmp(text, "retention-rr"))
		return hint_retention_rr;
	if (!strcmp(text, "retention-first"))
		return hint_retention_first;
	fprintf(stderr, "policy must be continuous, continuous-unmatched, futex-early, futex-early-both, seed, preseed, retention-rr, or retention-first\n");
#else
	fprintf(stderr, "policy must be continuous, continuous-unmatched, futex-early, futex-early-both, seed, or preseed\n");
#endif
	exit(2);
}

static enum sync_policy parse_sync(const char *text)
{
	if (!strcmp(text, "pipe"))
		return sync_pipe;
	if (!strcmp(text, "futex"))
		return sync_futex;
	fprintf(stderr, "sync must be pipe or futex\n");
	exit(2);
}

static enum profile_policy parse_profile(const char *text)
{
	if (!strcmp(text, "plain"))
		return profile_plain;
	if (!strcmp(text, "legs"))
		return profile_legs;
	fprintf(stderr, "profile must be plain or legs\n");
	exit(2);
}

static unsigned long prefix_status(void)
{
#if defined(BP_RESUME_HOST_VERIFY) \
 && !(defined(BP_RESUME_COMPLETE_POLICY_SCOPE) && BP_RESUME_COMPLETE_POLICY_SCOPE)
	return (32UL << 4) | 1;
#else
	unsigned long status;

	if (prctl(PR_BP_PREVIEW_ICACHE_STATUS, (unsigned long)&status,
		  0UL, 0UL, 0UL))
		fail("instruction-prefix status");
	return status;
#endif
}

static void issue_hint(unsigned enabled)
{
#if defined(BP_RESUME_HOST_VERIFY) \
 && !(defined(BP_RESUME_COMPLETE_POLICY_SCOPE) && BP_RESUME_COMPLETE_POLICY_SCOPE)
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
	extern void bp_resume_host_retention_hint(unsigned enabled);
	bp_resume_host_retention_hint(enabled);
#else
	(void)enabled;
#endif
#else
	if (prctl(PR_BP_PREVIEW_ICACHE_TRIGGER, enabled, 0UL, 0UL, 0UL))
		fail("instruction-prefix trigger");
#endif
}

static void issue_iteration_hint(unsigned enabled, enum hint_policy policy,
				 unsigned iteration)
{
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
	if (policy == hint_retention_rr || policy == hint_retention_first)
		return;
#endif
	if (policy == hint_continuous_unmatched) {
		if (enabled)
			issue_hint(1);
		return;
	}
	issue_hint(enabled && (policy == hint_continuous || iteration == 0));
}

static void set_futex_early_mode(unsigned enabled)
{
#if defined(BP_RESUME_HOST_VERIFY) \
 && !(defined(BP_RESUME_COMPLETE_POLICY_SCOPE) && BP_RESUME_COMPLETE_POLICY_SCOPE)
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
	extern void bp_resume_host_retention_task_mode(unsigned enabled);
	bp_resume_host_retention_task_mode(enabled);
#else
	(void)enabled;
#endif
#else
	if (prctl(PR_BP_PREVIEW_ENABLE, enabled ? 14UL : 0UL, 0UL, 0UL, 0UL))
		fail("futex-early preview mode");
#endif
}

static int is_futex_early(enum hint_policy policy)
{
	return policy == hint_futex_early || policy == hint_futex_early_both;
}

#if defined(BP_RESUME_COMPLETE_POLICY_SCOPE) && BP_RESUME_COMPLETE_POLICY_SCOPE
static void complete_policy_scope_reset(void)
{
	const unsigned long pending = (1UL << 1) | (1UL << 2) | (1UL << 3)
				      | (1UL << 54);

	/* Task mode must be zero before polling: a reschedule during a status
	 * syscall must not launch another selection-time mode-14 sweep. These
	 * CSR bits describe the prefix controller, not all UCE response slots.
	 */
	set_futex_early_mode(0);
	for (unsigned poll = 0; poll < COMPLETE_SCOPE_DRAIN_POLLS; ++poll)
		if (!(prefix_status() & pending))
			return;
	errno = ETIMEDOUT;
	fail("complete policy scope prefix-controller drain");
}
#endif

#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
#ifdef BP_RESUME_HOST_VERIFY
/* Host tests must supply an explicit shared-state hardware mock. */
extern int bp_resume_host_retention_prctl(int option, unsigned long arg2,
		unsigned long arg3, unsigned long arg4, unsigned long arg5);
#define retention_prctl bp_resume_host_retention_prctl
#else
#define retention_prctl prctl
#endif

static pid_t retention_owner, retention_child;
static unsigned retention_armed;

static uint64_t retention_read_status(void)
{
	uint64_t status = 0;

	if (retention_prctl(PR_BP_ICACHE_RETENTION_STATUS,
			    (unsigned long)&status, 0UL, 0UL, 0UL))
		fail("I-retention status/probe");
	if (!(status & (UINT64_C(1) << 63))) {
		errno = ENODEV;
		fail("I-retention capability absent");
	}
	return status;
}

static void retention_cleanup(void)
{
	int status;
	pid_t waited;

	/* The policy is CPU-global. Inherited child exit handlers must never
	 * disable it during the parent's measurement or another child's work.
	 */
	if (getpid() != retention_owner)
		return;
	if (retention_child > 0) {
		do { waited = waitpid(retention_child, &status, WNOHANG); }
		while (waited < 0 && errno == EINTR);
		if (!waited) {
			kill(retention_child, SIGKILL);
			while (waitpid(retention_child, &status, 0) < 0 && errno == EINTR) { }
		}
		retention_child = 0;
	}
	if (retention_armed) {
		if (retention_prctl(PR_BP_ICACHE_RETENTION_CONTROL, 0UL, 0UL, 0UL, 0UL)) {
			perror("I-retention error cleanup/reset");
			_Exit(1);
		}
		retention_armed = 0;
	}
}

static void retention_initialize(void)
{
	retention_owner = getpid();
	if (atexit(retention_cleanup))
		fail("I-retention cleanup registration");
	(void)retention_read_status();
	retention_armed = 1;
	/* Exec need not clear an old per-task preview mode. Retention tests
	 * must not accidentally inherit kernel wake hints from earlier code.
	 * Explicit futex policies rearm their own mode later as before.
	 */
	set_futex_early_mode(0);
}

static unsigned retention_mode(enum hint_policy policy, unsigned enabled)
{
	if (!enabled)
		return 0;
	return policy == hint_retention_rr ? 1 : policy == hint_retention_first ? 2 : 0;
}

static void retention_start_cell(enum hint_policy policy, unsigned enabled)
{
	unsigned mode = retention_mode(policy, enabled);

	retention_armed = 1;
	/* Both processes have allocated private state and completed setup fences.
	 * One global write/fence resets this cell; no per-wake hint is emitted.
	 */
	if (retention_prctl(PR_BP_ICACHE_RETENTION_CONTROL, (unsigned long)mode,
			    0UL, 0UL, 0UL))
		fail("I-retention policy control");
	if ((retention_read_status() & 3) != mode) {
		errno = EIO;
		fail("I-retention policy readback");
	}
}

static uint64_t retention_finish_cell(enum hint_policy policy, unsigned enabled)
{
	uint64_t status = retention_read_status();

	if ((status & 3) != retention_mode(policy, enabled)) {
		errno = EIO;
		fail("I-retention policy changed during cell");
	}
	if (retention_prctl(PR_BP_ICACHE_RETENTION_CONTROL, 0UL, 0UL, 0UL, 0UL))
		fail("I-retention normal reset");
	if (retention_read_status() & 3) {
		errno = EIO;
		fail("I-retention reset readback");
	}
	retention_armed = 0;
	return status;
}
#endif

static void futex_wait_for(_Atomic uint32_t *word, uint32_t wanted)
{
	for (;;) {
		uint32_t observed = atomic_load_explicit(word, memory_order_acquire);

		if (observed == wanted)
			return;
		if (syscall(SYS_futex, (uint32_t *)word, FUTEX_WAIT,
			    observed, NULL, NULL, 0) && errno != EAGAIN && errno != EINTR)
			fail("futex wait");
	}
}

static void futex_set_wake(_Atomic uint32_t *word, uint32_t value)
{
	atomic_store_explicit(word, value, memory_order_release);
	if (syscall(SYS_futex, (uint32_t *)word, FUTEX_WAKE,
		    1, NULL, NULL, 0) < 0)
		fail("futex wake");
}

static struct cell_result run_pipe_cell(unsigned enabled, unsigned loops,
					unsigned warmup,
					enum hint_policy policy,
					unsigned working_set_kib,
					 const char *workload)
{
	int to_child[2], to_parent[2], ready[2];
	unsigned char token = 0;
	uint64_t begin, end;
	pid_t child;
	int status;
	struct resume_workload parent_working_set;
	uint64_t parent_checksum = 0;

	if (pipe(to_child) || pipe(to_parent) || pipe(ready))
		fail("pipe");
	child = fork();
	if (child < 0)
		fail("fork");
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
	if (child)
		retention_child = child;
#endif
	if (!child) {
		struct resume_workload child_working_set =
			allocate_working_set(working_set_kib, 0x5a, workload);
		uint64_t child_checksum = 0;

		close(to_child[1]);
		close(to_parent[0]);
		close(ready[0]);
		flush_instruction_state();
		transfer(ready[1], &token, 1);
		for (unsigned i = 0; i < warmup + loops; ++i) {
			transfer(to_child[0], &token, 0);
			child_checksum += resume_workload_run(&child_working_set);
			if (policy != hint_preseed)
				issue_iteration_hint(enabled, policy, i);
			transfer(to_parent[1], &token, 1);
		}
		/* Parent releases this only after sampling the timed endpoint. */
		transfer(to_child[0], &token, 0);
		check_working_set(&child_working_set, child_checksum);
		_exit(0);
	}

	parent_working_set = allocate_working_set(working_set_kib, 0xa5, workload);
	close(to_child[0]);
	close(to_parent[1]);
	close(ready[1]);
	transfer(ready[0], &token, 0);
	flush_instruction_state();
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
	retention_start_cell(policy, enabled);
#endif
	if (policy == hint_preseed)
		issue_hint(enabled);
	for (unsigned i = 0; i < warmup; ++i) {
		if (policy != hint_preseed)
			issue_iteration_hint(enabled, policy, i);
		transfer(to_child[1], &token, 1);
		transfer(to_parent[0], &token, 0);
		parent_checksum += resume_workload_run(&parent_working_set);
	}
	begin = cycle();
	for (unsigned i = 0; i < loops; ++i) {
		if (policy != hint_preseed)
			issue_iteration_hint(enabled, policy, warmup + i);
		transfer(to_child[1], &token, 1);
		transfer(to_parent[0], &token, 0);
		parent_checksum += resume_workload_run(&parent_working_set);
	}
	end = cycle();
	transfer(to_child[1], &token, 1);
	if (waitpid(child, &status, 0) != child || !WIFEXITED(status)
	    || WEXITSTATUS(status)) {
		fputs("pipe child failed\n", stderr);
		exit(1);
	}
	close(to_child[1]);
	close(to_parent[0]);
	close(ready[0]);
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
	retention_child = 0;
#endif
	check_working_set(&parent_working_set, parent_checksum);
	return (struct cell_result){ .elapsed = end - begin };
}

static struct cell_result run_futex_cell(unsigned enabled, unsigned loops,
					 unsigned warmup,
					 enum hint_policy policy,
					 enum profile_policy profile,
					 unsigned working_set_kib,
					 const char *workload)
{
	struct futex_shared *shared = mmap(NULL, sizeof(*shared),
					  PROT_READ | PROT_WRITE,
					  MAP_SHARED | MAP_ANONYMOUS, -1, 0);
	int ready[2];
	unsigned char token = 0;
	uint64_t begin, end, parent_resume = 0;
	pid_t child;
	int status;
	struct resume_workload parent_working_set;
	uint64_t parent_checksum = 0;

	if (shared == MAP_FAILED || pipe(ready))
		fail("futex setup");
	if (is_futex_early(policy))
		set_futex_early_mode(enabled);
	atomic_init(&shared->turn, 0);
	child = fork();
	if (child < 0)
		fail("fork");
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
	if (child)
		retention_child = child;
#endif
	if (!child) {
		struct resume_workload child_working_set =
			allocate_working_set(working_set_kib, 0x3c, workload);
		/* Linux clears preview mode in both clone paths. Preserve the
		 * historical parent-only policy; opt in explicitly for reverse wakes.
		 */
		if (policy == hint_futex_early_both)
			set_futex_early_mode(enabled);
		close(ready[0]);
		flush_instruction_state();
		transfer(ready[1], &token, 1);
		uint64_t child_resume = 0;
		uint64_t child_checksum = 0;
		for (unsigned i = 0; i < warmup + loops; ++i) {
			futex_wait_for(&shared->turn, 1);
			if (profile == profile_legs && i >= warmup)
				child_resume += cycle() - shared->parent_launch;
			child_checksum += resume_workload_run(&child_working_set);
			if (policy != hint_preseed && !is_futex_early(policy))
				issue_iteration_hint(enabled, policy, i);
			if (profile == profile_legs && i >= warmup)
				shared->child_launch = cycle();
			futex_set_wake(&shared->turn, 0);
		}
		shared->child_resume = child_resume;
		/* Verification can take O(roundtrips * requests) work. Park until
		 * the parent has sampled end; it must not delay the last return.
		 */
		futex_wait_for(&shared->turn, 2);
		check_working_set(&child_working_set, child_checksum);
		_exit(0);
	}

	parent_working_set = allocate_working_set(working_set_kib, 0xc3, workload);
	close(ready[1]);
	transfer(ready[0], &token, 0);
	flush_instruction_state();
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
	retention_start_cell(policy, enabled);
#endif
	if (policy == hint_preseed)
		issue_hint(enabled);
	for (unsigned i = 0; i < warmup; ++i) {
		if (policy != hint_preseed && !is_futex_early(policy))
			issue_iteration_hint(enabled, policy, i);
		futex_set_wake(&shared->turn, 1);
		futex_wait_for(&shared->turn, 0);
		parent_checksum += resume_workload_run(&parent_working_set);
	}
	begin = cycle();
	for (unsigned i = 0; i < loops; ++i) {
		if (policy != hint_preseed && !is_futex_early(policy))
			issue_iteration_hint(enabled, policy, warmup + i);
		if (profile == profile_legs)
			shared->parent_launch = cycle();
		futex_set_wake(&shared->turn, 1);
		futex_wait_for(&shared->turn, 0);
		if (profile == profile_legs)
			parent_resume += cycle() - shared->child_launch;
		parent_checksum += resume_workload_run(&parent_working_set);
	}
	end = cycle();
	futex_set_wake(&shared->turn, 2);
	if (waitpid(child, &status, 0) != child || !WIFEXITED(status)
	    || WEXITSTATUS(status)) {
		fputs("futex child failed\n", stderr);
		exit(1);
	}
	close(ready[0]);
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
	retention_child = 0;
#endif
	struct cell_result result = {
		.elapsed = end - begin,
		.child_resume = shared->child_resume,
		.parent_resume = parent_resume,
	};
	if (munmap(shared, sizeof(*shared)))
		fail("futex munmap");
	check_working_set(&parent_working_set, parent_checksum);
	return result;
}

int main(int argc, char **argv)
{
	unsigned loops = default_loops;
	unsigned repeats = default_repeats;
	unsigned warmup = warmup_roundtrips;
	unsigned working_set_kib = 0;
	const char *workload = "scan";
	enum hint_policy policy = hint_continuous;
	enum sync_policy sync = sync_pipe;
	enum profile_policy profile = profile_plain;
	unsigned long before, after;

	if (argc > 9) {
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
		fprintf(stderr, "usage: %s [loops] [repeats] [continuous|continuous-unmatched|futex-early|futex-early-both|seed|preseed|retention-rr|retention-first] [warmup] [pipe|futex] [plain|legs] [working-set-kib] [scan|lookup|parse|chase]\n",
#else
		fprintf(stderr, "usage: %s [loops] [repeats] [continuous|continuous-unmatched|futex-early|futex-early-both|seed|preseed] [warmup] [pipe|futex] [plain|legs] [working-set-kib] [scan|lookup|parse|chase]\n",
#endif
			argv[0]);
		return 2;
	}
	if (argc > 1)
		loops = parse_positive(argv[1], "loops");
	if (argc > 2)
		repeats = parse_positive(argv[2], "repeats");
	if (argc > 3)
		policy = parse_policy(argv[3]);
	if (argc > 4)
		warmup = parse_positive(argv[4], "warmup");
	if (argc > 5)
		sync = parse_sync(argv[5]);
	if (argc > 6)
		profile = parse_profile(argv[6]);
	if (argc > 7)
		working_set_kib = parse_working_set(argv[7]);
	if (argc > 8)
		workload = argv[8];
	if (strcmp(workload, "scan") && strcmp(workload, "lookup")
	    && strcmp(workload, "parse") && strcmp(workload, "chase")
#if defined(BP_RESUME_ZLIB) && BP_RESUME_ZLIB
	    && strcmp(workload, "deflate")
#endif
	   ) {
		fputs("invalid resume workload\n", stderr);
		return 2;
	}
	if (profile == profile_legs && sync != sync_futex) {
		fputs("legs profile requires futex synchronization\n", stderr);
		return 2;
	}
	if (is_futex_early(policy) && sync != sync_futex) {
		fputs("futex-early policy requires futex synchronization\n", stderr);
		return 2;
	}
#if defined(BP_RESUME_COMPLETE_POLICY_SCOPE) && BP_RESUME_COMPLETE_POLICY_SCOPE
	/* Establish a clean first cell before library/config observer output. */
	complete_policy_scope_reset();
#endif
#if defined(BP_RESUME_ZLIB) && BP_RESUME_ZLIB
	if (!strcmp(workload, "deflate"))
		printf(PIPE_HINT_LABEL("LIBRARY") " name=zlib version=%s block_bytes=%u input_corpus_kib=%u\n",
		       zlibVersion(), RESUME_ZLIB_BLOCK_BYTES, working_set_kib);
#endif
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
	retention_initialize();
#endif
	before = prefix_status();
#ifdef BP_RESUME_HOST_VERIFY
	fputs("Software protocol verification only; host nanoseconds are not BlackParrot cycles.\n", stderr);
#endif
	printf(PIPE_HINT_LABEL("CONFIG") " loops=%u repeats=%u warmup=%u configured_entries=%lu policy=%s sync=%s profile=%s working_set_kib=%u workload=%s terminal_handshake=1\n",
	       loops, repeats, warmup, (before >> 4) & 0x1ffUL,
	       policy == hint_continuous ? "continuous"
	       : policy == hint_continuous_unmatched ? "continuous-unmatched"
	       : policy == hint_futex_early ? "futex-early"
	       : policy == hint_futex_early_both ? "futex-early-both"
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
	       : policy == hint_retention_rr ? "retention-rr"
	       : policy == hint_retention_first ? "retention-first"
#endif
	       : policy == hint_seed_once ? "seed" : "preseed",
	       sync == sync_pipe ? "pipe" : "futex",
	       profile == profile_plain ? "plain" : "legs", working_set_kib, workload);
#if defined(BP_RESUME_COMPLETE_POLICY_SCOPE) && BP_RESUME_COMPLETE_POLICY_SCOPE
	printf(PIPE_HINT_LABEL("SCOPE") " version=1 mode=cell cleanup=mode0 drain=prefix-controller max_polls=%u\n",
	       COMPLETE_SCOPE_DRAIN_POLLS);
#endif
	for (unsigned repeat = 0; repeat < repeats; ++repeat) {
		unsigned first = repeat & 1U;

		for (unsigned order = 0; order < 2; ++order) {
			unsigned enabled = first ^ order;
#if (defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION) \
 || (defined(BP_RESUME_RESOURCE_STATS) && BP_RESUME_RESOURCE_STATS)
			uint64_t whole_begin = cycle(), whole_elapsed;
#endif
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
			uint64_t retention_status;
#endif
#if defined(BP_RESUME_RESOURCE_STATS) && BP_RESUME_RESOURCE_STATS
			struct cell_resources resources_before = resource_snapshot();
			struct cell_resource_delta resources;
#endif
			struct cell_result result = sync == sync_pipe
				? run_pipe_cell(enabled, loops, warmup, policy,
						working_set_kib, workload)
				: run_futex_cell(enabled, loops, warmup, policy,
						  profile, working_set_kib, workload);
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
			/* Charge allocation, fork, setup, warmup, verification, teardown,
			 * status reads and policy reset separately from steady work.
			 */
			retention_status = retention_finish_cell(policy, enabled);
#endif
#if defined(BP_RESUME_COMPLETE_POLICY_SCOPE) && BP_RESUME_COMPLETE_POLICY_SCOPE
			/* run_*_cell has checked, reaped and freed both workloads. Charge
			 * mode reset and bounded controller drain to this cell, before the
			 * ending observers/timestamp and every result print. Both arms pay
			 * this cleanup; the next cell's initial mmap/pipe starts in mode 0.
			 */
			complete_policy_scope_reset();
#endif
#if defined(BP_RESUME_RESOURCE_STATS) && BP_RESUME_RESOURCE_STATS
			/* Include verification, reaping, frees, and retention reset/status.
			 * The whole-cell timer also charges both observer snapshots.
			 */
			resources = resource_delta(resource_snapshot(), resources_before);
#endif
#if (defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION) \
 || (defined(BP_RESUME_RESOURCE_STATS) && BP_RESUME_RESOURCE_STATS)
			whole_elapsed = cycle() - whole_begin;
#endif

			printf(PIPE_HINT_LABEL("RESULT") " repeat=%u order=%u enabled=%u cycles=%llu loops=%u\n",
			       repeat, order, enabled,
			       (unsigned long long)result.elapsed, loops);
			if (profile == profile_legs)
				printf(PIPE_HINT_LABEL("LEGS") " repeat=%u order=%u enabled=%u child_resume=%llu parent_resume=%llu loops=%u\n",
				       repeat, order, enabled,
				       (unsigned long long)result.child_resume,
				       (unsigned long long)result.parent_resume,
				       loops);
#if (defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION) \
 || (defined(BP_RESUME_RESOURCE_STATS) && BP_RESUME_RESOURCE_STATS)
			printf(PIPE_HINT_LABEL("WHOLE") " repeat=%u order=%u enabled=%u cycles=%llu loops=%u\n",
			       repeat, order, enabled, (unsigned long long)whole_elapsed, loops);
#endif
#if defined(BP_RESUME_RETENTION) && BP_RESUME_RETENTION
			printf(PIPE_HINT_LABEL("RETENTION") " repeat=%u order=%u enabled=%u raw=0x%016llx capability=%u mode=%u completed=%u consumed_fetches=%u\n",
			       repeat, order, enabled, (unsigned long long)retention_status,
			       (unsigned)(retention_status >> 63), (unsigned)(retention_status & 3),
			       (unsigned)((retention_status >> 2) & 1),
			       (unsigned)((retention_status >> 16) & 0xffff));
#endif
#if defined(BP_RESUME_RESOURCE_STATS) && BP_RESUME_RESOURCE_STATS
			printf(PIPE_HINT_LABEL("RESOURCE") " repeat=%u order=%u enabled=%u minor_faults=%llu major_faults=%llu user_us=%llu system_us=%llu voluntary_switches=%llu involuntary_switches=%llu\n",
			       repeat, order, enabled,
			       (unsigned long long)resources.minor_faults,
			       (unsigned long long)resources.major_faults,
			       (unsigned long long)resources.user_us,
			       (unsigned long long)resources.system_us,
			       (unsigned long long)resources.voluntary_switches,
			       (unsigned long long)resources.involuntary_switches);
#endif
			fflush(stdout);
		}
	}
	after = prefix_status();
	printf(PIPE_HINT_LABEL("STATUS") " before=0x%016lx after=0x%016lx configured_entries=%lu dropped=%lu\n",
	       before, after, (after >> 4) & 0x1ffUL,
	       (after >> 46) & 0xffUL);
	puts(PIPE_HINT_LABEL("PASS"));
	return 0;
}
