/* SPDX-License-Identifier: GPL-2.0
 * Address record/replay across a Linux futex handoff (draft kernel patch 0031).
 *
 * A latency-critical foreground (parent) and a cache-polluting background
 * (child) alternate through a futex, as in scheduler_retained_fgbg_benchmark.
 * The foreground registers its data footprint once with
 * PR_BP_REPLAY_FOOTPRINT: every 64-byte line of its workload buffer, its
 * shared handoff page and the top of its user stack, optionally preceded by
 * its own kernel switch state (top of kernel stack, head of task_struct). The
 * firmware already holds the kernel switch-path code lines.
 *
 * Cells (ABBA alternation against "off" in every repeat):
 *   off    : footprint registered, replay disabled (mode 0); paired control.
 *   wake   : mode 10, data slot + code prefix triggered in try_to_wake_up(),
 *            i.e. when the background wakes the foreground, before the
 *            background finishes its turn (the earlier trigger).
 *   switch : mode 16, same lanes triggered in context_switch() to the
 *            foreground (end of the background's turn).
 * Suffix "+k" adds the kernel switch-state lines to the footprint.
 *
 * Metrics, from the core-wide cycle CSR 0xcc0 over the measured loops:
 * whole (fg+bg transaction), fg_work (request body), fg_latency (background
 * yield -> foreground request complete: wakeup, switch, request) and
 * bg_work. Switch overhead = fg_latency - (warm fg_work, from "solo").
 */
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <sched.h>
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
#include "resume_workload.h"

#define PR_BP_PREVIEW_ENABLE 0x4250505a
#define PR_BP_REPLAY_FOOTPRINT 0x42505066
#define PR_BP_REPLAY_FP_KERNEL 1UL
#define FP_MAX_LINES 256u
#define FP_KERNEL_LINES 12u
#define FP_STACK_LINES 4u

static void fail(const char *m) { perror(m); exit(1); }
static uint64_t cycle(void)
{
	uint64_t v;
	__asm__ volatile("csrr %0, 0xcc0" : "=r"(v) : : "memory");
	return v;
}

struct shared {
	_Atomic uint32_t turn;
	uint32_t pad;
	volatile uint64_t bg_yield;
};
static void wait_turn(struct shared *s, unsigned want)
{
	for (;;) {
		uint32_t o = atomic_load_explicit(&s->turn, memory_order_acquire);
		if (o == want) return;
		if (syscall(SYS_futex, (uint32_t *)&s->turn, FUTEX_WAIT, o, NULL, NULL, 0)
		    && errno != EAGAIN && errno != EINTR) fail("futex wait");
	}
}
static void send_turn(struct shared *s, unsigned v)
{
	atomic_store_explicit(&s->turn, v, memory_order_release);
	if (syscall(SYS_futex, (uint32_t *)&s->turn, FUTEX_WAKE, 1, NULL, NULL, 0) < 0) fail("futex wake");
}

/* Footprint order follows first use after the wake: handoff page, stack,
 * then the request's buffer. Returns the number of user lines. */
static unsigned build_footprint(unsigned long *lines, unsigned cap, const struct shared *s,
				const struct resume_workload *w)
{
	unsigned n = 0;
	unsigned long sp = (unsigned long)__builtin_frame_address(0) & ~63UL;
	lines[n++] = (unsigned long)s;
	for (unsigned i = 0; i < FP_STACK_LINES && n < cap; ++i)
		lines[n++] = sp - i * 64;
	for (size_t off = 0; off < w->bytes && n < cap; off += 64)
		lines[n++] = (unsigned long)(w->data + off);
	return n;
}

struct result { uint64_t whole, fg_work, fg_latency, bg_work; };

