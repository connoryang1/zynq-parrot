#define _GNU_SOURCE

/* Measure four scheduler hints against four first-use target loads.
 * CSR 0x805 records demand misses separately from physical preview delivery
 * events. Every target line has a separate 64-byte index, and the peer
 * snapshots the recorder after each load.
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
#define PR_BP_PREVIEW_GET_COUNT 0x42505057
#define PR_BP_PREVIEW_GET_GUARD 0x42505058

enum { modes = 3, repetitions = 16, trials = modes * repetitions,
       preview_lines = 4, line_groups = 16, page_lines = 64,
       guard_outcomes = 5 };
enum { preview_off, preview_exact, preview_stale };

struct line { uint64_t word[8]; };
static volatile struct line target_lines[page_lines]
  __attribute__((aligned(4096)));
static volatile struct line stale_lines[page_lines]
  __attribute__((aligned(4096)));
static volatile unsigned char eviction[8 * 4096]
  __attribute__((aligned(4096)));
static _Atomic uint64_t sink;
static _Atomic uint32_t phase, done, ready;
static unsigned trial_mode[trials];
static uint64_t entry_cycle[trials], load_done_cycle[trials];
static uint64_t value[trials][preview_lines];
static uint64_t miss_status[trials][preview_lines + 1];
static uint64_t preview_status_entry[trials], preview_status_post[trials];
static uint64_t publication_records[trials][8];
static unsigned publication_count[trials], publication_overflow[trials];
static uint64_t removal_records[trials][16];
static unsigned removal_count[trials];
static unsigned long hook_count[trials];
static unsigned long guard_count[trials][guard_outcomes];

static unsigned line_index(unsigned trial, unsigned lane)
{
  return preview_lines * (trial % line_groups) + lane;
}

static inline void miss_trace_disarm(void)
{
  __asm__ volatile("csrw 0x805, zero" : : : "memory");
}

static inline void preview_trace_clear(void)
{
  // Retain publication addresses before the peer arms demand recording.
  __asm__ volatile("csrw 0x805, %0" : : "r"(6ULL) : "memory");
}

static inline uint64_t preview_trace_status(void)
{
  uint64_t status;
  __asm__ volatile("csrr %0, 0x805" : "=r"(status) : : "memory");
  return status;
}

static inline unsigned preview_event_count(uint64_t status, unsigned shift)
{
  return (unsigned)((status >> shift) & 0xff);
}

static inline uint64_t miss_trace_record(unsigned index)
{
  const uint64_t selector = 0x100U | index;
  uint64_t value;
  __asm__ volatile(
    "csrw 0x806, %1\n"
    "nop\n"
    "nop\n"
    "nop\n"
    "csrr %0, 0x807\n"
    : "=r"(value) : "r"(selector) : "memory");
  return value;
}

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
  unsigned long addr[preview_lines] = {0};
  if (trial < trials) {
    for (unsigned lane = 0; lane < preview_lines; ++lane) {
      unsigned index = line_index(trial, lane);
      if (trial_mode[trial] == preview_exact)
        addr[lane] = (unsigned long)&target_lines[index].word[0];
      else if (trial_mode[trial] == preview_stale)
        addr[lane] = (unsigned long)&stale_lines[index].word[0];
    }
  }
  if (prctl(PR_BP_PREVIEW_SET, addr[0], addr[1], addr[2], addr[3]))
    fail("preview prctl");
  if (trial < trials) {
    uint64_t total = 0;
    for (unsigned lane = 0; lane < preview_lines; ++lane) {
      unsigned index = line_index(trial, lane);
      total += target_lines[index].word[0] ^ stale_lines[index].word[0];
    }
    /* Warm the translation in the peer before the source evicts data. */
    atomic_store_explicit(&sink, total, memory_order_relaxed);
  }
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
    preview_status_entry[index] = preview_trace_status();
    unsigned i0 = line_index(index, 0), i1 = line_index(index, 1);
    unsigned i2 = line_index(index, 2), i3 = line_index(index, 3);
    uint64_t s0, s1, s2, s3, s4, v0, v1, v2, v3;
    __asm__ volatile(
      "li t2, 5\n"
      "csrw 0x805, t2\n"
      "nop\n"
      "nop\n"
      "nop\n"
      "csrr %0, 0x805\n"
      "ld %1, 0(%9)\n"
      "csrr %2, 0x805\n"
      "ld %3, 0(%10)\n"
      "csrr %4, 0x805\n"
      "ld %5, 0(%11)\n"
      "csrr %6, 0x805\n"
      "ld %7, 0(%12)\n"
      /* The D-cache removal event crosses a half-cycle before CSR capture. */
      "nop\nnop\nnop\nnop\nnop\nnop\n"
      "csrr %8, 0x805\n"
      : "=&r"(s0), "=&r"(v0), "=&r"(s1), "=&r"(v1), "=&r"(s2),
        "=&r"(v2), "=&r"(s3), "=&r"(v3), "=&r"(s4)
      : "r"(&target_lines[i0].word[0]), "r"(&target_lines[i1].word[0]),
        "r"(&target_lines[i2].word[0]), "r"(&target_lines[i3].word[0])
      : "t2", "memory");
    load_done_cycle[index] = global_cycle();
    value[index][0] = v0; value[index][1] = v1;
    value[index][2] = v2; value[index][3] = v3;
    miss_status[index][0] = s0; miss_status[index][1] = s1;
    miss_status[index][2] = s2; miss_status[index][3] = s3;
    miss_status[index][4] = s4;
    publication_count[index] = (unsigned)((s4 >> 53) & 0xf);
    publication_overflow[index] = (unsigned)((s4 >> 57) & 1);
    removal_count[index] = (unsigned)((s4 >> 59) & 0x1f);
    for (unsigned record = 0;
         record < removal_count[index] && record < 16; ++record)
      removal_records[index][record] = miss_trace_record(232 + record);
    for (unsigned record = 0;
         record < publication_count[index] && record < 8; ++record)
      publication_records[index][record] = miss_trace_record(248 + record);
    int count = prctl(PR_BP_PREVIEW_GET_COUNT, 0UL, 0UL, 0UL, 0UL);
    if (count < 0) fail("preview hook count prctl");
    hook_count[index] = (unsigned long)count;
    for (unsigned reason = 0; reason < guard_outcomes; ++reason) {
      count = prctl(PR_BP_PREVIEW_GET_GUARD, reason, 0UL, 0UL, 0UL);
      if (count < 0) fail("preview guard count prctl");
      guard_count[index][reason] = (unsigned long)count;
    }
    preview_status_post[index] = preview_trace_status();
    register_next(trial);
    atomic_store_explicit(&done, trial, memory_order_release);
    futex_wake(&done);
  }
  return NULL;
}

