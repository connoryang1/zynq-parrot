#define _GNU_SOURCE

/* Measure a best-case Linux handoff with one tagged data replay.
 * Both arms retain identical pins and hardware footprint configuration; only
 * the successful-wakeup trigger mode changes. Four page-aligned bases expand
 * to a configurable number of cache lines, and a dependent pointer ring
 * exposes first use.
 */
#include <errno.h>
#include <stdint.h>
#include <sched.h>
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

#define PR_BP_PREVIEW_GET_COUNT 0x42505057
#define PR_BP_PREVIEW_PIN_SET 0x42505059
#define PR_BP_PREVIEW_ENABLE 0x4250505a
#define PR_BP_PREVIEW_GET_HOOK_CYCLES 0x4250505b
#define PR_BP_PREVIEW_REPLAY_CONFIG 0x4250505c
#define PR_BP_PREVIEW_REPLAY_STATUS 0x4250505d
#define BP_REPLAY_DRAIN_MASK (0xfUL | (7UL << 60))

enum {
	warmup = 16,
	measured_trials = 512,
	trials = warmup + measured_trials,
	page_bytes = 4096,
	line_bytes = 64,
	bases = 4,
	max_lines_per_base = 8,
	max_replay_lines = bases * max_lines_per_base,
	eviction_pages = 16,
	replay_slot = 2,
	max_retries = 4096,
};

struct sample {
	uint64_t launch, entry, after_load, done, returned;
	uint64_t preblock_status;
	uint64_t entry_probe_status;
	unsigned long hook_cycles;
	unsigned long preblock_probe_cycles;
	unsigned long entry_probe_cycles;
	unsigned accepted_entries, filtered_entries, accepted_triggers, dropped_triggers;
	unsigned hooks, enabled, accepted;
};

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

static void transfer(int fd, char *token, int send)
{
	ssize_t count = send ? write(fd, token, 1) : read(fd, token, 1);

	if (count != 1)
		fail(send ? "write pipe" : "read pipe");
}

static unsigned trial_enabled(unsigned trial)
{
	/* Alternate block polarity so a four-trial scheduler phase cannot alias
	 * into the enabled arm. Each block remains balanced and drift-resistant.
	 */
	return ((trial ^ (trial >> 1)) & 1) ^ ((trial >> 2) & 1);
}