static struct result run_cell(unsigned loops, unsigned warmup, unsigned fg_kib, unsigned bg_kib,
			      const char *fg_kind, const char *bg_kind, unsigned mode, int kernel_lines,
			      unsigned *fp_lines)
{
	struct result r = {0};
	struct shared *s = mmap(NULL, sizeof(*s), PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0);
	if (s == MAP_FAILED) fail("mmap");
	atomic_init(&s->turn, 0);
	int ready[2];
	if (pipe(ready)) fail("pipe");
	pid_t child = fork();
	if (child < 0) fail("fork");
	if (!child) {
		struct resume_workload w;
		uint64_t sum = 0, bg = 0;
		char token = 0;
		if (prctl(PR_BP_PREVIEW_ENABLE, 0UL, 0UL, 0UL, 0UL)) fail("bg preview off");
		if (resume_workload_init(&w, bg_kind, bg_kib, 0x3c)) fail("bg alloc");
		close(ready[0]);
		if (write(ready[1], &token, 1) != 1) fail("ready");
		for (unsigned n = 0; n < warmup + loops; ++n) {
			wait_turn(s, 1);
			uint64_t t0 = cycle();
			sum += resume_workload_run(&w);
			uint64_t t1 = cycle();
			if (n >= warmup) bg += t1 - t0;
			s->bg_yield = cycle();
			send_turn(s, 0);
		}
		wait_turn(s, 2);
		if (!resume_workload_check_total(&w, sum)) { errno = EIO; fail("bg checksum"); }
		s->bg_yield = bg;
		atomic_store_explicit(&s->turn, 3, memory_order_release);
		_exit(0);
	}

	/* Foreground: register after fork so the slot and pins belong to it. */
	struct resume_workload w;
	uint64_t sum = 0, begin = 0;
	char token;
	if (resume_workload_init(&w, fg_kind, fg_kib, 0xc3)) fail("fg alloc");
	unsigned long lines[FP_MAX_LINES];
	unsigned cap = FP_MAX_LINES - (kernel_lines ? FP_KERNEL_LINES : 0);
	unsigned n_user = build_footprint(lines, cap, s, &w);
	unsigned total = n_user + (kernel_lines ? FP_KERNEL_LINES : 0);
	if (prctl(PR_BP_REPLAY_FOOTPRINT, 0UL, (unsigned long)lines, (unsigned long)total,
		  kernel_lines ? PR_BP_REPLAY_FP_KERNEL : 0UL))
		fail("replay footprint");
	if (prctl(PR_BP_PREVIEW_ENABLE, (unsigned long)mode, 0UL, 0UL, 0UL)) fail("replay mode");
	*fp_lines = total;
	close(ready[1]);
	if (read(ready[0], &token, 1) != 1) fail("ready read");
	close(ready[0]);
	s->bg_yield = cycle();
	for (unsigned n = 0; n < warmup + loops; ++n) {
		if (n == warmup) begin = cycle();
		uint64_t woke = s->bg_yield;
		uint64_t t0 = cycle();
		sum += resume_workload_run(&w);
		uint64_t t1 = cycle();
		if (n >= warmup) { r.fg_work += t1 - t0; r.fg_latency += t1 - woke; }
		send_turn(s, 1);
		wait_turn(s, 0);
	}
	r.whole = cycle() - begin;
	/* Disable before teardown; the next cell re-registers (and the kernel
	 * drains queued replay before unpinning the old footprint). */
	if (prctl(PR_BP_PREVIEW_ENABLE, 0UL, 0UL, 0UL, 0UL)) fail("replay off");
	send_turn(s, 2);
	while (atomic_load_explicit(&s->turn, memory_order_acquire) != 3) sched_yield();
	r.bg_work = s->bg_yield;
	int st;
	if (waitpid(child, &st, 0) != child || !WIFEXITED(st) || WEXITSTATUS(st)) { errno = ECHILD; fail("child"); }
	if (!resume_workload_check_total(&w, sum)) { errno = EIO; fail("fg checksum"); }
	resume_workload_free(&w);
	munmap(s, sizeof(*s));
	return r;
}

int main(int argc, char **argv)
{
	if (argc != 9) {
		fprintf(stderr, "usage: %s loops repeats warmup fg_kib bg_kib fg_kind bg_kind "
				"solo|off|wake|switch[+k]\n", argv[0]);
		return 2;
	}
	unsigned loops = strtoul(argv[1], 0, 0), repeats = strtoul(argv[2], 0, 0);
	unsigned warmup = strtoul(argv[3], 0, 0), fg_kib = strtoul(argv[4], 0, 0);
	unsigned bg_kib = strtoul(argv[5], 0, 0);
	const char *fg_kind = argv[6], *bg_kind = argv[7];
	char policy[16];
	if (strlen(argv[8]) >= sizeof(policy)) { fputs("policy too long\n", stderr); return 2; }
	strcpy(policy, argv[8]);
	int kernel_lines = 0;
	size_t plen = strlen(policy);
	if (plen > 2 && !strcmp(policy + plen - 2, "+k")) { policy[plen - 2] = 0; kernel_lines = 1; }

	if (!strcmp(policy, "solo")) {
		/* Warm reference: the same request run back to back, no handoff. */
		struct resume_workload w;
		uint64_t sum = 0;
		if (resume_workload_init(&w, fg_kind, fg_kib, 0xc3)) fail("fg alloc");
		for (unsigned rep = 0; rep < repeats; ++rep) {
			uint64_t tot = 0;
			for (unsigned n = 0; n < warmup + loops; ++n) {
				uint64_t t0 = cycle();
				sum += resume_workload_run(&w);
				uint64_t t1 = cycle();
				if (n >= warmup) tot += t1 - t0;
			}
			printf("REPLAYFP_SOLO repeat=%u fg=%s fg_kib=%u per_req=%" PRIu64 "\n",
			       rep, fg_kind, fg_kib, tot / loops);
			fflush(stdout);
		}
		if (!resume_workload_check_total(&w, sum)) { errno = EIO; fail("solo checksum"); }
		puts("REPLAYFP_PASS");
		return 0;
	}
	unsigned mode;
	if (!strcmp(policy, "off")) mode = 0;
	else if (!strcmp(policy, "wake")) mode = 10;
	else if (!strcmp(policy, "switch")) mode = 16;
	else { fputs("policy must be solo, off, wake or switch (optionally +k)\n", stderr); return 2; }

	printf("REPLAYFP_CONFIG loops=%u repeats=%u warmup=%u fg_kib=%u bg_kib=%u fg=%s bg=%s policy=%s%s\n",
	       loops, repeats, warmup, fg_kib, bg_kib, fg_kind, bg_kind, policy, kernel_lines ? "+k" : "");
	for (unsigned rep = 0; rep < repeats; ++rep) {
		for (unsigned order = 0; order < 2; ++order) {
			unsigned on = (rep + order) & 1;  /* ABBA-style alternation */
			unsigned fp = 0;
			struct result r = run_cell(loops, warmup, fg_kib, bg_kib, fg_kind, bg_kind,
						   on ? mode : 0, kernel_lines, &fp);
			printf("REPLAYFP_RESULT repeat=%u order=%u enabled=%u mode=%u fp_lines=%u whole=%" PRIu64
			       " fg_work=%" PRIu64 " fg_latency=%" PRIu64 " bg_work=%" PRIu64 " loops=%u\n",
			       rep, order, on, on ? mode : 0, fp, r.whole, r.fg_work, r.fg_latency, r.bg_work, loops);
			fflush(stdout);
		}
	}
	puts("REPLAYFP_PASS");
	return 0;
}
