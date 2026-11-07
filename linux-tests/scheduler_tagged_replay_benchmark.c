#define _GNU_SOURCE

/* Measure a best-case Linux handoff with one tagged data replay.
 * Both arms retain identical pins and hardware footprint configuration; only
 * the successful-wakeup trigger mode changes. Four page-aligned bases expand
 * to a configurable number of cache lines, and a dependent pointer ring
 * exposes first use.
 */
#include <errno.h>
#include <linux/futex.h>
#include <stdatomic.h>
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
#define PR_BP_PREVIEW_ICACHE_STATUS 0x4250505e
#define PR_BP_PREVIEW_ICACHE_TRIGGER 0x4250505f
#define BP_REPLAY_DRAIN_MASK (0xfUL | (7UL << 60))
#define TRACE_DEPTH 256U

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

_Static_assert((bases - 1) * max_lines_per_base * line_bytes
	       + max_lines_per_base * line_bytes <= page_bytes,
	       "skewed replay footprint must remain inside each pinned page");

struct sample {
	uint64_t launch, entry, after_load, done, returned;
	uint64_t trace_start, trace_status;
	uint64_t preblock_status;
	uint64_t entry_probe_status;
	_Atomic unsigned wake_count;
	unsigned long hook_cycles;
	unsigned long preblock_probe_cycles;
	unsigned long entry_probe_cycles;
	unsigned accepted_entries, filtered_entries, accepted_triggers, dropped_triggers;
	unsigned hooks, enabled, accepted;
};

struct shared_state {
	_Atomic uint32_t phase;
	struct sample samples[trials];
};

static void print_tail_partitions(volatile struct sample *samples)
	__attribute__((noinline));

static int diagnostic_progress;

static void diagnostic_stage(const char *role, const char *stage,
			     unsigned trial, unsigned enabled)
{
	if (diagnostic_progress)
		fprintf(stderr,
			"TAGGED_REPLAY_DIAG role=%s stage=%s trial=%u enabled=%u\n",
			role, stage, trial, enabled);
}

enum sync_style {
	sync_pipe,
	sync_futex,
};

enum futex_phase {
	futex_idle,
	futex_child_ready,
	futex_parent_go,
	futex_child_done,
	futex_parent_ack,
};

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

static inline uint64_t trace_record(unsigned index)
{
	uint64_t value;

	__asm__ volatile(
		"csrw 0x806, %1\n"
		"nop\n"
		"nop\n"
		"nop\n"
		"csrr %0, 0x807\n"
		: "=r"(value) : "r"((uint64_t)index) : "memory");
	return value;
}

static void fail(const char *what)
{
	perror(what);
	exit(1);
}

static uint64_t icache_prefix_status(void)
{
	uint64_t status;

	if (syscall(SYS_prctl, PR_BP_PREVIEW_ICACHE_STATUS,
		    (unsigned long)&status, 0UL, 0UL, 0UL))
		fail("read instruction-prefix status");
	return status;
}

static void transfer(int fd, char *token, int send)
{
	ssize_t count = send ? write(fd, token, 1) : read(fd, token, 1);

	if (count != 1)
		fail(send ? "write pipe" : "read pipe");
}

static void futex_wait_for(_Atomic uint32_t *word, uint32_t wanted)
{
	for (;;) {
		uint32_t observed = atomic_load_explicit(word, memory_order_acquire);

		if (observed == wanted)
			return;
		if (syscall(SYS_futex, (uint32_t *)word, FUTEX_WAIT,
			    observed, NULL, NULL, 0) && errno != EAGAIN && errno != EINTR)
			fail("futex wait tagged replay");
	}
}

static int futex_set_wake(_Atomic uint32_t *word, uint32_t value)
{
	int woken;

	atomic_store_explicit(word, value, memory_order_release);
	woken = syscall(SYS_futex, (uint32_t *)word, FUTEX_WAKE,
			1, NULL, NULL, 0);
	if (woken < 0)
		fail("futex wake tagged replay");
	return woken;
}

static void child_handoff_begin(int in, int out, char *token,
				_Atomic uint32_t *phase, enum sync_style sync)
{
	if (sync == sync_pipe) {
		transfer(out, token, 1);
		transfer(in, token, 0);
		return;
	}
	futex_wait_for(phase, futex_idle);
	futex_set_wake(phase, futex_child_ready);
	futex_wait_for(phase, futex_parent_go);
}

