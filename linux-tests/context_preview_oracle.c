#define _GNU_SOURCE

/* Measure oracle target-data hints before an actual Linux futex handoff.
 * Context 1 is a preview helper in the source process; the peer Linux task
 * remains an ordinary pthread and consumes the data after scheduling.
 */
#include <errno.h>
#include <linux/futex.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

#include "../testing/mt_seed.h"
#include "../software/include/bp_prefetch.h"

#if !defined(__riscv) || __riscv_xlen != 64
#error "The Linux preview oracle requires RV64 BlackParrot"
#endif
#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS < 2
#error "The preview oracle requires two resident slots and a peer context"
#endif

enum { modes = 9, repetitions = 16, trials = modes * repetitions };

struct line { uint64_t word[8]; };
static const volatile struct line target_lines[4]
  __attribute__((aligned(4096), used)) = {
    {{0x100}}, {{0x101}}, {{0x102}}, {{0x103}}
  };
static const volatile struct line stale_lines[4]
  __attribute__((aligned(4096), used)) = {
    {{0x200}}, {{0x201}}, {{0x202}}, {{0x203}}
  };
static volatile unsigned char eviction[10 * 4096]
  __attribute__((aligned(4096), used));
static volatile uint64_t eviction_sink;
static volatile uint64_t preview_done;

struct peer_result {
  uint64_t sum;
  uint64_t entry_cycle;
  uint64_t load_cycles;
  uint64_t line_cycles[4];
  uint64_t context;
};
static struct peer_result peer_results[trials];
static unsigned trial_mode[trials];
static _Atomic uint32_t phase;
static _Atomic uint32_t done;
static _Atomic uint32_t ready;
static int per_load_mode;

/* a0=target lines, a1=completion flag, a2=mode, a3=stale lines. */
static __attribute__((naked, noinline, noreturn, used, aligned(64)))
void preview_helper(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n.option norelax\n"
    "li t2, 1\nbeq a2, t2, 2f\n"
    "mv t0, a0\n"
    "li t2, 3\nbne a2, t2, 1f\nmv t0, a3\n"
    "1:\n"
    BP_PREFETCH_R_ASM("t0")
    "addi t0, t0, 64\n"
    BP_PREFETCH_R_ASM("t0")
    "addi t0, t0, 64\n"
    BP_PREFETCH_R_ASM("t0")
    "addi t0, t0, 64\n"
    BP_PREFETCH_R_ASM("t0")
    "2:\nli t2, 1\nsd t2, 0(a1)\nfence rw, rw\n"
    "csrwi 0x800, 0\n"
    "3: j 3b\n.option pop\n"
    ::: "memory");
}

static inline uint64_t global_cycle(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
  return value;
}

static inline uint64_t current_context(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0x800" : "=r"(value) : : "memory");
  return value;
}

static void fail(const char *what)
{
  perror(what);
  exit(EXIT_FAILURE);
}

static void check_pthread(int rc, const char *what)
{
  if (rc) {
    errno = rc;
    fail(what);
  }
}

static void futex_wait_until(_Atomic uint32_t *word, uint32_t wanted)
{
  for (;;) {
    uint32_t observed = atomic_load_explicit(word, memory_order_acquire);
    if (observed >= wanted) return;
    if (syscall(SYS_futex, (uint32_t *)word, FUTEX_WAIT_PRIVATE,
                observed, NULL, NULL, 0) < 0 && errno != EAGAIN && errno != EINTR)
      fail("futex wait");
  }
}

static void futex_wake(_Atomic uint32_t *word)
{
  if (syscall(SYS_futex, (uint32_t *)word, FUTEX_WAKE_PRIVATE, 1,
              NULL, NULL, 0) < 0)
    fail("futex wake");
}

static int pin_first_cpu(void)
{
  cpu_set_t allowed, selected;
  if (sched_getaffinity(0, sizeof(allowed), &allowed)) fail("get affinity");
  int cpu = -1;
  for (int i = 0; i < CPU_SETSIZE; ++i)
    if (CPU_ISSET(i, &allowed)) { cpu = i; break; }
  if (cpu < 0) fail("empty affinity");
  CPU_ZERO(&selected);
  CPU_SET(cpu, &selected);
  if (sched_setaffinity(0, sizeof(selected), &selected)) fail("set affinity");
  return cpu;
}

static void *peer_main(void *unused)
{
  (void)unused;
  atomic_store_explicit(&ready, 1, memory_order_release);
  futex_wake(&ready);
  for (unsigned trial = 1; trial <= trials; ++trial) {
    futex_wait_until(&phase, trial);
    const unsigned mode = trial_mode[trial - 1];
    const int reverse_demand = mode == 7 || mode == 8;
    peer_results[trial - 1].context = current_context();
    uint64_t sum = 0;
    if (per_load_mode) {
      uint64_t marks[5];
      marks[0] = global_cycle();
      for (unsigned step = 0; step < 4; ++step) {
        unsigned i = reverse_demand ? 3 - step : step;
        sum += target_lines[i].word[0];
        marks[step + 1] = global_cycle();
      }
      peer_results[trial - 1].entry_cycle = marks[0];
      peer_results[trial - 1].load_cycles = marks[4] - marks[0];
      for (unsigned step = 0; step < 4; ++step) {
        unsigned i = reverse_demand ? 3 - step : step;
        peer_results[trial - 1].line_cycles[i]
          = marks[step + 1] - marks[step];
      }
    } else {
      uint64_t begin = global_cycle();
      peer_results[trial - 1].entry_cycle = begin;
      for (unsigned step = 0; step < 4; ++step) {
        unsigned i = reverse_demand ? 3 - step : step;
        sum += target_lines[i].word[0];
      }
      peer_results[trial - 1].load_cycles = global_cycle() - begin;
    }
    peer_results[trial - 1].sum = sum;
    atomic_store_explicit(&done, trial, memory_order_release);
    futex_wake(&done);
  }
  return NULL;
}