static void child_run(int in, int out, volatile struct sample *samples,
		      unsigned mode, unsigned delay, unsigned gap,
		      unsigned lines_per_base, int probe_status)
{
	volatile unsigned char *target = mmap(NULL, bases * page_bytes,
					       PROT_READ | PROT_WRITE,
					       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	volatile unsigned char *eviction = mmap(NULL, eviction_pages * page_bytes,
						PROT_READ | PROT_WRITE,
						MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	unsigned long target_addr[max_replay_lines];
	const unsigned replay_lines = bases * lines_per_base;
	unsigned retries = 0;
	char token = 'x';

	if (target == MAP_FAILED || eviction == MAP_FAILED)
		fail("mmap replay benchmark");
	for (unsigned base = 0; base < bases; base++)
		for (unsigned line = 0; line < lines_per_base; line++) {
			unsigned index = base * lines_per_base + line;

			target_addr[index] = (unsigned long)&target[base * page_bytes
							       + line * line_bytes];
		}
	for (unsigned line = 0; line < replay_lines; line++)
		*(volatile unsigned long *)target_addr[line]
			= target_addr[(line + 1) % replay_lines];
	for (unsigned page = 0; page < eviction_pages; page++)
		for (unsigned offset = 0; offset < page_bytes; offset += line_bytes)
			eviction[page * page_bytes + offset] = page + offset;

	if (prctl(PR_BP_PREVIEW_PIN_SET,
		  target_addr[0], target_addr[lines_per_base],
		  target_addr[2 * lines_per_base], target_addr[3 * lines_per_base]))
		fail("pin tagged replay footprint");

	for (unsigned trial = 0; trial < trials;) {
		unsigned enabled = trial_enabled(trial);
		unsigned long before_hook, after_hook;
		uint64_t checksum = 0, entry, after_load;
		unsigned long node;

		/* Reconfiguration is outside timing and doubles as an idle barrier,
		 * preventing a late command from one arm from warming the next arm.
		 */
		while (prctl(PR_BP_PREVIEW_REPLAY_CONFIG, replay_slot,
			     lines_per_base, delay, gap)) {
			if (errno != EBUSY)
				fail("configure tagged replay footprint");
			usleep(100);
		}
		for (unsigned page = 0; page < eviction_pages; page++)
			for (unsigned offset = 0; offset < page_bytes; offset += line_bytes)
				checksum += eviction[page * page_bytes + offset];
		__asm__ volatile("fence rw, rw\nfence.i" : : : "memory");
		if (checksum == UINT64_MAX)
			fail("eviction checksum");
		if (prctl(PR_BP_PREVIEW_ENABLE, enabled ? mode : 0,
			  0UL, 0UL, 0UL))
			fail("toggle tagged replay");
		before_hook = prctl(PR_BP_PREVIEW_GET_COUNT, 0UL, 0UL, 0UL, 0UL);
		if (before_hook == (unsigned long)-1)
			fail("hook count before");
		samples[trial].enabled = enabled;
		samples[trial].accepted = 0;
		transfer(out, &token, 1);
		transfer(in, &token, 0);
		entry = cycle();
		if (probe_status) {
			uint64_t probe_start = cycle();
			long replay_status = syscall(SYS_prctl,
					PR_BP_PREVIEW_REPLAY_STATUS,
					0UL, 0UL, 0UL, 0UL);

			samples[trial].entry_probe_cycles = cycle() - probe_start;
			if (replay_status < 0)
				fail("read entry tagged replay status");
			samples[trial].entry_probe_status = replay_status;
		} else {
			samples[trial].entry_probe_cycles = 0;
			samples[trial].entry_probe_status = 0;
		}
		node = target_addr[0];
		for (unsigned line = 0; line < replay_lines; line++)
			node = *(volatile unsigned long *)node;
		after_load = cycle();
		if (node != target_addr[0])
			fail("tagged replay target checksum");
		after_hook = prctl(PR_BP_PREVIEW_GET_COUNT, 0UL, 0UL, 0UL, 0UL);
		if (after_hook == (unsigned long)-1)
			fail("hook count after");
		samples[trial].hooks = after_hook - before_hook;
		if (samples[trial].hooks != enabled) {
			fprintf(stderr,
				"TAGGED_REPLAY_RETRY trial=%u enabled=%u hooks=%u\n",
				trial, enabled, samples[trial].hooks);
			transfer(out, &token, 1);
			if (++retries > max_retries)
				fail("too many tagged replay retries");
			continue;
		}
		samples[trial].entry = entry;
		samples[trial].after_load = after_load;
		{
			long hook_cycles = prctl(PR_BP_PREVIEW_GET_HOOK_CYCLES,
						 0UL, 0UL, 0UL, 0UL);

			if (hook_cycles < 0)
				fail("read tagged replay hook cycles");
			samples[trial].hook_cycles = hook_cycles;
		}
		{
			long replay_status;
			unsigned timeout = 1048576;

			do {
				/* libc declares prctl() with an int return, which truncates
				 * the trigger/drop counters above bit 31. Use the raw syscall
				 * ABI so the complete 64-bit custom status reaches userspace.
				 */
				replay_status = syscall(SYS_prctl,
							PR_BP_PREVIEW_REPLAY_STATUS,
							0UL, 0UL, 0UL, 0UL);
				if (replay_status < 0)
					fail("read tagged replay status");
				if (!(replay_status & BP_REPLAY_DRAIN_MASK))
					break;
			} while (--timeout);
			if (!timeout) {
				fprintf(stderr,
					"TAGGED_REPLAY_DRAIN_TIMEOUT trial=%u enabled=%u status=0x%016lx\n",
					trial, enabled, replay_status);
				fail("tagged replay drain timeout");
			}
			samples[trial].accepted_entries = (replay_status >> 10) & 0xffff;
			samples[trial].filtered_entries = (replay_status >> 26) & 0xffff;
			samples[trial].accepted_triggers = (replay_status >> 42) & 0xff;
			samples[trial].dropped_triggers = (replay_status >> 50) & 0xff;
		}
		samples[trial].accepted = 1;
		samples[trial].done = cycle();
		transfer(out, &token, 1);
		trial++;
	}
	if (prctl(PR_BP_PREVIEW_ENABLE, 0UL, 0UL, 0UL, 0UL))
		fail("disable tagged replay");
	if (prctl(PR_BP_PREVIEW_PIN_SET, 0UL, 0UL, 0UL, 0UL))
		fail("release tagged replay footprint");
	printf("TAGGED_REPLAY_CHILD PASS retries=%u\n", retries);
}

int main(int argc, char **argv)
{
	int to_child[2], to_parent[2], status;
	unsigned mode = 9, delay = 0, gap = 2;
	unsigned lines_per_base = max_lines_per_base;
	unsigned long lead_cycles = 0;
	int fifo = 0, probe_status = 0;
	volatile struct sample *samples;
	char token = 'x';
	pid_t child;

	if (argc > 8) {
		fprintf(stderr, "usage: %s [data|joint] [delay-0..65535] [gap-0..255] [normal|fifo] [lead-cycles-0..1000000] [lines-per-base-1..8] [probe-status-0|1]\n",
			argv[0]);
		return 2;
	}
	if (argc >= 2) {
		if (!strcmp(argv[1], "joint"))
			mode = 10;
		else if (strcmp(argv[1], "data")) {
			fprintf(stderr, "invalid replay mode: %s\n", argv[1]);
			return 2;
		}
	}
	if (argc >= 3) {
		char *end;
		unsigned long parsed = strtoul(argv[2], &end, 10);

		if (*end || parsed > 65535) {
			fprintf(stderr, "invalid replay delay: %s\n", argv[2]);
			return 2;
		}
		delay = parsed;
	}
	if (argc >= 4) {
		char *end;
		unsigned long parsed = strtoul(argv[3], &end, 10);

		if (*end || parsed > 255) {
			fprintf(stderr, "invalid replay gap: %s\n", argv[3]);
			return 2;
		}
		gap = parsed;
	}
	if (argc >= 5) {
		if (!strcmp(argv[4], "fifo"))
			fifo = 1;
		else if (strcmp(argv[4], "normal")) {
			fprintf(stderr, "invalid scheduling policy: %s\n", argv[4]);
			return 2;
		}
	}
	if (argc >= 6) {
		char *end;
		unsigned long parsed = strtoul(argv[5], &end, 10);

		if (*end || parsed > 1000000) {
			fprintf(stderr, "invalid lead cycles: %s\n", argv[5]);
			return 2;
		}
		lead_cycles = parsed;
	}
	if (argc >= 7) {
		char *end;
		unsigned long parsed = strtoul(argv[6], &end, 10);

		if (*end || parsed < 1 || parsed > max_lines_per_base) {
			fprintf(stderr, "invalid lines per base: %s\n", argv[6]);
			return 2;
		}
		lines_per_base = parsed;
	}
	if (argc >= 8) {
		char *end;
		unsigned long parsed = strtoul(argv[7], &end, 10);

		if (*end || parsed > 1) {
			fprintf(stderr, "invalid probe status flag: %s\n", argv[7]);
			return 2;
		}
		probe_status = parsed;
	}
	if (fifo) {
		const struct sched_param parameter = {.sched_priority = 1};

		if (sched_setscheduler(0, SCHED_FIFO, &parameter))
			fail("sched_setscheduler FIFO");
	}

	samples = mmap(NULL, sizeof(*samples) * trials, PROT_READ | PROT_WRITE,
		       MAP_SHARED | MAP_ANONYMOUS, -1, 0);
	if (samples == MAP_FAILED || pipe(to_child) || pipe(to_parent))
		fail("shared memory or pipes");
	printf("TAGGED_REPLAY_CONFIG mode=%s lines=%u slot=%u delay=%u gap=%u policy=%s lead_cycles=%lu probe_status=%u\n",
	       mode == 10 ? "joint" : "data", bases * lines_per_base, replay_slot,
	       delay, gap, fifo ? "fifo" : "normal", lead_cycles, probe_status);
	child = fork();
	if (child < 0)
		fail("fork");
	if (!child) {
		close(to_child[1]);
		close(to_parent[0]);
		child_run(to_child[0], to_parent[1], samples, mode, delay, gap,
			  lines_per_base, probe_status);
		return 0;
	}
	close(to_child[0]);
	close(to_parent[1]);
	for (unsigned trial = 0; trial < trials;) {
		uint64_t lead_start;

		transfer(to_parent[0], &token, 0);
		samples[trial].launch = cycle();
		transfer(to_child[1], &token, 1);
		lead_start = cycle();
		while (cycle() - lead_start < lead_cycles)
			__asm__ volatile("" : : : "memory");
		if (probe_status) {
			uint64_t probe_start = cycle();
			long replay_status = syscall(SYS_prctl,
					PR_BP_PREVIEW_REPLAY_STATUS,
					0UL, 0UL, 0UL, 0UL);

			samples[trial].preblock_probe_cycles = cycle() - probe_start;
			if (replay_status < 0)
				fail("read preblock tagged replay status");
			samples[trial].preblock_status = replay_status;
		} else {
			samples[trial].preblock_probe_cycles = 0;
			samples[trial].preblock_status = 0;
		}
		transfer(to_parent[0], &token, 0);
		samples[trial].returned = cycle();
		if (samples[trial].accepted)
			trial++;
	}
	if (waitpid(child, &status, 0) != child)
		fail("waitpid");
	if (!WIFEXITED(status) || WEXITSTATUS(status)) {
		fprintf(stderr, "tagged replay child failed: status=%d\n", status);
		return 1;
	}
	for (unsigned trial = warmup; trial < trials; trial++) {
		const volatile struct sample *s = &samples[trial];

		if (!(s->launch <= s->entry && s->entry <= s->after_load
		      && s->after_load <= s->done && s->done <= s->returned)) {
			fprintf(stderr, "nonmonotonic tagged replay sample: %u\n", trial);
			return 1;
		}
		printf("TAGGED_REPLAY trial=%u enabled=%u hooks=%u hook_cycles=%lu admitted=%u filtered=%u triggers=%u dropped=%u wake_to_entry=%llu load_cycles=%llu wake_to_load=%llu roundtrip=%llu preblock_status=0x%016llx preblock_probe_cycles=%lu entry_probe_status=0x%016llx entry_probe_cycles=%lu\n",
		       trial - warmup, s->enabled, s->hooks, s->hook_cycles,
		       s->accepted_entries, s->filtered_entries,
		       s->accepted_triggers, s->dropped_triggers,
		       (unsigned long long)(s->entry - s->launch),
		       (unsigned long long)(s->after_load - s->entry),
		       (unsigned long long)(s->after_load - s->launch),
		       (unsigned long long)(s->returned - s->launch),
		       (unsigned long long)s->preblock_status,
		       s->preblock_probe_cycles,
		       (unsigned long long)s->entry_probe_status,
		       s->entry_probe_cycles);
	}
	puts("TAGGED_REPLAY_PARENT PASS");
	return 0;
}
