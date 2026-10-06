#define _GNU_SOURCE

#include <errno.h>
#include <inttypes.h>
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

#define TRACE_DEPTH 256U
#define TRACE_CONTROL 0x805
#define TRACE_SELECT  0x806
#define TRACE_DATA    0x807

static _Atomic uint32_t phase;
static _Atomic uint32_t peer_ready;
static uint64_t peer_begin_cycle;
static uint64_t peer_wake_cycle;
static uint64_t peer_block_cycle;
static uint64_t trace_start_cycle;
static uint64_t icache_records[TRACE_DEPTH];
static uint64_t dcache_records[TRACE_DEPTH];

enum trace_window {
  TRACE_WINDOW_FULL,
  TRACE_WINDOW_TO_PEER,
  TRACE_WINDOW_FROM_PEER,
};
static enum trace_window trace_window;

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

static inline uint64_t global_cycle(void)
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

static inline uint64_t trace_record(unsigned dcache, unsigned index)
{
  uint64_t value;
  const uint64_t selector = ((uint64_t)dcache << 8) | index;
  __asm__ volatile(
    "csrw 0x806, %1\n"
    "nop\n"
    "nop\n"
    "nop\n"
    "csrr %0, 0x807\n"
    : "=r"(value) : "r"(selector) : "memory");
  return value;
}

static int futex_wait_value(_Atomic uint32_t *word, uint32_t value)
{
  return (int)syscall(SYS_futex, (uint32_t *)word, FUTEX_WAIT_PRIVATE,
                      value, NULL, NULL, 0);
}

static void futex_wake_one(_Atomic uint32_t *word)
{
  if (syscall(SYS_futex, (uint32_t *)word, FUTEX_WAKE_PRIVATE,
              1, NULL, NULL, 0) < 0)
    fail("futex wake");
}

static int pin_to_first_allowed_cpu(void)
{
  cpu_set_t allowed, selected;
  if (sched_getaffinity(0, sizeof(allowed), &allowed))
    fail("sched_getaffinity");
  int cpu = -1;
  for (int candidate = 0; candidate < CPU_SETSIZE; ++candidate)
    if (CPU_ISSET(candidate, &allowed)) {
      cpu = candidate;
      break;
    }
  if (cpu < 0) {
    errno = EINVAL;
    fail("empty CPU affinity");
  }
  CPU_ZERO(&selected);
  CPU_SET(cpu, &selected);
  if (sched_setaffinity(0, sizeof(selected), &selected))
    fail("sched_setaffinity");
  if (sched_getaffinity(0, sizeof(allowed), &allowed))
    fail("verify affinity");
  if (CPU_COUNT(&allowed) != 1 || !CPU_ISSET(cpu, &allowed)) {
    errno = EINVAL;
    fail("singleton CPU affinity");
  }
  return cpu;
}

static void wait_until(_Atomic uint32_t *word, uint32_t wanted)
{
  for (;;) {
    uint32_t observed = atomic_load_explicit(word, memory_order_acquire);
    if (observed == wanted)
      return;
    if (futex_wait_value(word, observed) && errno != EAGAIN && errno != EINTR)
      fail("futex wait");
  }
}

static void *peer_main(void *unused)
{
  (void)unused;
  (void)pin_to_first_allowed_cpu();
  atomic_store_explicit(&peer_ready, 1, memory_order_release);
  futex_wake_one(&peer_ready);

  wait_until(&phase, 1);
  if (trace_window == TRACE_WINDOW_FROM_PEER) {
    trace_control(2);
    trace_start_cycle = global_cycle();
    peer_begin_cycle = trace_start_cycle;
    trace_control(3);
  } else {
    peer_begin_cycle = global_cycle();
    if (trace_window == TRACE_WINDOW_TO_PEER)
      trace_control(0);
  }
  atomic_store_explicit(&phase, 2, memory_order_release);
  peer_wake_cycle = global_cycle();
  futex_wake_one(&phase);
  peer_block_cycle = global_cycle();

  /* Block after waking the source, forcing the source task to be dispatched. */
  wait_until(&phase, 3);
  return NULL;
}

static uint32_t record_cycle(uint64_t record)
{
  return (uint32_t)(record >> 32);
}

static void print_record(unsigned sequence, char side, unsigned index,
                         uint64_t record, uint32_t start_cycle)
{
  const uint32_t cycle = record_cycle(record);
  const uint32_t relative = cycle - start_cycle;
  const unsigned message = (unsigned)((record >> 28) & 0xf);
  const uint64_t line = record & UINT64_C(0x0fffffff);
  printf("TRACE_RECORD seq=%u side=%c index=%u cycle=%" PRIu32
         " relative=%" PRIu32 " message=0x%x paddr=0x%09" PRIx64
         " raw=0x%016" PRIx64 "\n",
         sequence, side, index, cycle, relative, message, line << 6, record);
}

