/* SPDX-License-Identifier: GPL-2.0
 * Foreground/background retained-line application benchmark (Linux, ABI29).
 *
 * A latency-critical foreground process (parent) and a cache-polluting
 * background process (child) alternate through a futex handoff, as in
 * scheduler_retained29_cost_benchmark. Each foreground turn runs one request
 * of the selected workload over its private working set; each background
 * turn scans a larger private set that evicts the foreground from L1/L2.
 *
 * Retention policy is per task: while the foreground runs, CSR 0x5c2 enables
 * lookups and demand capture for the selected lanes; before it yields it keeps
 * lookups enabled but turns capture off, so the background's fills do not
 * displace the foreground's retained lines. With the preserve-on-capture-toggle
 * RTL, these writes never clear the store (the lane enables are unchanged).
 * The "off" cell issues the SAME two prctl() calls per turn with mask 0, so the
 * system-call overhead is matched and only the hardware policy differs.
 *
 * Metrics, all from the core-wide physical cycle CSR 0xcc0 over measured
 * loops: whole (complete fg+bg transaction time), fg_work (request body),
 * fg_latency (background yield -> foreground request complete, i.e. wakeup,
 * switch, policy write and request), bg_work.
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
#define PR_BP_RETAINED_CONTROL 0x42505063
#define PR_BP_RETAINED_STATUS 0x42505064
#define PR_BP_RETAINED_OWNER 0x42505065
#define BUSY UINT64_C(0x300)

static void fail(const char *m) { perror(m); exit(1); }
static uint64_t cycle(void)
{
	uint64_t v;
	__asm__ volatile("csrr %0, 0xcc0" : "=r"(v) : : "memory");
	return v;
}
static uint64_t status(void)
{
	uint64_t raw = 0;
	if (prctl(PR_BP_RETAINED_STATUS, (unsigned long)&raw, 0UL, 0UL, 0UL)) fail("retained status");
	return raw;
}
static void submit(unsigned mask)
{
	if (prctl(PR_BP_RETAINED_CONTROL, (unsigned long)mask, 0UL, 0UL, 0UL)) fail("retained control");
}
static void settle(unsigned mask)
{
	for (unsigned n = 0; n < 100000; ++n) {
		uint64_t raw = status();
		if ((raw & 15) == mask && !(raw & BUSY)) return;
	}
	errno = ETIMEDOUT; fail("retained settle");
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

struct result { uint64_t whole, fg_work, fg_latency, bg_work; };

static struct result run_cell(unsigned loops, unsigned warmup, unsigned fg_kib, unsigned bg_kib,
			      const char *fg_kind, const char *bg_kind, unsigned enable, unsigned capture,
			      unsigned bg_capture, int kmode)
{
	struct result r = {0};
	struct shared *s = mmap(NULL, sizeof(*s), PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0);
	if (s == MAP_FAILED) fail("mmap");
	atomic_init(&s->turn, 0);
	/* Start every cell from an empty, settled store. */
	submit(0); settle(0);
	if (enable) { submit(enable | bg_capture); settle(enable | bg_capture); }
	/* Kernel-managed gating: the foreground registers itself as the owner
	 * once; context_switch() turns capture on/off. No per-turn calls in
	 * either cell. Registration happens before fork, in the parent. */
	if (kmode && enable && prctl(PR_BP_RETAINED_OWNER, (unsigned long)enable, (unsigned long)capture, 0UL, 0UL))
		fail("retained owner register");
	int ready[2];
	if (pipe(ready)) fail("pipe");
	pid_t child = fork();
	if (child < 0) fail("fork");
	if (!child) {
		struct resume_workload w;
		uint64_t sum = 0, bg = 0;
		char token = 0;
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
		/* Report background work through the shared page. */
		s->bg_yield = bg;
		atomic_store_explicit(&s->turn, 3, memory_order_release);
		_exit(0);
	}
	struct resume_workload w;
	uint64_t sum = 0, begin = 0;
	char token;
	if (resume_workload_init(&w, fg_kind, fg_kib, 0xc3)) fail("fg alloc");
	close(ready[1]);
	if (read(ready[0], &token, 1) != 1) fail("ready read");
	close(ready[0]);
	s->bg_yield = cycle();
	for (unsigned n = 0; n < warmup + loops; ++n) {
		if (n == warmup) begin = cycle();
		uint64_t woke = s->bg_yield;
		if (!kmode) submit(enable | capture);  /* foreground: capture on */
		uint64_t t0 = cycle();
		sum += resume_workload_run(&w);
		uint64_t t1 = cycle();
		if (!kmode) submit(enable | bg_capture);  /* keep lookups; background capture */
		if (n >= warmup) { r.fg_work += t1 - t0; r.fg_latency += t1 - woke; }
		send_turn(s, 1);
		wait_turn(s, 0);
	}
	r.whole = cycle() - begin;
	send_turn(s, 2);
	while (atomic_load_explicit(&s->turn, memory_order_acquire) != 3) sched_yield();
	r.bg_work = s->bg_yield;
	if (kmode && enable && prctl(PR_BP_RETAINED_OWNER, 0UL, 0UL, 0UL, 0UL)) fail("retained owner unregister");
	int st;
	if (waitpid(child, &st, 0) != child || !WIFEXITED(st) || WEXITSTATUS(st)) { errno = ECHILD; fail("child"); }
	if (!resume_workload_check_total(&w, sum)) { errno = EIO; fail("fg checksum"); }
	resume_workload_free(&w);
	munmap(s, sizeof(*s));
	submit(0); settle(0);
	return r;
}