static void prepare_cold_lines(void)
{
  uint64_t sum = 0;
  for (unsigned i = 0; i < 4; ++i)
    sum += target_lines[i].word[0];
  for (unsigned page = 0; page < 10; ++page)
    for (unsigned set = 0; set < 4; ++set)
      sum += eviction[page * 4096 + set * 64];
  eviction_sink = sum;
  __asm__ volatile("fence rw, rw" : : : "memory");
}

static void source_work(void)
{
  __asm__ volatile("li t0, 128\n1: addi t0, t0, -1\nbnez t0, 1b\n"
                   : : : "t0", "memory");
}

int main(int argc, char **argv)
{
  if (argc == 2 && !strcmp(argv[1], "--per-load"))
    per_load_mode = 1;
  else if (argc != 1) {
    fputs("usage: context_preview_oracle [--per-load]\n", stderr);
    return EXIT_FAILURE;
  }
  /* Give each eviction page a distinct backing page without storing 40 KiB
   * of zeros in the serial-transfer ELF. */
  for (unsigned page = 0; page < 10; ++page)
    eviction[page * 4096] = (unsigned char)(page + 1);
  int cpu = pin_first_cpu();
  pthread_t peer;
  check_pthread(pthread_create(&peer, NULL, peer_main, NULL), "create peer");
  futex_wait_until(&ready, 1);
  if (current_context() != 0) {
    fputs("source did not start in context 0\n", stderr);
    return EXIT_FAILURE;
  }

  int helper_bound = 0;
  for (unsigned repeat = 0; repeat < repetitions; ++repeat) {
    for (unsigned slot = 0; slot < modes; ++slot) {
      const unsigned mode = (slot + repeat) % modes;
      const unsigned trial = repeat * modes + slot + 1;
      prepare_cold_lines();
      preview_done = 0;
      if (mode >= 1 && mode <= 3) {
        seed_reg(1, 10, (uintptr_t)target_lines);
        seed_reg(1, 11, (uintptr_t)&preview_done);
        seed_reg(1, 12, mode);
        seed_reg(1, 13, (uintptr_t)stale_lines);
        if (!helper_bound) {
          seed_npc_rebind(1, (uintptr_t)preview_helper);
          helper_bound = 1;
        } else {
          seed_npc(1, (uintptr_t)preview_helper);
        }
      }
      __asm__ volatile("fence rw, rw" : : : "memory");
      uint64_t begin = global_cycle();
      if (mode >= 1 && mode <= 3) {
        __asm__ volatile("csrwi 0x800, 1" : : : "memory");
        if (preview_done != 1 || current_context() != 0) {
          fputs("preview helper failed\n", stderr);
          return EXIT_FAILURE;
        }
      }
      if (mode == 4 || mode == 5 || mode == 8) {
        const volatile struct line *lines = mode == 5 ? stale_lines : target_lines;
        for (unsigned i = 0; i < 4; ++i)
          bp_prefetch_r(&lines[i].word[0]);
      }
      if (mode == 6)
        for (int i = 3; i >= 0; --i)
          bp_prefetch_r(&target_lines[i].word[0]);
      uint64_t preview_end = global_cycle();
      source_work();
      uint64_t work_end = global_cycle();
      trial_mode[trial - 1] = mode;
      atomic_store_explicit(&phase, trial, memory_order_release);
      futex_wake(&phase);
      uint64_t wake_end = global_cycle();
      futex_wait_until(&done, trial);
      uint64_t total_cycles = global_cycle() - begin;
      if (peer_results[trial - 1].sum != 0x406
          || peer_results[trial - 1].context != 0
          || current_context() != 0) {
        fputs("peer checksum or context failed\n", stderr);
        return EXIT_FAILURE;
      }
      printf("CONTEXT_PREVIEW mode=%u repeat=%u total=%llu preview=%llu work=%llu wake=%llu peer_entry=%llu peer_load=%llu cpu=%d\n",
             mode, repeat, (unsigned long long)total_cycles,
             (unsigned long long)(preview_end - begin),
             (unsigned long long)(work_end - begin),
             (unsigned long long)(wake_end - begin),
             (unsigned long long)(peer_results[trial - 1].entry_cycle - begin),
             (unsigned long long)peer_results[trial - 1].load_cycles, cpu);
      if (per_load_mode)
        printf("PREVIEW_LOADS mode=%u repeat=%u l0=%llu l1=%llu l2=%llu l3=%llu\n",
               mode, repeat,
               (unsigned long long)peer_results[trial - 1].line_cycles[0],
               (unsigned long long)peer_results[trial - 1].line_cycles[1],
               (unsigned long long)peer_results[trial - 1].line_cycles[2],
               (unsigned long long)peer_results[trial - 1].line_cycles[3]);
    }
  }
  check_pthread(pthread_join(peer, NULL), "join peer");
  puts("CONTEXT_PREVIEW PASS");
  return EXIT_SUCCESS;
}