int main(int argc, char **argv)
{
  if (argc == 3 && !strcmp(argv[1], "--window")) {
    if (!strcmp(argv[2], "full"))
      trace_window = TRACE_WINDOW_FULL;
    else if (!strcmp(argv[2], "to-peer"))
      trace_window = TRACE_WINDOW_TO_PEER;
    else if (!strcmp(argv[2], "from-peer"))
      trace_window = TRACE_WINDOW_FROM_PEER;
    else {
      fputs("usage: cache_miss_trace_capture [--window full|to-peer|from-peer]\n",
            stderr);
      return EXIT_FAILURE;
    }
  } else if (argc != 1) {
    fputs("usage: cache_miss_trace_capture [--window full|to-peer|from-peer]\n",
          stderr);
    return EXIT_FAILURE;
  }

  const int cpu = pin_to_first_allowed_cpu();
  pthread_t peer;
  check_pthread(pthread_create(&peer, NULL, peer_main, NULL), "pthread_create");
  wait_until(&peer_ready, 1);

  /* Clear while disarmed first, keeping setup and stale records out of scope. */
  trace_control(2);
  if (trace_window != TRACE_WINDOW_FROM_PEER) {
    trace_start_cycle = global_cycle();
    trace_control(3);
  }

  atomic_store_explicit(&phase, 1, memory_order_release);
  futex_wake_one(&phase);
  wait_until(&phase, 2);

  const uint64_t resume_cycle = global_cycle();
  trace_control(0);
  __asm__ volatile("nop\nnop\nnop" : : : "memory");
  const uint64_t status = trace_status();

  atomic_store_explicit(&phase, 3, memory_order_release);
  futex_wake_one(&phase);
  check_pthread(pthread_join(peer, NULL), "pthread_join");

  const unsigned icount = (unsigned)(status & UINT64_C(0x1ff));
  const unsigned dcount = (unsigned)((status >> 9) & UINT64_C(0x1ff));
  const unsigned ioverflow = (unsigned)((status >> 18) & 1);
  const unsigned doverflow = (unsigned)((status >> 19) & 1);
  const unsigned armed = (unsigned)((status >> 20) & 1);
  const uint64_t stop_cycle = trace_window == TRACE_WINDOW_TO_PEER
    ? peer_begin_cycle : resume_cycle;
  printf("TRACE_HEADER cpu=%d window=%u start=%" PRIu64 " peer_begin=%" PRIu64
         " peer_wake=%" PRIu64 " peer_block=%" PRIu64 " resume=%" PRIu64
         " elapsed=%" PRIu64 " i_count=%u d_count=%u"
         " i_overflow=%u d_overflow=%u armed=%u status=0x%016" PRIx64 "\n",
         cpu, (unsigned)trace_window, trace_start_cycle, peer_begin_cycle,
         peer_wake_cycle, peer_block_cycle, resume_cycle,
         stop_cycle - trace_start_cycle,
         icount, dcount, ioverflow, doverflow,
         armed, status);

  if (armed || icount > TRACE_DEPTH || dcount > TRACE_DEPTH ||
      icount + dcount == 0) {
    fputs("TRACE_FAIL invalid recorder status\n", stderr);
    return EXIT_FAILURE;
  }

  for (unsigned i = 0; i < icount; ++i)
    icache_records[i] = trace_record(0, i);
  for (unsigned i = 0; i < dcount; ++i)
    dcache_records[i] = trace_record(1, i);

  unsigned ii = 0, di = 0, sequence = 0;
  const uint32_t start32 = (uint32_t)trace_start_cycle;
  while (ii < icount || di < dcount) {
    const uint32_t irelative = ii < icount
      ? record_cycle(icache_records[ii]) - start32 : UINT32_MAX;
    const uint32_t drelative = di < dcount
      ? record_cycle(dcache_records[di]) - start32 : UINT32_MAX;
    if (irelative <= drelative) {
      print_record(sequence++, 'I', ii, icache_records[ii], start32);
      ++ii;
    } else {
      print_record(sequence++, 'D', di, dcache_records[di], start32);
      ++di;
    }
  }
  if (ioverflow || doverflow) {
    printf("TRACE_TRUNCATED records=%u elapsed=%" PRIu64
           " i_overflow=%u d_overflow=%u\n",
           icount + dcount, stop_cycle - trace_start_cycle,
           ioverflow, doverflow);
    return EXIT_FAILURE;
  }
  printf("TRACE_PASS records=%u elapsed=%" PRIu64 "\n",
         icount + dcount, stop_cycle - trace_start_cycle);
  return EXIT_SUCCESS;
}
