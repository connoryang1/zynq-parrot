#define _GNU_SOURCE

/* Exercise the scheduler-owned same-mm preview on a real futex handoff.
 * Every trial has the same cold target and handoff; only the peer's registered
 * preview address changes between disabled, exact, and stale controls.
 */
#include <errno.h>
#include <linux/futex.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <unistd.h>

#if !defined(__riscv) || __riscv_xlen != 64
#error "This benchmark requires RV64 BlackParrot"
#endif

#define PR_BP_PREVIEW_SET 0x42505056

enum { modes = 3, repetitions = 16, trials = modes * repetitions };
enum { preview_off, preview_exact, preview_stale };

struct line { uint64_t word[8]; };
static const volatile struct line target_line __attribute__((aligned(4096))) =
  { { 0x123456789abcdef0ULL } };
static const volatile struct line stale_line __attribute__((aligned(4096))) =
  { { 0xfedcba9876543210ULL } };
static volatile unsigned char eviction[10 * 4096]
  __attribute__((aligned(4096)));
static _Atomic uint64_t sink;
static _Atomic uint32_t phase, done, ready;
static unsigned trial_mode[trials];
static uint64_t entry_cycle[trials], load_done_cycle[trials], value[trials];

static inline uint64_t global_cycle(void)
{
  uint64_t cycle;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(cycle) : : "memory");
  return cycle;
}

static void fail(const char *what)
{
  perror(what);
  exit(EXIT_FAILURE);
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

static void register_next(unsigned trial)
{
  unsigned long addr = 0;
  if (trial < trials) {
    if (trial_mode[trial] == preview_exact)
      addr = (unsigned long)&target_line.word[0];
    else if (trial_mode[trial] == preview_stale)
      addr = (unsigned long)&stale_line.word[0];
  }
  if (prctl(PR_BP_PREVIEW_SET, addr, 0UL, 0UL, 0UL)) fail("preview prctl");
  /* A prior data access makes the target translation eligible for the
   * hardware's DTLB-hit-only hint path. The source later evicts the line. */
  atomic_store_explicit(&sink, target_line.word[0] ^ stale_line.word[0],
                        memory_order_relaxed);
}

static void *peer_main(void *unused)
{
  (void)unused;
  register_next(0);
  atomic_store_explicit(&ready, 1, memory_order_release);
  futex_wake(&ready);
  for (unsigned trial = 1; trial <= trials; ++trial) {
    futex_wait_until(&phase, trial);
    const unsigned index = trial - 1;
    entry_cycle[index] = global_cycle();
    value[index] = target_line.word[0];
    load_done_cycle[index] = global_cycle();
    register_next(trial);
    atomic_store_explicit(&done, trial, memory_order_release);
    futex_wake(&done);
  }
  return NULL;
}

static void prepare_cold_line(void)
{
  uint64_t total = target_line.word[0] + stale_line.word[0];
  for (unsigned page = 0; page < 10; ++page)
    for (unsigned set = 0; set < 4; ++set)
      total += eviction[page * 4096 + set * 64];
  atomic_store_explicit(&sink, total, memory_order_relaxed);
  __asm__ volatile("fence rw, rw" : : : "memory");
}

int main(void)
{
  for (unsigned trial = 0; trial < trials; ++trial)
    trial_mode[trial] = (trial + trial / modes) % modes;
  for (unsigned page = 0; page < 10; ++page)
    eviction[page * 4096] = (unsigned char)(page + 1);
  int cpu = pin_first_cpu();
  pthread_t peer;
  int rc = pthread_create(&peer, NULL, peer_main, NULL);
  if (rc) { errno = rc; fail("pthread create"); }
  futex_wait_until(&ready, 1);
  for (unsigned trial = 1; trial <= trials; ++trial) {
    prepare_cold_line();
    uint64_t begin = global_cycle();
    atomic_store_explicit(&phase, trial, memory_order_release);
    futex_wake(&phase);
    uint64_t wake_end = global_cycle();
    futex_wait_until(&done, trial);
    unsigned index = trial - 1;
    if (value[index] != 0x123456789abcdef0ULL) {
      fputs("target checksum failed\n", stderr);
      return EXIT_FAILURE;
    }
    printf("SCHED_PREVIEW mode=%u trial=%u cpu=%d wake=%llu entry=%llu load=%llu roundtrip=%llu\n",
           trial_mode[index], trial, cpu,
           (unsigned long long)(wake_end - begin),
           (unsigned long long)(entry_cycle[index] - begin),
           (unsigned long long)(load_done_cycle[index] - begin),
           (unsigned long long)(global_cycle() - begin));
  }
  rc = pthread_join(peer, NULL);
  if (rc) { errno = rc; fail("pthread join"); }
  puts("SCHED_PREVIEW PASS");
  return EXIT_SUCCESS;
}
