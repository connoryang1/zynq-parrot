#define _GNU_SOURCE

/* SPDX-License-Identifier: GPL-2.0
 *
 * Measure sustained two-process pipe ping-pong with either continuous or
 * one-time-seed instruction-prefix hints. The loop shape is derived from Linux
 * perf's tools/perf/bench/sched-pipe.c, which in turn is based on Ingo Molnar's
 * pipe-test-1m.c. Setup and fork are outside timing; both arms execute the same
 * prctl before each wake, and argument zero is the disabled no-op.
 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>

#if !defined(__riscv) || __riscv_xlen != 64
#error "This benchmark requires RV64 BlackParrot"
#endif

#define PR_BP_PREVIEW_ICACHE_STATUS 0x4250505e
#define PR_BP_PREVIEW_ICACHE_TRIGGER 0x4250505f

enum {
	default_loops = 512,
	default_repeats = 8,
	warmup_roundtrips = 32,
};

enum hint_policy {
	hint_continuous,
	hint_seed_once,
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

static enum hint_policy parse_policy(const char *text)
{
	if (!strcmp(text, "continuous"))
		return hint_continuous;
	if (!strcmp(text, "seed"))
		return hint_seed_once;
	fprintf(stderr, "policy must be continuous or seed\n");
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
	issue_hint(enabled && (policy == hint_continuous || iteration == 0));
}

static uint64_t run_cell(unsigned enabled, unsigned loops,
			 enum hint_policy policy)
{
	int to_child[2], to_parent[2], ready[2];
	unsigned char token = 0;
	uint64_t begin, end;
	pid_t child;
	int status;

	if (pipe(to_child) || pipe(to_parent) || pipe(ready))
		fail("pipe");
	child = fork();
	if (child < 0)
		fail("fork");
	if (!child) {
		close(to_child[1]);
		close(to_parent[0]);
		close(ready[0]);
		flush_instruction_state();
		transfer(ready[1], &token, 1);
		for (unsigned i = 0; i < warmup_roundtrips + loops; ++i) {
			transfer(to_child[0], &token, 0);
			issue_iteration_hint(enabled, policy, i);
			transfer(to_parent[1], &token, 1);
		}
		_exit(0);
	}

	close(to_child[0]);
	close(to_parent[1]);
	close(ready[1]);
	transfer(ready[0], &token, 0);
	flush_instruction_state();
	for (unsigned i = 0; i < warmup_roundtrips; ++i) {
		issue_iteration_hint(enabled, policy, i);
		transfer(to_child[1], &token, 1);
		transfer(to_parent[0], &token, 0);
	}
	begin = cycle();
	for (unsigned i = 0; i < loops; ++i) {
		issue_iteration_hint(enabled, policy, warmup_roundtrips + i);
		transfer(to_child[1], &token, 1);
		transfer(to_parent[0], &token, 0);
	}
	end = cycle();
	if (waitpid(child, &status, 0) != child || !WIFEXITED(status)
	    || WEXITSTATUS(status)) {
		fputs("pipe child failed\n", stderr);
		exit(1);
	}
	return end - begin;
}

int main(int argc, char **argv)
{
	unsigned loops = default_loops;
	unsigned repeats = default_repeats;
	enum hint_policy policy = hint_continuous;
	unsigned long before, after;

	if (argc > 4) {
		fprintf(stderr, "usage: %s [loops] [repeats] [continuous|seed]\n",
			argv[0]);
		return 2;
	}
	if (argc > 1)
		loops = parse_positive(argv[1], "loops");
	if (argc > 2)
		repeats = parse_positive(argv[2], "repeats");
	if (argc > 3)
		policy = parse_policy(argv[3]);
	before = prefix_status();
	printf("PIPE_HINT_CONFIG loops=%u repeats=%u warmup=%u configured_entries=%lu policy=%s\n",
	       loops, repeats, warmup_roundtrips, (before >> 4) & 0x1ffUL,
	       policy == hint_continuous ? "continuous" : "seed");
	for (unsigned repeat = 0; repeat < repeats; ++repeat) {
		unsigned first = repeat & 1U;

		for (unsigned order = 0; order < 2; ++order) {
			unsigned enabled = first ^ order;
			uint64_t elapsed = run_cell(enabled, loops, policy);

			printf("PIPE_HINT_RESULT repeat=%u order=%u enabled=%u cycles=%llu loops=%u\n",
			       repeat, order, enabled,
			       (unsigned long long)elapsed, loops);
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
