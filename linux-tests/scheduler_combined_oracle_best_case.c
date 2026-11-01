#define _GNU_SOURCE

/* Measure completed instruction/data cache-state upper bounds across a
 * cross-process wakeup. The child evicts both target footprints and blocks;
 * the parent warms matched target or decoy state before starting the timer.
 */
#include <inttypes.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

#if !defined(__riscv) || __riscv_xlen != 64
#error "This benchmark requires RV64 BlackParrot"
#endif

enum {
	warmups = 8,
	measured_trials = 256,
	trials = warmups + measured_trials,
	page_bytes = 4096,
	line_bytes = 64,
	data_lines = 32,
	data_eviction_bytes = 256 * 1024,
	mode_instruction = 1,
	mode_data = 2,
};

/* Target and decoy each occupy exactly 32 64-byte lines. The eviction body
 * occupies 576 lines: nine complete ways across every set of the 64-set,
 * eight-way 32 KiB instruction cache. All bodies are branch-free so target
 * execution cannot train a branch predictor that the decoy arm does not.
 */
__asm__(
".pushsection .text.oracle,\"ax\",@progbits\n"
".option push\n"
".option norvc\n"
".balign 64\n"
".global instruction_target\n"
".hidden instruction_target\n"
".type instruction_target,@function\n"
"instruction_target:\n"
".rept 511\n"
"addi x0,x0,0\n"
".endr\n"
"ret\n"
".size instruction_target,.-instruction_target\n"
".balign 64\n"
".global instruction_decoy\n"
".hidden instruction_decoy\n"
".type instruction_decoy,@function\n"
"instruction_decoy:\n"
".rept 511\n"
"addi x0,x0,0\n"
".endr\n"
"ret\n"
".size instruction_decoy,.-instruction_decoy\n"
".balign 64\n"
".global instruction_evict\n"
".hidden instruction_evict\n"
".type instruction_evict,@function\n"
"instruction_evict:\n"
".rept 9215\n"
"addi x0,x0,0\n"
".endr\n"
"ret\n"
".size instruction_evict,.-instruction_evict\n"
".option pop\n"
".popsection\n");

extern void instruction_target(void);
extern void instruction_decoy(void);
extern void instruction_evict(void);

struct sample {
	uint64_t prep_begin;
	uint64_t launch;
	uint64_t entry;
	uint64_t code_end;
	uint64_t data_end;
	uint64_t returned;
	unsigned mode;
};

static volatile uint64_t sink;

static inline uint64_t cycle(void)
{
	uint64_t value;

	__asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
	return value;
}

static void fail(const char *what)
{
	perror(what);
	exit(1);
}

static void pin_cpu0(void)
{
	cpu_set_t set;

	CPU_ZERO(&set);
	CPU_SET(0, &set);
	if (sched_setaffinity(0, sizeof(set), &set))
		fail("sched_setaffinity");
}

static void transfer(int fd, char *token, int send)
{
	ssize_t count = send ? write(fd, token, 1) : read(fd, token, 1);

	if (count != 1)
		fail(send ? "write pipe" : "read pipe");
}

static unsigned mode_for(unsigned trial)
{
	/* Every eight-trial block contains each mode twice in mirrored order.
	 * Rotate labels across blocks so periodic scheduler behavior cannot stay
	 * correlated with one cache-state mode.
	 */
	static const unsigned balanced[8] = {0, 3, 1, 2, 2, 1, 3, 0};

	return (balanced[trial & 7] + (trial >> 3)) & 3;
}

static volatile uint64_t *line_word(volatile unsigned char *base,
				    unsigned line, unsigned word)
{
	unsigned offset = (line * line_bytes) & (page_bytes - 1);

	return (volatile uint64_t *)(base + line * page_bytes + offset
				       + word * sizeof(uint64_t));
}

static uint64_t expected_sum(void)
{
	uint64_t sum = 0;

	for (unsigned line = 0; line < data_lines; line++)
		sum += UINT64_C(0x12340000) + line;
	return sum;
}

static uint64_t touch_data(volatile unsigned char *base)
{
	uint64_t sum = 0;
	unsigned line = 0;

	for (unsigned step = 0; step < data_lines; step++) {
		sum += *line_word(base, line, 1);
		line = (unsigned)*line_word(base, line, 0);
	}
	if (line != 0)
		fail("dependent chain termination");
	return sum;
}

static void initialize_data(volatile unsigned char *base)
{
	for (unsigned line = 0; line < data_lines; line++) {
		*line_word(base, line, 0) = (line + 1) % data_lines;
		*line_word(base, line, 1) = UINT64_C(0x12340000) + line;
	}
}

static long minor_faults(void)
{
	struct rusage usage;

	if (getrusage(RUSAGE_SELF, &usage))
		fail("getrusage");
	return usage.ru_minflt;
}

