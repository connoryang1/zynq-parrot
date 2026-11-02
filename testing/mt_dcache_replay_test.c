/* Validate tagged physical-data replay through the D-cache's L1 lookup path.
 * The default case leaves 32 host-initialized target lines cold and requires lower-cache admission;
 * diagnostic mode one dirties them in L1 and requires all hints to be filtered,
 * while mode two immediately demands the cold lines during replay.
 * All cases verify that replay does not corrupt target data.
 */
#include <stdint.h>
#include "bp_utils.h"

#define REPLAY_LINES 32
#define REPLAY_SLOT 2
#define REPLAY_DELAY 12
#define REPLAY_GAP 2

struct cache_line { uint64_t value, padding[7]; };

static volatile struct cache_line targets[REPLAY_LINES]
  __attribute__((aligned(64), used)) = {
    [0 ... REPLAY_LINES-1] = {.value = 7}
  };
static inline void write_csr_9c1(uint64_t value)
{
  __asm__ volatile("csrw 0x9c1, %0" : : "r"(value) : "memory");
}

static inline void write_csr_9c2(uint64_t value)
{
  __asm__ volatile("csrw 0x9c2, %0" : : "r"(value) : "memory");
}

static inline void write_csr_9c3(uint64_t value)
{
  __asm__ volatile("csrw 0x9c3, %0" : : "r"(value) : "memory");
}

static inline uint64_t read_csr_9c3(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0x9c3" : "=r"(value) : : "memory");
  return value;
}

static inline uint64_t read_csr_9c0(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0x9c0" : "=r"(value) : : "memory");
  return value;
}

int main(void)
{
  // The host NBF loader initializes .data directly in simulated DRAM, so the
  // default arm leaves these lines cold without executing eviction traffic.
  uint64_t expected_sum = REPLAY_LINES * 7;

#if BENCH_DIAGNOSTIC == 1
  // Dirty-resident lines must be satisfied by the L1 lookup and must never
  // enter the lower detached-prefetch path.
  expected_sum = 0;
  for (unsigned i = 0; i < REPLAY_LINES; ++i) {
    targets[i].value = i + 1;
    expected_sum += i + 1;
  }
#endif

  // Entry format: [46:45] slot, [44:40] line index, [39:0] paddr.
  for (unsigned i = 0; i < REPLAY_LINES; ++i) {
    uint64_t entry = ((uint64_t)REPLAY_SLOT << 45)
                     | ((uint64_t)i << 40)
                     | ((uint64_t)&targets[i] & ((1ULL << 40) - 1));
    write_csr_9c1(entry);
  }

  // Config format: [1:0] slot, [7:2] count, [23:8] delay, [31:24] gap.
  uint64_t config = REPLAY_SLOT | ((uint64_t)REPLAY_LINES << 2)
                    | ((uint64_t)REPLAY_DELAY << 8)
                    | ((uint64_t)REPLAY_GAP << 24) | (1ULL << 63);
  write_csr_9c2(config);

  bp_print_string("DCACHE-REPLAY configured\n");

  write_csr_9c3(REPLAY_SLOT);
  bp_print_string("DCACHE-REPLAY triggered\n");

#if BENCH_DIAGNOSTIC == 2
  // Linux consumes the footprint as soon as the woken task runs. Exercise
  // that coexistence instead of waiting for advisory replay to become idle.
  uint64_t overlap_sum = 0;
  for (unsigned i = 0; i < REPLAY_LINES; ++i)
    overlap_sum += targets[i].value;
  if (overlap_sum != expected_sum) {
    bp_print_string("[BSG-FAIL] tagged replay overlap corrupted target data\n");
    bp_finish(1);
  }
  bp_print_string("DCACHE-REPLAY overlap demand completed\n");
#endif

  uint64_t status = 0;
  // A coexistence failure must terminate quickly enough to preserve a traced
  // waveform without exhausting the shared simulator filesystem.
  unsigned timeout = BENCH_DIAGNOSTIC == 2 ? 2048 : 100000;
  do {
    status = read_csr_9c3();
    if (!--timeout) {
      bp_print_string("[BSG-FAIL] tagged data replay controller timeout\n");
      bp_finish(1);
    }
  } while ((status & 1) || ((status >> 1) & 3));
  bp_print_string("DCACHE-REPLAY completed\n");

  timeout = 100000;
  while (!(read_csr_9c0() & 1)) {
    if (!--timeout) {
      bp_print_string("[BSG-FAIL] tagged data replay UCE drain timeout\n");
      bp_finish(1);
    }
  }
  bp_print_string("DCACHE-REPLAY drained\n");

  uint64_t expected_accepted = BENCH_DIAGNOSTIC == 1 ? 0 : REPLAY_LINES;
  uint64_t expected_filtered = BENCH_DIAGNOSTIC == 1 ? REPLAY_LINES : 0;
  if (((status >> 10) & 0xffff) != expected_accepted
      || ((status >> 26) & 0xffff) != expected_filtered
      || ((status >> 42) & 0xff) != 1
      || ((status >> 50) & 0xff) != 0) {
    bp_print_string("[BSG-FAIL] tagged data replay status counters\n");
    bp_finish(1);
  }

  uint64_t observed_sum = 0;
  for (unsigned i = 0; i < REPLAY_LINES; ++i)
    observed_sum += targets[i].value;
  if (observed_sum != expected_sum) {
    bp_print_string("[BSG-FAIL] tagged data replay corrupted target data\n");
    bp_finish(1);
  }

#if BENCH_DIAGNOSTIC == 1
  bp_print_string("DCACHE-REPLAY dirty-L1 filter passed\n");
#else
  bp_print_string("DCACHE-REPLAY cold admission passed\n");
#endif
  bp_print_string("[BSG-PASS] tagged 32-line physical data replay\n");
  bp_finish(0);
  return 0;
}