static void prepare_cold_line(unsigned index)
{
  uint64_t total = 0;
  for (unsigned lane = 0; lane < preview_lines; ++lane) {
    unsigned line = line_index(index, lane);
    total += target_lines[line].word[0] + stale_lines[line].word[0];
  }
  /* Eight 4 KiB-spaced eviction pages exceed L1 associativity when combined
   * with target and stale pages, while using two fewer DTLB entries. */
  for (unsigned page = 0; page < 8; ++page)
    for (unsigned set = 0; set < page_lines; ++set)
      total += eviction[page * 4096 + set * 64];
  /* Refresh only the target page's DTLB entry after eviction. This probe
   * line is outside the four demand lines; the off control must still miss
   * on all four for the comparison to be valid. */
  unsigned probe = (line_index(index, 0) + preview_lines) % page_lines;
  total += target_lines[probe].word[0];
  atomic_store_explicit(&sink, total, memory_order_relaxed);
  __asm__ volatile("fence rw, rw" : : : "memory");
}

int main(void)
{
  for (unsigned trial = 0; trial < trials; ++trial)
    trial_mode[trial] = (trial + trial / modes) % modes;
  for (unsigned trial = 0; trial < page_lines; ++trial) {
    target_lines[trial].word[0] = 0x123456789abcdef0ULL + trial;
    stale_lines[trial].word[0] = 0xfedcba9876543210ULL + trial;
  }
  for (unsigned page = 0; page < 8; ++page)
    eviction[page * 4096] = (unsigned char)(page + 1);
  int cpu = pin_first_cpu();
  pthread_t peer;
  int rc = pthread_create(&peer, NULL, peer_main, NULL);
  if (rc) { errno = rc; fail("pthread create"); }
  futex_wait_until(&ready, 1);
  for (unsigned trial = 1; trial <= trials; ++trial) {
    prepare_cold_line(trial - 1);
    preview_trace_clear();
    uint64_t begin = global_cycle();
    atomic_store_explicit(&phase, trial, memory_order_release);
    futex_wake(&phase);
    uint64_t wake_end = global_cycle();
    futex_wait_until(&done, trial);
    miss_trace_disarm();
    unsigned index = trial - 1;
    for (unsigned lane = 0; lane < preview_lines; ++lane) {
      unsigned line = line_index(index, lane);
      if (value[index][lane] != 0x123456789abcdef0ULL + line) {
        fputs("target checksum failed\n", stderr);
        return EXIT_FAILURE;
      }
    }
    printf("SCHED_PREVIEW mode=%u trial=%u cpu=%d wake=%llu entry=%llu load=%llu roundtrip=%llu\n",
           trial_mode[index], trial, cpu,
           (unsigned long long)(wake_end - begin),
           (unsigned long long)(entry_cycle[index] - begin),
           (unsigned long long)(load_done_cycle[index] - begin),
           (unsigned long long)(global_cycle() - begin));
    unsigned misses[preview_lines], armed = 1, overflow = 0;
    for (unsigned lane = 0; lane < preview_lines; ++lane) {
      unsigned before = (unsigned)((miss_status[index][lane] >> 9) & 0x1ff);
      unsigned after = (unsigned)((miss_status[index][lane + 1] >> 9) & 0x1ff);
      if (after < before) fail("miss counter reversed");
      misses[lane] = after - before;
    }
    for (unsigned lane = 0; lane <= preview_lines; ++lane) {
      armed &= (unsigned)(miss_status[index][lane] >> 20) & 1;
      overflow |= (unsigned)(miss_status[index][lane] >> 19) & 1;
    }
    printf("SCHED_PREVIEW_MISS4 mode=%u trial=%u d0=%u d1=%u d2=%u d3=%u total=%u armed=%u overflow=%u\n",
           trial_mode[index], trial, misses[0], misses[1], misses[2], misses[3],
           misses[0] + misses[1] + misses[2] + misses[3], armed, overflow);
    printf("SCHED_PREVIEW_HOOK mode=%u trial=%u count=%lu\n",
           trial_mode[index], trial, hook_count[index]);
    printf("SCHED_PREVIEW_GUARD mode=%u trial=%u selected=%lu idle=%lu different_mm=%lu descriptor=%lu empty=%lu\n",
           trial_mode[index], trial, guard_count[index][0],
           guard_count[index][1], guard_count[index][2],
           guard_count[index][3], guard_count[index][4]);
    const uint64_t entry_status = preview_status_entry[index];
    const uint64_t demand_status = miss_status[index][0];
    const uint64_t load_status = miss_status[index][preview_lines];
    const uint64_t post_status = preview_status_post[index];
    printf("SCHED_PREVIEW_EVENTS mode=%u trial=%u entry=%u,%u,%u,%u demand=%u,%u,%u,%u load=%u,%u,%u,%u post=%u,%u,%u,%u\n",
           trial_mode[index], trial,
           preview_event_count(entry_status, 21), preview_event_count(entry_status, 29),
           preview_event_count(entry_status, 37), preview_event_count(entry_status, 45),
           preview_event_count(demand_status, 21), preview_event_count(demand_status, 29),
           preview_event_count(demand_status, 37), preview_event_count(demand_status, 45),
           preview_event_count(load_status, 21), preview_event_count(load_status, 29),
           preview_event_count(load_status, 37), preview_event_count(load_status, 45),
           preview_event_count(post_status, 21), preview_event_count(post_status, 29),
           preview_event_count(post_status, 37), preview_event_count(post_status, 45));
    printf("SCHED_PREVIEW_PUBLICATIONS mode=%u trial=%u count=%u overflow=%u records=%016llx,%016llx,%016llx,%016llx,%016llx,%016llx,%016llx,%016llx\n",
           trial_mode[index], trial, publication_count[index],
           publication_overflow[index],
           (unsigned long long)publication_records[index][0],
           (unsigned long long)publication_records[index][1],
           (unsigned long long)publication_records[index][2],
           (unsigned long long)publication_records[index][3],
           (unsigned long long)publication_records[index][4],
           (unsigned long long)publication_records[index][5],
           (unsigned long long)publication_records[index][6],
           (unsigned long long)publication_records[index][7]);
    printf("SCHED_PREVIEW_REMOVALS mode=%u trial=%u count=%u overflow=%u\n",
           trial_mode[index], trial, removal_count[index],
           publication_overflow[index]);
    for (unsigned record = 0;
         record < removal_count[index] && record < 16; ++record) {
      uint64_t event = removal_records[index][record];
      printf("SCHED_PREVIEW_REMOVAL mode=%u trial=%u index=%u cycle=%u reason=%u paddr=0x%llx\n",
             trial_mode[index], trial, record, (unsigned)(event >> 32),
             (unsigned)((event >> 30) & 3),
             (unsigned long long)((event & UINT64_C(0x3fffffff)) << 4));
    }
    if (!overflow) {
      for (unsigned lane = 0; lane < preview_lines; ++lane) {
        unsigned first = (unsigned)((miss_status[index][lane] >> 9) & 0x1ff);
        unsigned last = (unsigned)((miss_status[index][lane + 1] >> 9) & 0x1ff);
        for (unsigned record_index = first; record_index < last; ++record_index) {
          uint64_t record = miss_trace_record(record_index);
          printf("SCHED_PREVIEW_RECORD mode=%u trial=%u lane=%u index=%u cycle=%u paddr=0x%llx msg=%u\n",
                 trial_mode[index], trial, lane, record_index,
                 (unsigned)(record >> 32),
                 (unsigned long long)((record & UINT64_C(0x0fffffff)) << 6),
                 (unsigned)((record >> 28) & 0xf));
        }
      }
    }
  }
  rc = pthread_join(peer, NULL);
  if (rc) { errno = rc; fail("pthread join"); }
  puts("SCHED_PREVIEW PASS");
  return EXIT_SUCCESS;
}