static void child_run(int in, int out, volatile struct sample *samples,
		      volatile unsigned char *target)
{
	volatile unsigned char *eviction = mmap(NULL, data_eviction_bytes,
						PROT_READ | PROT_WRITE,
						MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	char token = 'x';
	long measured_fault_start = 0;

	if (eviction == MAP_FAILED)
		fail("mmap eviction");
	pin_cpu0();
	for (unsigned trial = 0; trial < trials; trial++)
		samples[trial].entry = 0;
	for (unsigned offset = 0; offset < data_eviction_bytes; offset += line_bytes)
		eviction[offset] = (unsigned char)(offset / line_bytes);

	for (unsigned trial = 0; trial < trials; trial++) {
		uint64_t checksum = 0;
		uint64_t value;

		instruction_evict();
		for (unsigned offset = 0; offset < data_eviction_bytes;
		     offset += line_bytes)
			checksum += eviction[offset];
		__asm__ volatile("fence rw, rw" : : : "memory");
		if (checksum == UINT64_MAX)
			fail("eviction checksum");
		transfer(out, &token, 1);
		transfer(in, &token, 0);
		samples[trial].entry = cycle();
		instruction_target();
		samples[trial].code_end = cycle();
		value = touch_data(target);
		samples[trial].data_end = cycle();
		if (value != expected_sum())
			fail("target checksum");
		sink += value;
		transfer(out, &token, 1);
		if (trial + 1 == warmups)
			measured_fault_start = minor_faults();
	}
	printf("COMBINED_ORACLE_FAULTS faults=%ld\n",
	       minor_faults() - measured_fault_start);
	puts("COMBINED_ORACLE_CHILD PASS");
}

int main(void)
{
	const size_t footprint_bytes = data_lines * page_bytes;
	volatile struct sample *samples = mmap(NULL, trials * sizeof(*samples),
					      PROT_READ | PROT_WRITE,
					      MAP_SHARED | MAP_ANONYMOUS, -1, 0);
	volatile unsigned char *target = mmap(NULL, footprint_bytes,
					     PROT_READ | PROT_WRITE,
					     MAP_SHARED | MAP_ANONYMOUS, -1, 0);
	volatile unsigned char *decoy = mmap(NULL, footprint_bytes,
					    PROT_READ | PROT_WRITE,
					    MAP_SHARED | MAP_ANONYMOUS, -1, 0);
	int to_child[2], to_parent[2], status;
	char token = 'x';
	pid_t child;

	if (samples == MAP_FAILED || target == MAP_FAILED || decoy == MAP_FAILED
	    || pipe(to_child) || pipe(to_parent))
		fail("shared memory or pipes");
	pin_cpu0();
	for (unsigned trial = 0; trial < trials; trial++)
		samples[trial].entry = 0;
	initialize_data(target);
	initialize_data(decoy);
	__asm__ volatile("fence rw, rw" : : : "memory");

	child = fork();
	if (child < 0)
		fail("fork");
	if (!child) {
		close(to_child[1]);
		close(to_parent[0]);
		child_run(to_child[0], to_parent[1], samples, target);
		return 0;
	}
	close(to_child[0]);
	close(to_parent[1]);

	for (unsigned trial = 0; trial < trials; trial++) {
		volatile struct sample *sample = &samples[trial];
		unsigned mode = mode_for(trial);
		uint64_t value;

		transfer(to_parent[0], &token, 0);
		sample->mode = mode;
		sample->prep_begin = cycle();
		if (mode & mode_instruction)
			instruction_target();
		else
			instruction_decoy();
		value = touch_data((mode & mode_data) ? target : decoy);
		__asm__ volatile("fence rw, rw" : : : "memory");
		sink += value;
		sample->launch = cycle();
		transfer(to_child[1], &token, 1);
		transfer(to_parent[0], &token, 0);
		sample->returned = cycle();
	}

	if (waitpid(child, &status, 0) != child)
		fail("waitpid");
	if (!WIFEXITED(status) || WEXITSTATUS(status)) {
		fprintf(stderr, "child failed: status=%d\n", status);
		return 1;
	}
	if (!sink) {
		fputs("COMBINED_ORACLE_PARENT FAIL sink\n", stderr);
		return 1;
	}

	for (unsigned trial = warmups; trial < trials; trial++) {
		const volatile struct sample *sample = &samples[trial];
		uint64_t code_cycles, data_cycles, useful_cycles;

		if (!(sample->prep_begin <= sample->launch
		      && sample->launch <= sample->entry
		      && sample->entry <= sample->code_end
		      && sample->code_end <= sample->data_end
		      && sample->data_end <= sample->returned)) {
			fprintf(stderr, "nonmonotonic sample: trial=%u\n", trial);
			return 1;
		}
		code_cycles = sample->code_end - sample->entry;
		data_cycles = sample->data_end - sample->code_end;
		useful_cycles = sample->data_end - sample->entry;
		printf("COMBINED_ORACLE trial=%u mode=%u prep_cost=%" PRIu64
		       " wake_to_entry=%" PRIu64 " code_cycles=%" PRIu64
		       " data_cycles=%" PRIu64 " useful_cycles=%" PRIu64
		       " wake_to_useful=%" PRIu64 " roundtrip=%" PRIu64 "\n",
		       trial - warmups, sample->mode,
		       sample->launch - sample->prep_begin,
		       sample->entry - sample->launch, code_cycles, data_cycles,
		       useful_cycles, sample->data_end - sample->launch,
		       sample->returned - sample->launch);
	}
	puts("COMBINED_ORACLE_PARENT PASS");
	return 0;
}
