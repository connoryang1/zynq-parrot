#define _GNU_SOURCE

/* Capture physical cache misses across the exact pipe handoff used by the
 * scheduler physical-preview benchmark. The first 16 handoffs warm the code
 * path with preview disabled. On the final handoff the parent arms the miss
 * recorder immediately before waking the child, optionally with prefix replay
 * enabled for that child, and the child disarms it immediately after the same
 * four dependent first-use loads.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>

#if !defined(__riscv) || __riscv_xlen != 64
#error "This capture requires RV64 BlackParrot"
#endif

#define PR_BP_PREVIEW_GET_COUNT 0x42505057
#define PR_BP_PREVIEW_PIN_SET 0x42505059
#define PR_BP_PREVIEW_ENABLE 0x4250505a

enum {
	warmup = 16,
	trials = warmup + 1,
	lines = 4,
	line_bytes = 64,
	page_bytes = 4096,
	eviction_pages = 10,
	trace_depth = 256,
};

enum replay_mode {
	replay_disabled = 0,
	replay_wake_early_data = 1,
	replay_trigger = 5,
	replay_wake_trigger = 6,
};

struct sample {
	uint64_t trace_start, launch, entry, after_load, returned, status;
	unsigned hooks;
};

static uint64_t icache_records[trace_depth];
static uint64_t dcache_records[trace_depth];

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

static inline uint64_t trace_record(unsigned dcache, unsigned index)
{
	uint64_t value;
	const uint64_t selector = ((uint64_t)dcache << 8) | index;

	__asm__ volatile(
		"csrw 0x806, %1\n"
		"nop\n"
		"nop\n"
		"nop\n"
		"csrr %0, 0x807\n"
		: "=r"(value) : "r"(selector) : "memory");
	return value;
}

static void fail(const char *what)
{
	perror(what);
	exit(EXIT_FAILURE);
}

static void transfer(int fd, char *token, int send)
{
	ssize_t count = send ? write(fd, token, 1) : read(fd, token, 1);

	if (count != 1)
		fail(send ? "write pipe" : "read pipe");
}

static uint32_t record_cycle(uint64_t record)
{
	return (uint32_t)(record >> 32);
}

static void print_record(unsigned sequence, char side, unsigned index,
			 uint64_t record, uint32_t start_cycle)
{
	const uint32_t record_at = record_cycle(record);
	const uint32_t relative = record_at - start_cycle;
	const unsigned message = (unsigned)((record >> 28) & 0xf);
	const uint64_t line = record & UINT64_C(0x0fffffff);

	printf("TRACE_RECORD seq=%u side=%c index=%u cycle=%" PRIu32
	       " relative=%" PRIu32 " message=0x%x paddr=0x%09" PRIx64
	       " raw=0x%016" PRIx64 "\n",
	       sequence, side, index, record_at, relative, message, line << 6,
	       record);
}

static int emit_trace(const volatile struct sample *sample, unsigned group)
{
	const uint64_t status = sample->status;
	const unsigned icount = (unsigned)(status & UINT64_C(0x1ff));
	const unsigned dcount = (unsigned)((status >> 9) & UINT64_C(0x1ff));
	const unsigned ioverflow = (unsigned)((status >> 18) & 1);
	const unsigned doverflow = (unsigned)((status >> 19) & 1);
	const unsigned armed = (unsigned)((status >> 20) & 1);

	printf("TRACE_HEADER path=pipe group=%u warmups=%u start=%" PRIu64
	       " launch=%" PRIu64 " entry=%" PRIu64 " after_load=%" PRIu64
	       " returned=%" PRIu64 " wake_to_entry=%" PRIu64
	       " load_cycles=%" PRIu64 " wake_to_load=%" PRIu64
	       " i_count=%u d_count=%u i_overflow=%u d_overflow=%u"
	       " armed=%u status=0x%016" PRIx64 "\n",
	       group, warmup, sample->trace_start, sample->launch, sample->entry,
	       sample->after_load, sample->returned,
	       sample->entry - sample->launch,
	       sample->after_load - sample->entry,
	       sample->after_load - sample->launch,
	       icount, dcount, ioverflow, doverflow, armed, status);
	if (armed || ioverflow || doverflow || icount > trace_depth ||
	    dcount > trace_depth || icount + dcount == 0) {
		fputs("TRACE_FAIL invalid recorder status\n", stderr);
		return EXIT_FAILURE;
	}

	for (unsigned index = 0; index < icount; ++index)
		icache_records[index] = trace_record(0, index);
	for (unsigned index = 0; index < dcount; ++index)
		dcache_records[index] = trace_record(1, index);

	unsigned ii = 0, di = 0, sequence = 0;
	const uint32_t start32 = (uint32_t)sample->trace_start;
	while (ii < icount || di < dcount) {
		const uint32_t irelative = ii < icount
			? record_cycle(icache_records[ii]) - start32 : UINT32_MAX;
		const uint32_t drelative = di < dcount
			? record_cycle(dcache_records[di]) - start32 : UINT32_MAX;

		if (irelative <= drelative) {
			print_record(sequence++, 'I', ii, icache_records[ii], start32);
			++ii;
		} else {
			print_record(sequence++, 'D', di, dcache_records[di], start32);
			++di;
		}
	}
	printf("TRACE_PASS records=%u elapsed=%" PRIu64 "\n",
	       icount + dcount, sample->after_load - sample->trace_start);
	return EXIT_SUCCESS;
}

static void child_run(int in, int out, volatile struct sample *samples,
		      unsigned group, enum replay_mode replay)
{
	volatile unsigned char *target = mmap(NULL, page_bytes,
					       PROT_READ | PROT_WRITE,
					       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	volatile unsigned char *eviction = mmap(NULL, eviction_pages * page_bytes,
						 PROT_READ | PROT_WRITE,
						 MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	unsigned long target_addr[lines];
	const unsigned target_offset = group * 4 * line_bytes;
	char token = 'x';

	if (target == MAP_FAILED || eviction == MAP_FAILED)
		fail("mmap child pages");
	for (unsigned line = 0; line < lines; ++line)
		target_addr[line] = (unsigned long)&target[target_offset
							     + line * line_bytes];
	for (unsigned line = 0; line < lines; ++line)
		*(volatile unsigned long *)target_addr[line]
			= target_addr[(line + 1) % lines];
	for (unsigned page = 0; page < eviction_pages; ++page)
		for (unsigned offset = 0; offset < page_bytes; offset += line_bytes)
			eviction[page * page_bytes + offset] = page + offset;
	if (prctl(PR_BP_PREVIEW_PIN_SET, target_addr[0], target_addr[1],
		  target_addr[2], target_addr[3]))
		fail("register preview lines");
	for (unsigned line = 0; line < lines; ++line)
		printf("TRACE_TARGET line=%u vaddr=0x%lx\n", line,
		       target_addr[line]);

	for (unsigned trial = 0; trial < trials; ++trial) {
		unsigned long before_hook, after_hook;
		uint64_t checksum = 0;
		unsigned long node;

		for (unsigned page = 0; page < eviction_pages; ++page)
			for (unsigned offset = 0; offset < page_bytes;
			     offset += line_bytes)
				checksum += eviction[page * page_bytes + offset];
		__asm__ volatile("fence rw, rw" : : : "memory");
		if (checksum == UINT64_MAX)
			fail("eviction checksum");
		const unsigned long trial_mode = trial == warmup ? replay : 0;
		if (prctl(PR_BP_PREVIEW_ENABLE, trial_mode, 0UL, 0UL, 0UL))
			fail(trial_mode ? "enable prefix replay" :
			     "disable preview emission");
		before_hook = prctl(PR_BP_PREVIEW_GET_COUNT, 0UL, 0UL, 0UL, 0UL);
		if (before_hook == (unsigned long)-1)
			fail("hook count before");
		transfer(out, &token, 1);
		transfer(in, &token, 0);
		samples[trial].entry = cycle();
		node = target_addr[0];
		for (unsigned line = 0; line < lines; ++line)
			node = *(volatile unsigned long *)node;
		samples[trial].after_load = cycle();
		if (trial == warmup) {
			trace_control(0);
			__asm__ volatile("nop\nnop\nnop" : : : "memory");
			samples[trial].status = trace_status();
		}
		if (node != target_addr[0])
			fail("target checksum");
		after_hook = prctl(PR_BP_PREVIEW_GET_COUNT, 0UL, 0UL, 0UL, 0UL);
		if (after_hook == (unsigned long)-1)
			fail("hook count after");
		samples[trial].hooks = after_hook - before_hook;
		const unsigned expected_hooks =
			trial_mode == replay_wake_early_data ? 1 : 0;
		if (samples[trial].hooks != expected_hooks) {
			fprintf(stderr,
				"TRACE_FAIL preview hook delta=%u expected=%u\n",
				samples[trial].hooks, expected_hooks);
			exit(EXIT_FAILURE);
		}
		if (trial_mode &&
		    prctl(PR_BP_PREVIEW_ENABLE, 0UL, 0UL, 0UL, 0UL))
			fail("disable prefix replay after capture");
		transfer(out, &token, 1);
	}
	if (prctl(PR_BP_PREVIEW_PIN_SET, 0UL, 0UL, 0UL, 0UL))
		fail("release preview");
}

int main(int argc, char **argv)
{
	int to_child[2], to_parent[2], status;
	unsigned group = 0;
	enum replay_mode replay = replay_disabled;
	volatile struct sample *samples = mmap(NULL, sizeof(struct sample) * trials,
						 PROT_READ | PROT_WRITE,
						 MAP_SHARED | MAP_ANONYMOUS, -1, 0);
	char token = 'x';
	pid_t child;

	if (argc > 3 || (argc >= 2 &&
	    (argv[1][0] < '0' || argv[1][0] > '7' || argv[1][1]))) {
		fprintf(stderr,
			"usage: %s [l2-set-group-0..7] [disabled|wake-early-data|trigger|wake-trigger]\n",
			argv[0]);
		return 2;
	}
	if (argc >= 2)
		group = (unsigned)(argv[1][0] - '0');
	if (argc == 3) {
		if (!strcmp(argv[2], "wake-early-data"))
			replay = replay_wake_early_data;
		else if (!strcmp(argv[2], "trigger"))
			replay = replay_trigger;
		else if (!strcmp(argv[2], "wake-trigger"))
			replay = replay_wake_trigger;
		else if (strcmp(argv[2], "disabled")) {
			fprintf(stderr,
				"usage: %s [l2-set-group-0..7] [disabled|wake-early-data|trigger|wake-trigger]\n",
				argv[0]);
			return 2;
		}
	}
	printf("TRACE_CONFIG path=pipe group=%u first_offset=%u lines=%u warmups=%u replay=%s mode=%u\n",
	       group, group * 4 * line_bytes, lines, warmup,
	       replay == replay_wake_early_data ? "wake-early-data" :
	       replay == replay_trigger ? "trigger" :
	       replay == replay_wake_trigger ? "wake-trigger" : "disabled",
	       replay);
	fflush(stdout);

	if (samples == MAP_FAILED || pipe(to_child) || pipe(to_parent))
		fail("shared memory or pipes");
	child = fork();
	if (child < 0)
		fail("fork");
	if (!child) {
		close(to_child[1]);
		close(to_parent[0]);
		child_run(to_child[0], to_parent[1], samples, group, replay);
		return 0;
	}
	close(to_child[0]);
	close(to_parent[1]);
	for (unsigned trial = 0; trial < trials; ++trial) {
		transfer(to_parent[0], &token, 0);
		if (trial == warmup) {
			trace_control(2);
			samples[trial].trace_start = cycle();
			trace_control(3);
		}
		samples[trial].launch = cycle();
		__asm__ volatile("fence rw, rw" : : : "memory");
		transfer(to_child[1], &token, 1);
		transfer(to_parent[0], &token, 0);
		samples[trial].returned = cycle();
	}
	if (waitpid(child, &status, 0) != child)
		fail("waitpid");
	if (!WIFEXITED(status) || WEXITSTATUS(status)) {
		fprintf(stderr, "child failed: status=%d\n", status);
		return EXIT_FAILURE;
	}
	if (!(samples[warmup].launch <= samples[warmup].entry &&
	      samples[warmup].entry <= samples[warmup].after_load &&
	      samples[warmup].after_load <= samples[warmup].returned)) {
		fputs("TRACE_FAIL nonmonotonic cycle sample\n", stderr);
		return EXIT_FAILURE;
	}
	return emit_trace(&samples[warmup], group);
}
