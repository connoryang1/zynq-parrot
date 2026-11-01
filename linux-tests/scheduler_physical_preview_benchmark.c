#define _GNU_SOURCE

/* Measure the best-case Linux benefit of four physical L2 preview hints.
 * Target pages remain pinned in both arms. Before every handoff the child
 * pushes the four first-use lines out of the 4 KiB L2, and only scheduler hint
 * emission changes. A dependent pointer ring exposes all four cold misses.
 * An optional group 0--7 selects two adjacent L2 sets in both banks so a full
 * sweep can distinguish useful preview timing from post-hint set conflicts.
 * The second optional argument selects the historical early hook or the late
 * pre-register-switch hook in the same kernel image. An optional hot-proxy
 * footprint redirects hints to freshly reread eviction-buffer lines while
 * leaving the measured dependent target ring cold. This approximates an
 * instruction-only and counter-only A/B without changing the kernel. Mode five
 * removes hook accounting and uses getrusage context-switch deltas as an
 * independent one-switch filter. Mode six retains that filter but launches
 * instruction replay when the target is made runnable, before selection.
 */
#include <stdint.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

#if !defined(__riscv) || __riscv_xlen != 64
#error "This benchmark requires RV64 BlackParrot"
#endif

#define PR_BP_PREVIEW_GET_COUNT 0x42505057
#define PR_BP_PREVIEW_PIN_SET 0x42505059
#define PR_BP_PREVIEW_ENABLE 0x4250505a

enum { warmup = 16, measured_trials = 512, trials = warmup + measured_trials,
       lines = 4, line_bytes = 64, page_bytes = 4096, eviction_pages = 10,
       max_retries = 4096 };

