#define _GNU_SOURCE

/* Measure the first four private data lines after a cross-process wakeup.
 * The child evicts its own target lines before blocking. A core-wide recorder
 * separates accepted demand misses from physical preview admissions/issues.
 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>

#if !defined(__riscv) || __riscv_xlen != 64
#error "This diagnostic requires RV64 BlackParrot"
#endif

#define PR_BP_PREVIEW_GET_COUNT 0x42505057
#define PR_BP_PREVIEW_PIN_SET 0x42505059

enum { trials = 16, lines = 4, line_bytes = 64, page_bytes = 4096,
	 eviction_pages = 10 };

#ifdef BP_PREVIEW_TRACE
enum { traced_trials = 3, max_publications = 8, max_removals = 16,
	 max_demand_records = 8 };

static inline uint64_t trace_record(unsigned dcache, unsigned index)
{
	const uint64_t selector = ((uint64_t)dcache << 8) | index;
	uint64_t value;

	__asm__ volatile("csrw 0x806, %1\n"
			 "nop\n"
			 "nop\n"
			 "nop\n"
			 "csrr %0, 0x807\n"
			 : "=r"(value) : "r"(selector) : "memory");
	return value;
}
#endif

static void fail(const char *what)
{
	perror(what);
	exit(1);
}

static void transfer(int fd, char *token, int send)
{
	ssize_t count = send ? write(fd, token, 1) : read(fd, token, 1);

	if (count != 1)
		fail(send ? "write pipe" : "read pipe");
}

static inline uint64_t cycle(void)
{
	uint64_t value;

	__asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
	return value;
}

static inline void trace_control(uint64_t value)
{
	__asm__ volatile("csrw 0x805, %0" : : "r"(value) : "memory");
}

static inline uint64_t trace_status(void)
{
	uint64_t value;

	__asm__ volatile("csrr %0, 0x805" : "=r"(value) : : "memory");
	return value;
}

static unsigned mode_for(unsigned trial)
{
	return (trial ^ (trial >> 1)) & 1;
}

static void child_run(int in, int out)
{
	volatile uint64_t *target = mmap(NULL, page_bytes, PROT_READ | PROT_WRITE,
					MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	volatile unsigned char *eviction = mmap(NULL, eviction_pages * page_bytes,
						PROT_READ | PROT_WRITE,
						MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	uint64_t target_addr[lines], measured[trials], status[trials];
	uint64_t entry_status[trials];
	unsigned demand_miss[trials], hook_delta[trials], mode[trials];
#ifdef BP_PREVIEW_TRACE
	uint64_t publications[traced_trials][max_publications];
	uint64_t removals[traced_trials][max_removals];
	uint64_t demands[traced_trials][max_demand_records];
	unsigned publication_count[traced_trials], removal_count[traced_trials];
	unsigned demand_count[traced_trials], preview_overflow[traced_trials];
#endif
	char token = 'x';
	unsigned trial, line, page, offset;

	if (target == MAP_FAILED || eviction == MAP_FAILED)
		fail("mmap");
	for (line = 0; line < lines; line++) {
		target_addr[line] = (uintptr_t)&target[line * line_bytes / 8];
		*(volatile uint64_t *)(uintptr_t)target_addr[line] =
			0x12340000UL + line;
	}
	for (page = 0; page < eviction_pages; page++)
		for (offset = 0; offset < page_bytes; offset += line_bytes)
			eviction[page * page_bytes + offset] = page + offset;
	for (trial = 0; trial < trials; trial++) {
		unsigned long before_hook, after_hook;
		uint64_t before, after, start, stop, sum = 0;
		unsigned enabled = mode_for(trial);

		mode[trial] = enabled;
		if (prctl(PR_BP_PREVIEW_PIN_SET,
			  enabled ? (unsigned long)target_addr[0] : 0UL,
			  enabled ? (unsigned long)target_addr[1] : 0UL,
			  enabled ? (unsigned long)target_addr[2] : 0UL,
			  enabled ? (unsigned long)target_addr[3] : 0UL))
			fail("register preview");
		before_hook = prctl(PR_BP_PREVIEW_GET_COUNT, 0UL, 0UL, 0UL, 0UL);
		if (before_hook == (unsigned long)-1)
			fail("hook count before");
		/* Every eviction page spans the target's four L1/L2 set offsets. */
		for (page = 0; page < eviction_pages; page++)
			for (offset = 0; offset < page_bytes; offset += line_bytes)
				sum += eviction[page * page_bytes + offset];
		__asm__ volatile("fence rw, rw" : : : "memory");
		if (sum == UINT64_MAX)
			fail("impossible eviction checksum");
#ifdef BP_PREVIEW_TRACE
		trace_control(6); /* trace publications/removals, not kernel demand */
#else
		trace_control(2); /* clear preview counters before the switch */
#endif
		transfer(out, &token, 1); /* ready; parent will then block on us */
		transfer(in, &token, 0);
		entry_status[trial] = trace_status();
#ifdef BP_PREVIEW_TRACE
		trace_control(5); /* arm demand without clearing preview history */
#else
		trace_control(3); /* count only the first four target loads */
#endif
		start = cycle();
		before = trace_status();
		for (line = 0; line < lines; line++) {
			uint64_t value = *(volatile uint64_t *)(uintptr_t)target_addr[line];

			if (value != 0x12340000UL + line) {
				fprintf(stderr, "wrong target: trial=%u line=%u value=%llu\n",
					trial, line, (unsigned long long)value);
				exit(1);
			}
		}
		after = trace_status();
		stop = cycle();
		status[trial] = after;
		measured[trial] = stop - start;
		demand_miss[trial] = ((after >> 9) & 0x1ff) - ((before >> 9) & 0x1ff);
