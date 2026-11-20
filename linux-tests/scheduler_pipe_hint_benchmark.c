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
	fprintf(stderr, "policy must be continuous, continuous-unmatched, futex-early, futex-early-both, seed, or preseed\n");
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
#ifdef BP_RESUME_HOST_VERIFY
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
#ifdef BP_RESUME_HOST_VERIFY
	(void)enabled;
#else
	if (prctl(PR_BP_PREVIEW_ICACHE_TRIGGER, enabled, 0UL, 0UL, 0UL))
		fail("instruction-prefix trigger");
#endif
}

static void issue_iteration_hint(unsigned enabled, enum hint_policy policy,
				 unsigned iteration)
{
	if (policy == hint_continuous_unmatched) {
		if (enabled)
			issue_hint(1);
		return;
	}
	issue_hint(enabled && (policy == hint_continuous || iteration == 0));
}

static void set_futex_early_mode(unsigned enabled)
{
#ifdef BP_RESUME_HOST_VERIFY
	(void)enabled;
#else
	if (prctl(PR_BP_PREVIEW_ENABLE, enabled ? 14UL : 0UL, 0UL, 0UL, 0UL))
		fail("futex-early preview mode");
#endif
}

static int is_futex_early(enum hint_policy policy)
{
	return policy == hint_futex_early || policy == hint_futex_early_both;
}

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
		fprintf(stderr, "usage: %s [loops] [repeats] [continuous|continuous-unmatched|futex-early|futex-early-both|seed|preseed] [warmup] [pipe|futex] [plain|legs] [working-set-kib] [scan|lookup|parse|chase]\n",
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
	    && strcmp(workload, "parse") && strcmp(workload, "chase")) {
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
	       : policy == hint_seed_once ? "seed" : "preseed",
	       sync == sync_pipe ? "pipe" : "futex",
	       profile == profile_plain ? "plain" : "legs", working_set_kib, workload);
	for (unsigned repeat = 0; repeat < repeats; ++repeat) {
		unsigned first = repeat & 1U;

		for (unsigned order = 0; order < 2; ++order) {
			unsigned enabled = first ^ order;
			struct cell_result result = sync == sync_pipe
				? run_pipe_cell(enabled, loops, warmup, policy,
						working_set_kib, workload)
				: run_futex_cell(enabled, loops, warmup, policy,
						  profile, working_set_kib, workload);

			printf(PIPE_HINT_LABEL("RESULT") " repeat=%u order=%u enabled=%u cycles=%llu loops=%u\n",
			       repeat, order, enabled,
			       (unsigned long long)result.elapsed, loops);
			if (profile == profile_legs)
				printf(PIPE_HINT_LABEL("LEGS") " repeat=%u order=%u enabled=%u child_resume=%llu parent_resume=%llu loops=%u\n",
				       repeat, order, enabled,
				       (unsigned long long)result.child_resume,
				       (unsigned long long)result.parent_resume,
				       loops);
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
