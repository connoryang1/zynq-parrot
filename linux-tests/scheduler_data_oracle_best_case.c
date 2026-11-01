#define _GNU_SOURCE

/* Measure a completed-cache-state upper bound for cross-process wakeups.
 * The child displaces a 16- or 32-line target footprint, then blocks. The
 * parent touches either those exact shared physical lines (oracle) or an
 * equal-sized decoy (cold control) before starting the handoff timer.
 */
#include <errno.h>
#include <inttypes.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

#if !defined(__riscv) || __riscv_xlen != 64
#error "This benchmark requires RV64 BlackParrot"
#endif

enum {
	warmups = 8,
	measured_trials = 128,
	trials = warmups + measured_trials,
	page_bytes = 4096,
	line_bytes = 64,
	max_lines = 32,
	eviction_bytes = 256 * 1024,
	conditions = 4,
};

enum shape { independent, dependent };

struct condition {
	unsigned lines;
	enum shape shape;
	const char *name;
};

static const struct condition condition[conditions] = {
	{16, independent, "independent"},
	{16, dependent, "dependent"},
	{32, independent, "independent"},
	{32, dependent, "dependent"},
};

struct sample {
	uint64_t oracle_begin;
	uint64_t launch;
	uint64_t entry;
	uint64_t after_load;
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
	static const unsigned balanced[4] = {0, 1, 1, 0};

	return balanced[trial & 3];
}

static volatile uint64_t *line_word(volatile unsigned char *base,
				    unsigned line, unsigned word)
{
	/* Rotate page offsets so one-line-per-page does not collapse into one set. */
	unsigned offset = (line * line_bytes) & (page_bytes - 1);

	return (volatile uint64_t *)(base + line * page_bytes + offset
				       + word * sizeof(uint64_t));
}

static uint64_t expected_sum(unsigned lines)
{
	uint64_t sum = 0;

	for (unsigned line = 0; line < lines; line++)
		sum += UINT64_C(0x12340000) + line;
	return sum;
}

static uint64_t touch_footprint(volatile unsigned char *base,
				const struct condition *cfg)
{
	uint64_t sum = 0;

	if (cfg->shape == independent) {
		for (unsigned line = 0; line < cfg->lines; line++)
			sum += *line_word(base, line, 1);
	} else {
		unsigned line = 0;
		unsigned next_word = cfg->lines == 16 ? 0 : 2;

		for (unsigned step = 0; step < cfg->lines; step++) {
			sum += *line_word(base, line, 1);
			line = (unsigned)*line_word(base, line, next_word);
		}
		if (line != 0)
			fail("dependent chain termination");
	}
	return sum;
}

static long minor_faults(void)
{
	struct rusage usage;

	if (getrusage(RUSAGE_SELF, &usage))
		fail("getrusage");
	return usage.ru_minflt;
}

static void initialize_footprint(volatile unsigned char *base)
{
	for (unsigned line = 0; line < max_lines; line++) {
		*line_word(base, line, 0) = (line + 1) % 16;
		*line_word(base, line, 1) = UINT64_C(0x12340000) + line;
		*line_word(base, line, 2) = (line + 1) % max_lines;
	}
}