static void child_handoff_end(int out, char *token, _Atomic uint32_t *phase,
			      enum sync_style sync)
{
	if (sync == sync_pipe) {
		transfer(out, token, 1);
		return;
	}
	futex_set_wake(phase, futex_child_done);
	futex_wait_for(phase, futex_parent_ack);
	futex_set_wake(phase, futex_idle);
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
		      unsigned lines_per_base, unsigned config_lines_per_base,
		      int probe_status, int skew_layout, int trace_stop_at_entry,
		      unsigned expected_enabled_hooks, int explicit_instruction,
		      _Atomic uint32_t *phase,
		      enum sync_style sync)
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
			/* The historical layout places all four bases at identical page
			 * offsets. Skew by one maximum-width footprint per page to keep
			 * the line count constant while reducing L2 set concentration.
			 */
			unsigned set_offset = skew_layout
				? base * max_lines_per_base * line_bytes : 0;

			target_addr[index] = (unsigned long)&target[base * page_bytes
							       + set_offset
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
		unsigned enabled = (mode || explicit_instruction)
			? trial_enabled(trial) : 0;
		unsigned long before_hook, after_hook;
		uint64_t checksum = 0, entry, after_load;
		unsigned long node;

		diagnostic_stage("child", "configure_begin", trial, enabled);
		/* Reconfiguration is outside timing and doubles as an idle barrier,
		 * preventing a late command from one arm from warming the next arm.
		 */
		while (prctl(PR_BP_PREVIEW_REPLAY_CONFIG, replay_slot,
			     config_lines_per_base, delay, gap)) {
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
		atomic_store_explicit(&samples[trial].wake_count, UINT32_MAX,
				      memory_order_release);
		diagnostic_stage("child", "handoff_begin", trial, enabled);
		child_handoff_begin(in, out, &token, phase, sync);
		diagnostic_stage("child", "resumed", trial, enabled);
		entry = cycle();
		if (samples[trial].trace_start && trace_stop_at_entry) {
			trace_control(0);
			__asm__ volatile("nop\nnop\nnop" : : : "memory");
			samples[trial].trace_status = trace_status();
		}
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
		if (samples[trial].trace_start && !trace_stop_at_entry) {
			trace_control(0);
			__asm__ volatile("nop\nnop\nnop" : : : "memory");
			samples[trial].trace_status = trace_status();
		}
		after_hook = prctl(PR_BP_PREVIEW_GET_COUNT, 0UL, 0UL, 0UL, 0UL);
		if (after_hook == (unsigned long)-1)
			fail("hook count after");
		samples[trial].hooks = after_hook - before_hook;
		while (atomic_load_explicit(&samples[trial].wake_count,
					   memory_order_acquire) == UINT32_MAX)
			__asm__ volatile("" : : : "memory");
		if (samples[trial].hooks != enabled * expected_enabled_hooks
		    || atomic_load_explicit(&samples[trial].wake_count,
					    memory_order_relaxed) != 1) {
			fprintf(stderr,
				"TAGGED_REPLAY_RETRY trial=%u enabled=%u hooks=%u woken=%u\n",
				trial, enabled, samples[trial].hooks,
				atomic_load_explicit(&samples[trial].wake_count,
						     memory_order_relaxed));
			child_handoff_end(out, &token, phase, sync);
			diagnostic_stage("child", "retry_complete", trial, enabled);
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
		diagnostic_stage("child", "accepted_end_begin", trial, enabled);
		child_handoff_end(out, &token, phase, sync);
		diagnostic_stage("child", "accepted_complete", trial, enabled);
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
	unsigned config_lines_per_base = max_lines_per_base;
	unsigned long lead_cycles = 0;
	const char *mode_name = "data";
	unsigned expected_enabled_hooks = 1;
	int fifo = 0, probe_status = 0, skew_layout = 0, trace_icache = 0;
	int explicit_instruction = 0;
	int trace_stop_at_entry = 0, trace_allow_i_overflow = 0;
	int trace_explicit_disabled = 0;
	unsigned trace_trial = 0;
	enum sync_style sync = sync_pipe;
	struct shared_state *shared;
	volatile struct sample *samples;
	uint64_t icache_status_before = 0, icache_status_after = 0;
	char token = 'x';
	pid_t child;

	if (argc > 11) {
		fprintf(stderr, "usage: %s [off|data|data-late|instruction-select|instruction-wake|instruction-explicit|joint|joint-split|joint-split-one-hook|joint-follow-only] [delay-0..65535] [gap-0..255] [normal|fifo] [lead-cycles-0..1000000] [lines-per-base-1..8] [probe-status-0|1] [aligned|skew] [pipe|futex] [no-trace|trace-icache|trace-icache-entry|trace-icache-entry-prefix|trace-icache-entry-prefix-off]\n",
			argv[0]);
		return 2;
	}
	if (argc >= 2) {
		mode_name = argv[1];
		if (!strcmp(argv[1], "off"))
			mode = 0;
		else if (!strcmp(argv[1], "instruction-select"))
			mode = 3;
		else if (!strcmp(argv[1], "instruction-wake")) {
			/* Kernel mode four is the selection-time counter-only control.
			 * Mode six combines wakeup instruction replay with late physical
			 * data replay. Mode thirteen is the dedicated instruction-only
			 * successful-wakeup trigger and accounts for exactly one hook. */
			mode = 13;
		}
		else if (!strcmp(argv[1], "instruction-explicit")) {
			mode = 0;
			explicit_instruction = 1;
			expected_enabled_hooks = 0;
		}
		else if (!strcmp(argv[1], "joint"))
			mode = 10;
		else if (!strcmp(argv[1], "data-late"))
			mode = 11;
		else if (!strcmp(argv[1], "joint-split")
			 || !strcmp(argv[1], "joint-split-one-hook")
			 || !strcmp(argv[1], "joint-follow-only"))
			mode = 12;
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
	if (argc >= 9) {
		if (!strcmp(argv[8], "skew"))
			skew_layout = 1;
		else if (strcmp(argv[8], "aligned")) {
			fprintf(stderr, "invalid footprint layout: %s\n", argv[8]);
			return 2;
		}
	}
	if (argc >= 10) {
		if (!strcmp(argv[9], "futex"))
			sync = sync_futex;
		else if (strcmp(argv[9], "pipe")) {
			fprintf(stderr, "invalid synchronization style: %s\n", argv[9]);
			return 2;
		}
	}
	if (argc >= 11) {
		if (!strcmp(argv[10], "trace-icache"))
			trace_icache = 1;
		else if (!strcmp(argv[10], "trace-icache-entry")) {
			trace_icache = 1;
			trace_stop_at_entry = 1;
		}
		else if (!strcmp(argv[10], "trace-icache-entry-prefix")) {
			trace_icache = 1;
			trace_stop_at_entry = 1;
			trace_allow_i_overflow = 1;
		}
		else if (!strcmp(argv[10], "trace-icache-entry-prefix-off")) {
			trace_icache = 1;
			trace_stop_at_entry = 1;
			trace_allow_i_overflow = 1;
			trace_explicit_disabled = 1;
		}
		else if (strcmp(argv[10], "no-trace")) {
			fprintf(stderr, "invalid instruction trace mode: %s\n", argv[10]);
			return 2;
		}
	}
	if (trace_explicit_disabled && !explicit_instruction) {
		fputs("disabled-arm trace requires instruction-explicit mode\n", stderr);
		return 2;
	}
	if (trace_icache)
		trace_trial = warmup + (trace_explicit_disabled ? 0U
			: (unsigned)((mode != 0) || explicit_instruction
				     || trace_stop_at_entry));
	if (!strcmp(mode_name, "joint-follow-only"))
		config_lines_per_base = 0;
	diagnostic_progress = getenv("BP_TAGGED_REPLAY_DIAG") != NULL;
	if (fifo) {
		const struct sched_param parameter = {.sched_priority = 1};

		if (sched_setscheduler(0, SCHED_FIFO, &parameter))
			fail("sched_setscheduler FIFO");
	}

	shared = mmap(NULL, sizeof(*shared), PROT_READ | PROT_WRITE,
		       MAP_SHARED | MAP_ANONYMOUS, -1, 0);
	if (shared == MAP_FAILED || pipe(to_child) || pipe(to_parent))
		fail("shared memory or pipes");
	atomic_init(&shared->phase, futex_idle);
	samples = shared->samples;
	printf("TAGGED_REPLAY_CONFIG mode=%s lines=%u slot=%u delay=%u gap=%u policy=%s lead_cycles=%lu layout=%s probe_status=%u sync=%s kernel_mode=%u expected_hooks=%u trace_icache=%u trace_stop=%s trace_prefix=%u trace_arm=%s\n",
	       mode_name,
	       bases * lines_per_base, replay_slot,
	       delay, gap, fifo ? "fifo" : "normal", lead_cycles,
	       skew_layout ? "skew" : "aligned", probe_status,
	       sync == sync_futex ? "futex" : "pipe", mode,
	       expected_enabled_hooks, trace_icache,
	       trace_stop_at_entry ? "entry" : "after-load",
	       trace_allow_i_overflow,
	       trace_icache ? (trace_explicit_disabled ? "disabled" : "enabled")
		: "none");
	if (!strcmp(mode_name, "instruction-wake")
	    || !strcmp(mode_name, "instruction-explicit"))
		icache_status_before = icache_prefix_status();
	child = fork();
	if (child < 0)
		fail("fork");
	if (!child) {
		close(to_child[1]);
		close(to_parent[0]);
		child_run(to_child[0], to_parent[1], samples, mode, delay, gap,
			  lines_per_base, config_lines_per_base, probe_status,
			  skew_layout, trace_stop_at_entry,
			  expected_enabled_hooks, explicit_instruction,
			  &shared->phase, sync);
		return 0;
	}
	close(to_child[0]);
	close(to_parent[1]);
	for (unsigned trial = 0; trial < trials;) {
		uint64_t lead_start;
		int woken;
		unsigned enabled = (mode || explicit_instruction)
			? trial_enabled(trial) : 0;

		diagnostic_stage("parent", "wait_ready", trial, enabled);
		if (sync == sync_pipe)
			transfer(to_parent[0], &token, 0);
		else {
			futex_wait_for(&shared->phase, futex_child_ready);
			/* The ready store precedes the child's FUTEX_WAIT. Yield outside
			 * the timed interval so the single-core child can enter the kernel
			 * wait queue before the measured wake. The returned wake count is
			 * still the fail-closed proof that this scheduling step succeeded.
			 */
			if (sched_yield())
				fail("yield before tagged replay wake");
		}
		diagnostic_stage("parent", "ready", trial, enabled);
		/* Entry-bounded A/B diagnostics always use measured trial one so the
		 * scheduler phase is matched even when the replay mode is disabled.
		 * Preserve trial zero for the original complete replay-off extractor.
		 */
		if (trace_icache && trial == trace_trial) {
			trace_control(2);
			samples[trial].trace_start = cycle();
			trace_control(3);
		}
		samples[trial].launch = cycle();
		if (explicit_instruction
		    && prctl(PR_BP_PREVIEW_ICACHE_TRIGGER, enabled,
			     0UL, 0UL, 0UL))
			fail("explicit instruction-prefix trigger");
		if (sync == sync_pipe) {
			transfer(to_child[1], &token, 1);
			woken = 1;
		} else {
			woken = futex_set_wake(&shared->phase, futex_parent_go);
		}
		atomic_store_explicit(&samples[trial].wake_count, woken,
				      memory_order_release);
		diagnostic_stage("parent", "wake_complete", trial, enabled);
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
		if (sync == sync_pipe) {
			transfer(to_parent[0], &token, 0);
		} else {
			futex_wait_for(&shared->phase, futex_child_done);
		}
		diagnostic_stage("parent", "child_done", trial, enabled);
		samples[trial].returned = cycle();
		if (sync == sync_futex) {
			futex_set_wake(&shared->phase, futex_parent_ack);
			diagnostic_stage("parent", "ack_complete", trial, enabled);
			/* Do not wait for idle here. The child may pass through idle and
			 * publish child-ready for the next attempt before this task runs,
			 * making a transient-state wait deadlock. The next loop's stable
			 * child-ready wait is the acknowledgement barrier; waitpid covers
			 * the final accepted attempt.
			 */
		}
		if (samples[trial].accepted)
			trial++;
	}
	if (waitpid(child, &status, 0) != child)
		fail("waitpid");
	if (!WIFEXITED(status) || WEXITSTATUS(status)) {
		fprintf(stderr, "tagged replay child failed: status=%d\n", status);
		return 1;
	}
	if (trace_icache) {
		const uint64_t raw_status = samples[trace_trial].trace_status;
		const unsigned icount = raw_status & 0x1ff;
		const unsigned dcount = (raw_status >> 9) & 0x1ff;
		const unsigned ioverflow = (raw_status >> 18) & 1;
		const unsigned doverflow = (raw_status >> 19) & 1;
		const unsigned armed = (raw_status >> 20) & 1;
		const uint32_t start = (uint32_t)samples[trace_trial].trace_start;

		printf("TAGGED_REPLAY_ITRACE_HEADER trial=%u enabled=%u i_count=%u d_count=%u i_overflow=%u d_overflow=%u armed=%u status=0x%016llx\n",
		       trace_trial - warmup, samples[trace_trial].enabled,
		       icount, dcount, ioverflow, doverflow, armed,
		       (unsigned long long)raw_status);
		if (armed || (!trace_allow_i_overflow && ioverflow) || doverflow || !icount
		    || icount > TRACE_DEPTH || dcount > TRACE_DEPTH) {
			fputs("TAGGED_REPLAY_ITRACE_FAIL invalid recorder status\n", stderr);
			return 1;
		}
		for (unsigned index = 0; index < icount; index++) {
			const uint64_t record = trace_record(index);
			const uint32_t relative = (uint32_t)(record >> 32) - start;
			const uint64_t paddr = (record & UINT64_C(0x0fffffff)) << 6;

			printf("TAGGED_REPLAY_ITRACE_RECORD index=%u relative=%u paddr=0x%09llx raw=0x%016llx\n",
			       index, relative, (unsigned long long)paddr,
			       (unsigned long long)record);
		}
		if (trace_allow_i_overflow)
			printf("TAGGED_REPLAY_ITRACE_PREFIX_PASS truncated=%u records=%u\n",
			       ioverflow, icount);
		else
			printf("TAGGED_REPLAY_ITRACE_PASS records=%u\n", icount);
	}
	if (!strcmp(mode_name, "instruction-wake")
	    || !strcmp(mode_name, "instruction-explicit")) {
		icache_status_after = icache_prefix_status();
		printf("TAGGED_REPLAY_ICACHE_STATUS before=0x%016llx after=0x%016llx\n",
		       (unsigned long long)icache_status_before,
		       (unsigned long long)icache_status_after);
	}
	for (unsigned trial = warmup; trial < trials; trial++) {
		const volatile struct sample *s = &samples[trial];

		if (!(s->launch <= s->entry && s->entry <= s->after_load
		      && s->after_load <= s->done && s->done <= s->returned)) {
			fprintf(stderr, "nonmonotonic tagged replay sample: %u\n", trial);
			return 1;
		}
		printf("TAGGED_REPLAY trial=%u enabled=%u hooks=%u woken=%u hook_cycles=%lu admitted=%u filtered=%u triggers=%u dropped=%u wake_to_entry=%llu load_cycles=%llu wake_to_load=%llu roundtrip=%llu preblock_status=0x%016llx preblock_probe_cycles=%lu entry_probe_status=0x%016llx entry_probe_cycles=%lu\n",
		       trial - warmup, s->enabled, s->hooks,
		       atomic_load_explicit(&s->wake_count, memory_order_relaxed),
		       s->hook_cycles,
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
	print_tail_partitions(samples);
	puts("TAGGED_REPLAY_PARENT PASS");
	return 0;
}

static void print_tail_partitions(volatile struct sample *samples)
{
	/* These timestamps already bracket the accepted child bookkeeping and
	 * reply path. Emit their partitions only after all timing and original row
	 * output is complete so localization cannot perturb the handoff itself.
	 */
	for (unsigned trial = warmup; trial < trials; trial++) {
		const volatile struct sample *s = &samples[trial];

		printf("TAGGED_REPLAY_TAIL trial=%u enabled=%u child_post_load=%llu return_handoff=%llu post_load_total=%llu\n",
		       trial - warmup, s->enabled,
		       (unsigned long long)(s->done - s->after_load),
		       (unsigned long long)(s->returned - s->done),
		       (unsigned long long)(s->returned - s->after_load));
	}
}
