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

#if !defined(__riscv) || __riscv_xlen != 64
#error "This benchmark requires RV64 BlackParrot"
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
	uint64_t value;

	__asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
	return value;
}

static void flush_instruction_state(void)
{
	__asm__ volatile("fence.i" : : : "memory");
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
	if (errno || !end || *end || value > 65536UL) {
		fputs("working-set-kib must be in 0..65536\n", stderr);
		exit(2);
	}
	return (unsigned)value;
}

static volatile unsigned char *allocate_working_set(unsigned kib, unsigned salt)
{
	size_t bytes = (size_t)kib * 1024;
	volatile unsigned char *buffer;

	if (!bytes)
		return NULL;
	buffer = mmap(NULL, bytes, PROT_READ | PROT_WRITE,
		      MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	if (buffer == MAP_FAILED)
		fail("working-set mmap");
	for (size_t offset = 0; offset < bytes; offset += 64)
		buffer[offset] = (unsigned char)(salt + offset / 64);
	return buffer;
}

static uint64_t touch_working_set(volatile unsigned char *buffer, unsigned kib)
{
	size_t bytes = (size_t)kib * 1024;
	uint64_t checksum = 0;

	for (size_t offset = 0; offset < bytes; offset += 64)
		checksum += buffer[offset];
	return checksum;
}

static void release_working_set(volatile unsigned char *buffer, unsigned kib)
{
	if (buffer && munmap((void *)buffer, (size_t)kib * 1024))
		fail("working-set munmap");
}

static enum hint_policy parse_policy(const char *text)
{
	if (!strcmp(text, "continuous"))
		return hint_continuous;
	if (!strcmp(text, "continuous-unmatched"))
		return hint_continuous_unmatched;
	if (!strcmp(text, "futex-early"))
		return hint_futex_early;
	if (!strcmp(text, "seed"))
		return hint_seed_once;
	if (!strcmp(text, "preseed"))
		return hint_preseed;
	fprintf(stderr, "policy must be continuous, continuous-unmatched, futex-early, seed, or preseed\n");
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
	unsigned long status;

	if (prctl(PR_BP_PREVIEW_ICACHE_STATUS, (unsigned long)&status,
		  0UL, 0UL, 0UL))
		fail("instruction-prefix status");
	return status;
}

static void issue_hint(unsigned enabled)
{
	if (prctl(PR_BP_PREVIEW_ICACHE_TRIGGER, enabled, 0UL, 0UL, 0UL))
		fail("instruction-prefix trigger");
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
	if (prctl(PR_BP_PREVIEW_ENABLE, enabled ? 14UL : 0UL, 0UL, 0UL, 0UL))
		fail("futex-early preview mode");
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
					unsigned working_set_kib)
{
	int to_child[2], to_parent[2], ready[2];
	unsigned char token = 0;
	uint64_t begin, end;
	pid_t child;
	int status;
	volatile unsigned char *parent_working_set;
	uint64_t parent_checksum = 0;

	if (pipe(to_child) || pipe(to_parent) || pipe(ready))
		fail("pipe");
	child = fork();
	if (child < 0)
		fail("fork");
	if (!child) {
		volatile unsigned char *child_working_set =
			allocate_working_set(working_set_kib, 0x5a);
		uint64_t child_checksum = 0;

		close(to_child[1]);
		close(to_parent[0]);
		close(ready[0]);
		flush_instruction_state();
		transfer(ready[1], &token, 1);
		for (unsigned i = 0; i < warmup + loops; ++i) {
			transfer(to_child[0], &token, 0);
			child_checksum += touch_working_set(
				child_working_set, working_set_kib);
			if (policy != hint_preseed)
				issue_iteration_hint(enabled, policy, i);
			transfer(to_parent[1], &token, 1);
		}
		release_working_set(child_working_set, working_set_kib);
		_exit(child_checksum == UINT64_MAX);
	}

	parent_working_set = allocate_working_set(working_set_kib, 0xa5);
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
		parent_checksum += touch_working_set(
			parent_working_set, working_set_kib);
	}
	begin = cycle();
	for (unsigned i = 0; i < loops; ++i) {
		if (policy != hint_preseed)
			issue_iteration_hint(enabled, policy, warmup + i);
		transfer(to_child[1], &token, 1);
		transfer(to_parent[0], &token, 0);
		parent_checksum += touch_working_set(
			parent_working_set, working_set_kib);
	}
	end = cycle();
	if (waitpid(child, &status, 0) != child || !WIFEXITED(status)
	    || WEXITSTATUS(status)) {
		fputs("pipe child failed\n", stderr);
		exit(1);
	}
	release_working_set(parent_working_set, working_set_kib);
	if (parent_checksum == UINT64_MAX)
		fail("working-set checksum");
	return (struct cell_result){ .elapsed = end - begin };
}