static void child_run(int in, int out, volatile struct sample *samples,
		      volatile unsigned char *target)
{
	volatile unsigned char *eviction = mmap(NULL, eviction_bytes,
						PROT_READ | PROT_WRITE,
						MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	char token = 'x';

	if (eviction == MAP_FAILED)
		fail("mmap eviction");
	pin_cpu0();
	/* MAP_SHARED pages can still lack child PTEs after fork even when the
	 * parent populated them.  Establish every result mapping here too.
	 */
	for (size_t sample = 0; sample < conditions * trials; sample++)
		samples[sample].entry = 0;
	for (unsigned offset = 0; offset < eviction_bytes; offset += line_bytes)
		eviction[offset] = (unsigned char)(offset / line_bytes);

	for (unsigned c = 0; c < conditions; c++) {
		long measured_fault_start = 0;

		for (unsigned trial = 0; trial < trials; trial++) {
			uint64_t checksum = 0;
			uint64_t value;

			for (unsigned offset = 0; offset < eviction_bytes;
			     offset += line_bytes)
				checksum += eviction[offset];
			__asm__ volatile("fence rw, rw" : : : "memory");
			if (checksum == UINT64_MAX)
				fail("eviction checksum");
			transfer(out, &token, 1);
			transfer(in, &token, 0);
			samples[c * trials + trial].entry = cycle();
			value = touch_footprint(target, &condition[c]);
			samples[c * trials + trial].after_load = cycle();
			if (value != expected_sum(condition[c].lines))
				fail("target checksum");
			sink += value;
			transfer(out, &token, 1);
			if (trial + 1 == warmups)
				measured_fault_start = minor_faults();
		}
		printf("DATA_ORACLE_FAULTS footprint=%u shape=%s faults=%ld\n",
		       condition[c].lines, condition[c].name,
		       minor_faults() - measured_fault_start);
	}
	puts("DATA_ORACLE_CHILD PASS");
}

int main(void)
{
	const size_t footprint_bytes = max_lines * page_bytes;
	const size_t sample_count = conditions * trials;
	volatile struct sample *samples = mmap(NULL,
					      sample_count * sizeof(*samples),
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
	/* The child writes every result page after fork.  Fault them in now so
	 * result bookkeeping cannot masquerade as a target-footprint miss.
	 */
	for (size_t sample = 0; sample < sample_count; sample++)
		samples[sample].entry = 0;
	initialize_footprint(target);
	initialize_footprint(decoy);
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

	for (unsigned c = 0; c < conditions; c++) {
		for (unsigned trial = 0; trial < trials; trial++) {
			volatile struct sample *sample = &samples[c * trials + trial];
			unsigned mode = mode_for(trial);
			uint64_t value;

			transfer(to_parent[0], &token, 0);
			sample->mode = mode;
			sample->oracle_begin = cycle();
			value = touch_footprint(mode ? target : decoy, &condition[c]);
			__asm__ volatile("fence rw, rw" : : : "memory");
			sink += value;
			sample->launch = cycle();
			transfer(to_child[1], &token, 1);
			transfer(to_parent[0], &token, 0);
			sample->returned = cycle();
		}
	}

	if (waitpid(child, &status, 0) != child)
		fail("waitpid");
	if (!WIFEXITED(status) || WEXITSTATUS(status)) {
		fprintf(stderr, "child failed: status=%d\n", status);
		return 1;
	}

	for (unsigned c = 0; c < conditions; c++) {
		for (unsigned trial = warmups; trial < trials; trial++) {
			const volatile struct sample *sample =
				&samples[c * trials + trial];

			if (!(sample->oracle_begin <= sample->launch
			      && sample->launch <= sample->entry
			      && sample->entry <= sample->after_load
			      && sample->after_load <= sample->returned)) {
				fprintf(stderr, "nonmonotonic sample: condition=%u trial=%u\n",
					c, trial);
				return 1;
			}
			printf("DATA_ORACLE trial=%u footprint=%u shape=%s mode=%u oracle_cost=%" PRIu64
			       " wake_to_entry=%" PRIu64 " load_cycles=%" PRIu64
			       " wake_to_load=%" PRIu64 " roundtrip=%" PRIu64 "\n",
			       trial - warmups, condition[c].lines, condition[c].name,
			       sample->mode, sample->launch - sample->oracle_begin,
			       sample->entry - sample->launch,
			       sample->after_load - sample->entry,
			       sample->after_load - sample->launch,
			       sample->returned - sample->launch);
		}
	}
	if (!sink) {
		puts("DATA_ORACLE_PARENT FAIL sink");
		return 1;
	}
	puts("DATA_ORACLE_PARENT PASS");
	return 0;
}
