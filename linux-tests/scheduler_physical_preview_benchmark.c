#define _GNU_SOURCE

/* Measure the best-case Linux benefit of four physical L2 preview hints.
 * Target pages remain pinned in both arms. Before every handoff the child
 * pushes the four first-use lines out of the 4 KiB L2, and only scheduler hint
 * emission changes. A dependent pointer ring exposes all four cold misses.
 * An optional group 0--7 selects two adjacent L2 sets in both banks so a full
 * sweep can distinguish useful preview timing from post-hint set conflicts.
 * The second optional argument selects the historical early hook or the late
 * pre-register-switch hook in the same kernel image.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>

#if !defined(__riscv) || __riscv_xlen != 64
#error "This benchmark requires RV64 BlackParrot"
#endif

#define PR_BP_PREVIEW_GET_COUNT 0x42505057
#define PR_BP_PREVIEW_PIN_SET 0x42505059
#define PR_BP_PREVIEW_ENABLE 0x4250505a

enum { warmup = 16, measured_trials = 512, trials = warmup + measured_trials,
       lines = 4, line_bytes = 64, page_bytes = 4096, eviction_pages = 10 };

struct sample {
	uint64_t launch, entry, after_load, returned;
	unsigned mode, hooks;
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

static void child_run(int in, int out, volatile struct sample *samples,
		      unsigned group, unsigned enable_mode)
{
	volatile unsigned char *target = mmap(NULL, page_bytes,
					       PROT_READ | PROT_WRITE,
					MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	volatile unsigned char *eviction = mmap(NULL, eviction_pages * page_bytes,
						PROT_READ | PROT_WRITE,
						MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	unsigned long target_addr[lines];
	unsigned target_offset = group * 4 * line_bytes;
	char token = 'x';

	if (target == MAP_FAILED || eviction == MAP_FAILED)
		fail("mmap child pages");
	for (unsigned line = 0; line < lines; line++)
		target_addr[line] = (unsigned long)&target[target_offset
							     + line * line_bytes];
	for (unsigned line = 0; line < lines; line++)
		*(volatile unsigned long *)target_addr[line]
			= target_addr[(line + 1) % lines];
	for (unsigned page = 0; page < eviction_pages; page++)
		for (unsigned offset = 0; offset < page_bytes; offset += line_bytes)
			eviction[page * page_bytes + offset] = page + offset;
	/* Registration is intentionally outside the trial loop: both arms retain
	 * exactly the same long-term pins and physical-address bookkeeping. */
	if (prctl(PR_BP_PREVIEW_PIN_SET, target_addr[0], target_addr[1],
		  target_addr[2], target_addr[3]))
		fail("register preview lines");
	for (unsigned trial = 0; trial < trials; trial++) {
		unsigned enabled = mode_for(trial);
		unsigned long before_hook, after_hook;
		uint64_t checksum = 0, entry, after_load;
		unsigned long node;

		if (prctl(PR_BP_PREVIEW_ENABLE,
			  enabled ? enable_mode : 0UL, 0UL, 0UL, 0UL))
			fail("toggle preview emission");
		before_hook = prctl(PR_BP_PREVIEW_GET_COUNT, 0UL, 0UL, 0UL, 0UL);
		if (before_hook == (unsigned long)-1)
			fail("hook count before");
		for (unsigned page = 0; page < eviction_pages; page++)
			for (unsigned offset = 0; offset < page_bytes; offset += line_bytes)
				checksum += eviction[page * page_bytes + offset];
		__asm__ volatile("fence rw, rw" : : : "memory");
		if (checksum == UINT64_MAX)
			fail("eviction checksum");
		samples[trial].mode = enabled;
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
		/* One measured handoff must produce exactly one preview hook. A
		 * timer preemption and second selection would issue another hint
		 * batch and no longer be a matched one-switch comparison. */
		if (samples[trial].hooks != enabled)
			fail("unexpected scheduler hook count");
		transfer(out, &token, 1); /* done */
	}
	if (prctl(PR_BP_PREVIEW_ENABLE, 0UL, 0UL, 0UL, 0UL))
		fail("disable preview");
	if (prctl(PR_BP_PREVIEW_PIN_SET, 0UL, 0UL, 0UL, 0UL))
		fail("release preview");
	puts("PHYSICAL_BENCH_CHILD PASS");
}

int main(int argc, char **argv)
{
	int to_child[2], to_parent[2], status;
	unsigned group = 0;
	unsigned enable_mode = 2;
	volatile struct sample *samples = mmap(NULL, sizeof(struct sample) * trials,
					PROT_READ | PROT_WRITE,
					MAP_SHARED | MAP_ANONYMOUS, -1, 0);
	char token = 'x';
	pid_t child;

	if (argc > 3) {
		fprintf(stderr, "usage: %s [l2-set-group-0..7] [early|late]\n",
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
	if (argc == 3) {
		if (!strcmp(argv[2], "early"))
			enable_mode = 1;
		else if (!strcmp(argv[2], "late"))
			enable_mode = 2;
		else {
			fprintf(stderr, "invalid preview timing: %s\n", argv[2]);
			return 2;
		}
	}
	printf("PHYSICAL_BENCH_CONFIG group=%u first_offset=%u lines=%u timing=%s mode=%u\n",
	       group, group * 4 * line_bytes, lines,
	       enable_mode == 1 ? "early" : "late", enable_mode);

	if (samples == MAP_FAILED || pipe(to_child) || pipe(to_parent))
		fail("shared memory or pipes");
	child = fork();
	if (child < 0)
		fail("fork");
	if (!child) {
		close(to_child[1]);
		close(to_parent[0]);
		child_run(to_child[0], to_parent[1], samples, group, enable_mode);
		return 0;
	}
	close(to_child[0]);
	close(to_parent[1]);
	for (unsigned trial = 0; trial < trials; trial++) {
		transfer(to_parent[0], &token, 0);
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
		return 1;
	}
	for (unsigned trial = warmup; trial < trials; trial++) {
		const volatile struct sample *s = &samples[trial];

		if (!(s->launch <= s->entry && s->entry <= s->after_load
		      && s->after_load <= s->returned)) {
			fprintf(stderr, "nonmonotonic cycle sample: trial=%u\n", trial);
			return 1;
		}
		printf("PHYSICAL_BENCH trial=%u mode=%u hooks=%u wake_to_entry=%llu load_cycles=%llu wake_to_load=%llu roundtrip=%llu\n",
		       trial - warmup, s->mode, s->hooks,
		       (unsigned long long)(s->entry - s->launch),
		       (unsigned long long)(s->after_load - s->entry),
		       (unsigned long long)(s->after_load - s->launch),
		       (unsigned long long)(s->returned - s->launch));
	}
	puts("PHYSICAL_BENCH_PARENT PASS");
	return 0;
}