static struct cell_result run_futex_cell(unsigned enabled, unsigned loops,
					 unsigned warmup,
					 enum hint_policy policy,
					 enum profile_policy profile,
					 unsigned working_set_kib)
{
	struct futex_shared *shared = mmap(NULL, sizeof(*shared),
					  PROT_READ | PROT_WRITE,
					  MAP_SHARED | MAP_ANONYMOUS, -1, 0);
	int ready[2];
	unsigned char token = 0;
	uint64_t begin, end, parent_resume = 0;
	pid_t child;
	int status;
	volatile unsigned char *parent_working_set;
	uint64_t parent_checksum = 0;

	if (shared == MAP_FAILED || pipe(ready))
		fail("futex setup");
	if (policy == hint_futex_early)
		set_futex_early_mode(enabled);
	atomic_init(&shared->turn, 0);
	child = fork();
	if (child < 0)
		fail("fork");
	if (!child) {
		volatile unsigned char *child_working_set =
			allocate_working_set(working_set_kib, 0x3c);
		close(ready[0]);
		flush_instruction_state();
		transfer(ready[1], &token, 1);
		uint64_t child_resume = 0;
		uint64_t child_checksum = 0;
		for (unsigned i = 0; i < warmup + loops; ++i) {
			futex_wait_for(&shared->turn, 1);
			if (profile == profile_legs && i >= warmup)
				child_resume += cycle() - shared->parent_launch;
			child_checksum += touch_working_set(
				child_working_set, working_set_kib);
			if (policy != hint_preseed && policy != hint_futex_early)
				issue_iteration_hint(enabled, policy, i);
			if (profile == profile_legs && i >= warmup)
				shared->child_launch = cycle();
			futex_set_wake(&shared->turn, 0);
		}
		shared->child_resume = child_resume;
		release_working_set(child_working_set, working_set_kib);
		_exit(child_checksum == UINT64_MAX);
	}

	parent_working_set = allocate_working_set(working_set_kib, 0xc3);
	close(ready[1]);
	transfer(ready[0], &token, 0);
	flush_instruction_state();
	if (policy == hint_preseed)
		issue_hint(enabled);
	for (unsigned i = 0; i < warmup; ++i) {
		if (policy != hint_preseed && policy != hint_futex_early)
			issue_iteration_hint(enabled, policy, i);
		futex_set_wake(&shared->turn, 1);
		futex_wait_for(&shared->turn, 0);
		parent_checksum += touch_working_set(
			parent_working_set, working_set_kib);
	}
	begin = cycle();
	for (unsigned i = 0; i < loops; ++i) {
		if (policy != hint_preseed && policy != hint_futex_early)
			issue_iteration_hint(enabled, policy, warmup + i);
		if (profile == profile_legs)
			shared->parent_launch = cycle();
		futex_set_wake(&shared->turn, 1);
		futex_wait_for(&shared->turn, 0);
		if (profile == profile_legs)
			parent_resume += cycle() - shared->child_launch;
		parent_checksum += touch_working_set(
			parent_working_set, working_set_kib);
	}
	end = cycle();
	if (waitpid(child, &status, 0) != child || !WIFEXITED(status)
	    || WEXITSTATUS(status)) {
		fputs("futex child failed\n", stderr);
		exit(1);
	}
	struct cell_result result = {
		.elapsed = end - begin,
		.child_resume = shared->child_resume,
		.parent_resume = parent_resume,
	};
	if (munmap(shared, sizeof(*shared)))
		fail("futex munmap");
	release_working_set(parent_working_set, working_set_kib);
	if (parent_checksum == UINT64_MAX)
		fail("working-set checksum");
	return result;
}

int main(int argc, char **argv)
{
	unsigned loops = default_loops;
	unsigned repeats = default_repeats;
	unsigned warmup = warmup_roundtrips;
	unsigned working_set_kib = 0;
	enum hint_policy policy = hint_continuous;
	enum sync_policy sync = sync_pipe;
	enum profile_policy profile = profile_plain;
	unsigned long before, after;

	if (argc > 8) {
		fprintf(stderr, "usage: %s [loops] [repeats] [continuous|continuous-unmatched|futex-early|seed|preseed] [warmup] [pipe|futex] [plain|legs] [working-set-kib]\n",
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
	if (profile == profile_legs && sync != sync_futex) {
		fputs("legs profile requires futex synchronization\n", stderr);
		return 2;
	}
	if (policy == hint_futex_early && sync != sync_futex) {
		fputs("futex-early policy requires futex synchronization\n", stderr);
		return 2;
	}
	before = prefix_status();
	printf("PIPE_HINT_CONFIG loops=%u repeats=%u warmup=%u configured_entries=%lu policy=%s sync=%s profile=%s working_set_kib=%u\n",
	       loops, repeats, warmup, (before >> 4) & 0x1ffUL,
	       policy == hint_continuous ? "continuous"
	       : policy == hint_continuous_unmatched ? "continuous-unmatched"
	       : policy == hint_futex_early ? "futex-early"
	       : policy == hint_seed_once ? "seed" : "preseed",
	       sync == sync_pipe ? "pipe" : "futex",
	       profile == profile_plain ? "plain" : "legs", working_set_kib);
	for (unsigned repeat = 0; repeat < repeats; ++repeat) {
		unsigned first = repeat & 1U;

		for (unsigned order = 0; order < 2; ++order) {
			unsigned enabled = first ^ order;
			struct cell_result result = sync == sync_pipe
				? run_pipe_cell(enabled, loops, warmup, policy,
						working_set_kib)
				: run_futex_cell(enabled, loops, warmup, policy,
						  profile, working_set_kib);

			printf("PIPE_HINT_RESULT repeat=%u order=%u enabled=%u cycles=%llu loops=%u\n",
			       repeat, order, enabled,
			       (unsigned long long)result.elapsed, loops);
			if (profile == profile_legs)
				printf("PIPE_HINT_LEGS repeat=%u order=%u enabled=%u child_resume=%llu parent_resume=%llu loops=%u\n",
				       repeat, order, enabled,
				       (unsigned long long)result.child_resume,
				       (unsigned long long)result.parent_resume,
				       loops);
			fflush(stdout);
		}
	}
	after = prefix_status();
	printf("PIPE_HINT_STATUS before=0x%016lx after=0x%016lx configured_entries=%lu dropped=%lu\n",
	       before, after, (after >> 4) & 0x1ffUL,
	       (after >> 46) & 0xffUL);
	puts("PIPE_HINT_PASS");
	return 0;
}