int main(int argc, char **argv)
{
	if (argc != 9) {
		fprintf(stderr, "usage: %s loops repeats warmup fg_kib bg_kib fg_kind bg_kind off|i|d|joint\n", argv[0]);
		return 2;
	}
	unsigned loops = strtoul(argv[1], 0, 0), repeats = strtoul(argv[2], 0, 0);
	unsigned warmup = strtoul(argv[3], 0, 0), fg_kib = strtoul(argv[4], 0, 0);
	unsigned bg_kib = strtoul(argv[5], 0, 0);
	const char *fg_kind = argv[6], *bg_kind = argv[7], *policy = argv[8];
	/* bg_capture: capture bits left on while the background runs. "-iall"
	 * keeps instruction capture on for both tasks (shared kernel code). */
	unsigned enable, capture, bg_capture = 0;
	int kmode = 0;
	size_t plen = strlen(policy);
	char base[32];
	if (plen > 2 && plen < sizeof(base) && !strcmp(policy + plen - 2, "-k")) {
		memcpy(base, policy, plen - 2); base[plen - 2] = 0; policy = base; kmode = 1;
	}
	if (!strcmp(policy, "i")) { enable = 1; capture = 8; }
	else if (!strcmp(policy, "d")) { enable = 2; capture = 4; }
	else if (!strcmp(policy, "joint")) { enable = 3; capture = 12; }
	else if (!strcmp(policy, "iall")) { enable = 1; capture = 8; bg_capture = 8; }
	else if (!strcmp(policy, "joint-iall")) { enable = 3; capture = 12; bg_capture = 8; }
	else { fputs("policy must be i, d, joint, iall or joint-iall (off is the paired control)\n", stderr); return 2; }
	if (prctl(PR_BP_PREVIEW_ENABLE, 0UL, 0UL, 0UL, 0UL)) fail("preview off");
	uint64_t raw = status();
	if (!(raw >> 63)) { errno = ENODEV; fail("retained capability"); }
	printf("FGBG_CONFIG loops=%u repeats=%u warmup=%u fg_kib=%u bg_kib=%u fg=%s bg=%s policy=%s%s"
	       " i_lines=%u d_lines=%u set_log2=%u\n", loops, repeats, warmup, fg_kib, bg_kib, fg_kind,
	       bg_kind, policy, kmode ? "-k" : "", (unsigned)((raw >> 16) & 0xffff), (unsigned)((raw >> 32) & 0xffff),
	       (unsigned)((raw >> 48) & 0xff));
	for (unsigned rep = 0; rep < repeats; ++rep) {
		for (unsigned order = 0; order < 2; ++order) {
			unsigned on = (rep + order) & 1;  /* ABBA-style alternation */
			struct result r = run_cell(loops, warmup, fg_kib, bg_kib, fg_kind, bg_kind,
						   on ? enable : 0, on ? capture : 0, on ? bg_capture : 0, kmode);
			printf("FGBG_RESULT repeat=%u order=%u enabled=%u whole=%" PRIu64 " fg_work=%" PRIu64
			       " fg_latency=%" PRIu64 " bg_work=%" PRIu64 " loops=%u\n", rep, order, on,
			       r.whole, r.fg_work, r.fg_latency, r.bg_work, loops);
			fflush(stdout);
		}
	}
	puts("FGBG_PASS");
	return 0;
}