#ifdef BP_PREVIEW_TRACE
		trace_control(4); /* stop demand, retain preview records */
		if (trial < traced_trials) {
			unsigned i;

			publication_count[trial] = (after >> 53) & 15;
			removal_count[trial] = (after >> 59) & 31;
			demand_count[trial] = (after >> 9) & 511;
			preview_overflow[trial] = (after >> 57) & 1;
			for (i = 0; i < publication_count[trial] && i < max_publications; i++)
				publications[trial][i] = trace_record(0, 248 + i);
			for (i = 0; i < removal_count[trial] && i < max_removals; i++)
				removals[trial][i] = trace_record(1, 232 + i);
			for (i = 0; i < demand_count[trial] && i < max_demand_records; i++)
				demands[trial][i] = trace_record(1, i);
		}
#else
		trace_control(0);
#endif
		after_hook = prctl(PR_BP_PREVIEW_GET_COUNT, 0UL, 0UL, 0UL, 0UL);
		if (after_hook == (unsigned long)-1)
			fail("hook count after");
		hook_delta[trial] = after_hook - before_hook;
		transfer(out, &token, 1);
	}
	if (prctl(PR_BP_PREVIEW_PIN_SET, 0UL, 0UL, 0UL, 0UL))
		fail("release preview");
	for (trial = 0; trial < trials; trial++) {
		uint64_t s = status[trial], e = entry_status[trial];
		unsigned pre_admitted = (e >> 29) & 255;
		unsigned pre_issued = (e >> 37) & 255;
		unsigned pre_published = (e >> 45) & 255;
#ifdef BP_PREVIEW_TRACE
		unsigned admitted = (s >> 29) & 255;
		unsigned issued = (s >> 37) & 255;
		unsigned published = (s >> 45) & 255;
#else
		unsigned admitted = pre_admitted + ((s >> 29) & 255);
		unsigned issued = pre_issued + ((s >> 37) & 255);
		unsigned published = pre_published + ((s >> 45) & 255);
#endif

		printf("PHYSICAL_MISS trial=%u mode=%u hooks=%u dmiss=%u load_cycles=%llu pre_admitted=%u pre_issued=%u pre_published=%u admitted=%u issued=%u published=%u overflow=%llu\n",
		       trial, mode[trial], hook_delta[trial], demand_miss[trial],
		       (unsigned long long)measured[trial],
		       pre_admitted, pre_issued, pre_published,
		       admitted, issued, published,
		       (unsigned long long)((s >> 19) & 1));
		if ((s >> 19) & 1) {
			fprintf(stderr, "demand trace overflow: trial=%u\n", trial);
			exit(1);
		}
#ifdef BP_PREVIEW_TRACE
		if (trial < traced_trials) {
			unsigned i;

			printf("PHYSICAL_TRACE_STATUS trial=%u publications=%u removals=%u demands=%u overflow=%u\n",
			       trial, publication_count[trial], removal_count[trial],
			       demand_count[trial], preview_overflow[trial]);
			for (i = 0; i < publication_count[trial] && i < max_publications; i++)
				printf("PHYSICAL_TRACE_PUBLISH trial=%u index=%u addr=0x%llx cycle=%u\n",
				       trial, i,
				       (unsigned long long)(publications[trial][i] & 0x3fffffff),
				       (unsigned)(publications[trial][i] >> 32));
			for (i = 0; i < removal_count[trial] && i < max_removals; i++)
				printf("PHYSICAL_TRACE_REMOVE trial=%u index=%u reason=%u addr=0x%llx cycle=%u\n",
				       trial, i, (unsigned)((removals[trial][i] >> 30) & 3),
				       (unsigned long long)(removals[trial][i] & 0x3fffffff),
				       (unsigned)(removals[trial][i] >> 32));
			for (i = 0; i < demand_count[trial] && i < max_demand_records; i++)
				printf("PHYSICAL_TRACE_DEMAND trial=%u index=%u addr=0x%llx cycle=%u\n",
				       trial, i,
				       (unsigned long long)(demands[trial][i] & 0xfffffff),
				       (unsigned)(demands[trial][i] >> 32));
		}
#endif
	}
	puts("PHYSICAL_MISS PASS");
}

int main(void)
{
	int to_child[2], to_parent[2], status;
	char token = 'x';
	pid_t child;
	unsigned trial;

	if (pipe(to_child) || pipe(to_parent))
		fail("pipe");
	child = fork();
	if (child < 0)
		fail("fork");
	if (!child) {
		close(to_child[1]);
		close(to_parent[0]);
		child_run(to_child[0], to_parent[1]);
		return 0;
	}
	close(to_child[0]);
	close(to_parent[1]);
	for (trial = 0; trial < trials; trial++) {
		transfer(to_parent[0], &token, 0);
		transfer(to_child[1], &token, 1);
		transfer(to_parent[0], &token, 0);
	}
	if (waitpid(child, &status, 0) != child)
		fail("waitpid");
	if (!WIFEXITED(status) || WEXITSTATUS(status)) {
		fprintf(stderr, "child failed: status=%d\n", status);
		return 1;
	}
	puts("PHYSICAL_MISS_PARENT PASS");
	return 0;
}