struct sample {
	uint64_t launch, entry, after_load, done, returned;
	unsigned mode, hooks, accepted;
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

static unsigned mode_for(unsigned trial)
{
	return (trial ^ (trial >> 1)) & 1;
}

static int uncounted_mode(unsigned mode)
{
	return mode == 5 || mode == 6;
}

static void child_run(int in, int out, volatile struct sample *samples,
		      unsigned group, unsigned enable_mode, int hot_proxy)
{
	volatile unsigned char *target = mmap(NULL, page_bytes,
					       PROT_READ | PROT_WRITE,
					MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	volatile unsigned char *eviction = mmap(NULL, eviction_pages * page_bytes,
						PROT_READ | PROT_WRITE,
						MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	unsigned long target_addr[lines];
	unsigned long preview_addr[lines];
	unsigned target_offset = group * 4 * line_bytes;
	unsigned retries = 0;
	char token = 'x';

	if (target == MAP_FAILED || eviction == MAP_FAILED)
		fail("mmap child pages");
	for (unsigned line = 0; line < lines; line++)
		target_addr[line] = (unsigned long)&target[target_offset
							     + line * line_bytes];
	for (unsigned line = 0; line < lines; line++)
		preview_addr[line] = hot_proxy
			? (unsigned long)&eviction[target_offset + line * line_bytes]
			: target_addr[line];
	for (unsigned line = 0; line < lines; line++)
		*(volatile unsigned long *)target_addr[line]
			= target_addr[(line + 1) % lines];
	for (unsigned page = 0; page < eviction_pages; page++)
		for (unsigned offset = 0; offset < page_bytes; offset += line_bytes)
			eviction[page * page_bytes + offset] = page + offset;
	/* Registration is intentionally outside the trial loop: both arms retain
	 * exactly the same long-term pins and physical-address bookkeeping. */
	if (prctl(PR_BP_PREVIEW_PIN_SET, preview_addr[0], preview_addr[1],
		  preview_addr[2], preview_addr[3]))
		fail("register preview lines");
	for (unsigned trial = 0; trial < trials;) {
		unsigned enabled = mode_for(trial);
		unsigned long before_hook, after_hook;
		struct rusage before_usage, after_usage;
		uint64_t checksum = 0, entry, after_load;
		unsigned long node;
		long voluntary = 0, involuntary = 0;

		for (unsigned page = 0; page < eviction_pages; page++)
			for (unsigned offset = 0; offset < page_bytes; offset += line_bytes)
				checksum += eviction[page * page_bytes + offset];
		/* Keep proxy hints as cache hits without touching the cold target ring.
		 * This traffic is identical in the enabled and disabled arms until the
		 * scheduler trigger itself. */
		if (hot_proxy)
			for (unsigned line = 0; line < lines; line++)
				checksum += *(volatile unsigned char *)preview_addr[line];
		__asm__ volatile("fence rw, rw" : : : "memory");
		if (checksum == UINT64_MAX)
			fail("eviction checksum");
		/* Arm only after cache preparation. On the slow FPGA, enabling before
		 * this 40 KiB loop allowed a timer preemption to issue one hint batch,
		 * followed by the intended pipe-wakeup batch. Besides violating the
		 * one-hook invariant, that gave the first batch excessive lead time. */
		if (prctl(PR_BP_PREVIEW_ENABLE,
			  enabled ? enable_mode : 0UL, 0UL, 0UL, 0UL))
			fail("toggle preview emission");
		before_hook = prctl(PR_BP_PREVIEW_GET_COUNT, 0UL, 0UL, 0UL, 0UL);
		if (before_hook == (unsigned long)-1)
			fail("hook count before");
		samples[trial].mode = enabled;
		samples[trial].accepted = 0;
		if (uncounted_mode(enable_mode)
		    && getrusage(RUSAGE_SELF, &before_usage))
			fail("getrusage before handoff");
		transfer(out, &token, 1); /* ready */
		transfer(in, &token, 0);  /* parent blocks; scheduler selects child */
		entry = cycle();
		node = target_addr[0];
		for (unsigned line = 0; line < lines; line++)
			node = *(volatile unsigned long *)node;
		after_load = cycle();
		samples[trial].entry = entry;
		samples[trial].after_load = after_load;
		if (node != target_addr[0])
			fail("target checksum");
		after_hook = prctl(PR_BP_PREVIEW_GET_COUNT, 0UL, 0UL, 0UL, 0UL);
		if (after_hook == (unsigned long)-1)
			fail("hook count after");
		samples[trial].hooks = after_hook - before_hook;
		if (uncounted_mode(enable_mode)) {
			if (getrusage(RUSAGE_SELF, &after_usage))
				fail("getrusage after handoff");
			voluntary = after_usage.ru_nvcsw - before_usage.ru_nvcsw;
			involuntary = after_usage.ru_nivcsw - before_usage.ru_nivcsw;
		}
		/* Retain only one-switch handoffs. Counted modes use the scheduler
		 * hook itself. Uncounted mode five instead requires exactly the one
		 * voluntary pipe block and no involuntary switch in both A/B arms. */
		if ((uncounted_mode(enable_mode) && (samples[trial].hooks != 0
					 || voluntary != 1 || involuntary != 0))
			|| (!uncounted_mode(enable_mode)
			    && samples[trial].hooks != enabled)) {
			fprintf(stderr,
				"PHYSICAL_BENCH_RETRY trial=%u enabled=%u mode=%u before=%lu after=%lu delta=%u voluntary=%ld involuntary=%ld\n",
				trial, enabled, enable_mode, before_hook, after_hook,
				samples[trial].hooks, voluntary, involuntary);
			transfer(out, &token, 1); /* contaminated attempt done */
			if (++retries > max_retries)
				fail("too many scheduler hook retries");
			continue;
		}
		samples[trial].accepted = 1;
		samples[trial].done = cycle();
		transfer(out, &token, 1); /* done */
		trial++;
	}
	if (prctl(PR_BP_PREVIEW_ENABLE, 0UL, 0UL, 0UL, 0UL))
		fail("disable preview");
	if (prctl(PR_BP_PREVIEW_PIN_SET, 0UL, 0UL, 0UL, 0UL))
		fail("release preview");
	printf("PHYSICAL_BENCH_CHILD PASS retries=%u\n", retries);
}

int main(int argc, char **argv)
{
	int to_child[2], to_parent[2], status;
	unsigned group = 0;
	unsigned enable_mode = 2;
	int hot_proxy = 0;
	int fifo = 0;
	volatile struct sample *samples = mmap(NULL, sizeof(struct sample) * trials,
					PROT_READ | PROT_WRITE,
					MAP_SHARED | MAP_ANONYMOUS, -1, 0);
	char token = 'x';
	pid_t child;

	if (argc > 5) {
		fprintf(stderr, "usage: %s [l2-set-group-0..7] [early|late|instruction|counter|trigger|wake-trigger] [target|hot-proxy] [normal|fifo]\n",
			argv[0]);
		return 2;
	}
	if (argc >= 2) {
		if (argv[1][0] < '0' || argv[1][0] > '7' || argv[1][1]) {
			fprintf(stderr, "invalid L2 set group: %s\n", argv[1]);
			return 2;
		}
		group = argv[1][0] - '0';
	}
	if (argc >= 3) {
		if (!strcmp(argv[2], "early"))
			enable_mode = 1;
		else if (!strcmp(argv[2], "late"))
			enable_mode = 2;
		else if (!strcmp(argv[2], "instruction"))
			enable_mode = 3;
		else if (!strcmp(argv[2], "counter"))
			enable_mode = 4;
		else if (!strcmp(argv[2], "trigger"))
			enable_mode = 5;
		else if (!strcmp(argv[2], "wake-trigger"))
			enable_mode = 6;
		else {
			fprintf(stderr, "invalid preview timing: %s\n", argv[2]);
			return 2;
		}
	}
	if (argc >= 4) {
		if (!strcmp(argv[3], "hot-proxy"))
			hot_proxy = 1;
		else if (strcmp(argv[3], "target")) {
			fprintf(stderr, "invalid preview footprint: %s\n", argv[3]);
			return 2;
		}
	}
	if (argc >= 5) {
		if (!strcmp(argv[4], "fifo"))
			fifo = 1;
		else if (strcmp(argv[4], "normal")) {
			fprintf(stderr, "invalid scheduling policy: %s\n", argv[4]);
			return 2;
		}
	}
	printf("PHYSICAL_BENCH_CONFIG group=%u first_offset=%u lines=%u timing=%s mode=%u footprint=%s policy=%s\n",
	       group, group * 4 * line_bytes, lines,
	       enable_mode == 1 ? "early" :
	       enable_mode == 2 ? "late" :
	       enable_mode == 3 ? "instruction" :
	       enable_mode == 4 ? "counter" :
	       enable_mode == 5 ? "trigger" : "wake-trigger", enable_mode,
	       hot_proxy ? "hot-proxy" : "target", fifo ? "fifo" : "normal");

	if (fifo) {
		const struct sched_param parameter = {.sched_priority = 1};

		/* Both processes inherit equal-priority FIFO policy across fork. They
		 * alternate only at blocking pipe operations, removing normal-policy
		 * timeslice phase from this best-case mechanism experiment. */
		if (sched_setscheduler(0, SCHED_FIFO, &parameter))
			fail("sched_setscheduler FIFO");
	}

	if (samples == MAP_FAILED || pipe(to_child) || pipe(to_parent))
		fail("shared memory or pipes");
	child = fork();
	if (child < 0)
		fail("fork");
	if (!child) {
		close(to_child[1]);
		close(to_parent[0]);
		child_run(to_child[0], to_parent[1], samples, group, enable_mode,
			  hot_proxy);
		return 0;
	}
	close(to_child[0]);
	close(to_parent[1]);
	for (unsigned trial = 0; trial < trials;) {
		transfer(to_parent[0], &token, 0);
		samples[trial].launch = cycle();
		__asm__ volatile("fence rw, rw" : : : "memory");
		transfer(to_child[1], &token, 1);
		transfer(to_parent[0], &token, 0);
		samples[trial].returned = cycle();
		if (samples[trial].accepted)
			trial++;
	}
	if (waitpid(child, &status, 0) != child)
		fail("waitpid");
	if (!WIFEXITED(status) || WEXITSTATUS(status)) {
		fprintf(stderr, "child failed: status=%d\n", status);
		return 1;
	}
	for (unsigned trial = warmup; trial < trials; trial++) {
		const volatile struct sample *s = &samples[trial];

		if (!(s->launch <= s->entry && s->entry <= s->after_load
		      && s->after_load <= s->done && s->done <= s->returned)) {
			fprintf(stderr, "nonmonotonic cycle sample: trial=%u\n", trial);
			return 1;
		}
		printf("PHYSICAL_BENCH trial=%u mode=%u hooks=%u wake_to_entry=%llu load_cycles=%llu wake_to_load=%llu roundtrip=%llu\n",
		       trial - warmup, s->mode, s->hooks,
		       (unsigned long long)(s->entry - s->launch),
		       (unsigned long long)(s->after_load - s->entry),
		       (unsigned long long)(s->after_load - s->launch),
		       (unsigned long long)(s->returned - s->launch));
		printf("PHYSICAL_BENCH_TAIL trial=%u child_post_load=%llu return_handoff=%llu\n",
		       trial - warmup,
		       (unsigned long long)(s->done - s->after_load),
		       (unsigned long long)(s->returned - s->done));
	}
	puts("PHYSICAL_BENCH_PARENT PASS");
	return 0;
}
