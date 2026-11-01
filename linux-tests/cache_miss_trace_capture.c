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
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <unistd.h>

#define TRACE_DEPTH 256U
#define TRACE_CONTROL 0x805
#define TRACE_SELECT  0x806
#define TRACE_DATA    0x807
#define PR_BP_PREVIEW_PIN_SET 0x42505059
#define PR_BP_PREVIEW_ENABLE  0x4250505a

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
static int summary_only;
static int allow_overflow;
static unsigned samples = 1;
static unsigned preview_mode;
static int preview_control;

static void usage(FILE *stream)
{
  fputs("usage: cache_miss_trace_capture [--window full|to-peer|from-peer]"
        " [--summary-only] [--samples 1..10000]"
        " [--allow-overflow]"
        " [--preview-mode disabled|trigger|wake-trigger]\n", stream);
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

static void configure_preview(void)
{
  if (!preview_control)
    return;
  /* The kernel requires a registered physical page before any nonzero mode,
   * including instruction-only modes. Register the same harmless shared page
   * in both A/B arms; modes five and six never issue its data hint. */
  if (prctl(PR_BP_PREVIEW_PIN_SET, (unsigned long)&phase,
            0UL, 0UL, 0UL))
    fail("register preview page");
  if (prctl(PR_BP_PREVIEW_ENABLE, (unsigned long)preview_mode,
            0UL, 0UL, 0UL))
    fail("set preview mode");
}

static void release_preview(void)
{
  if (!preview_control)
    return;
  if (prctl(PR_BP_PREVIEW_ENABLE, 0UL, 0UL, 0UL, 0UL))
    fail("disable preview mode");
  if (prctl(PR_BP_PREVIEW_PIN_SET, 0UL, 0UL, 0UL, 0UL))
    fail("release preview page");
}

static void *peer_main(void *unused)
{
  (void)unused;
  (void)pin_to_first_allowed_cpu();
  configure_preview();
  atomic_store_explicit(&peer_ready, 1, memory_order_release);
  futex_wake_one(&peer_ready);

  for (unsigned sample = 0; sample < samples; ++sample) {
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
  }
  release_preview();
  return NULL;
}

static unsigned parse_samples(const char *text)
{
  unsigned value = 0;
  if (!text[0]) {
    usage(stderr);
    exit(EXIT_FAILURE);
  }
  for (const char *p = text; *p; ++p) {
    if (*p < '0' || *p > '9' || value > 10000U / 10U) {
      usage(stderr);
      exit(EXIT_FAILURE);
    }
    value = value * 10U + (unsigned)(*p - '0');
    if (value > 10000U) {
      usage(stderr);
      exit(EXIT_FAILURE);
    }
  }
  if (!value) {
    usage(stderr);
    exit(EXIT_FAILURE);
  }
  return value;
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
  for (int arg = 1; arg < argc; ++arg) {
    if (!strcmp(argv[arg], "--summary-only")) {
      summary_only = 1;
    } else if (!strcmp(argv[arg], "--allow-overflow")) {
      allow_overflow = 1;
    } else if (!strcmp(argv[arg], "--samples") && arg + 1 < argc) {
      samples = parse_samples(argv[++arg]);
    } else if (!strcmp(argv[arg], "--preview-mode") && arg + 1 < argc) {
      const char *mode = argv[++arg];
      preview_control = 1;
      if (!strcmp(mode, "disabled"))
        preview_mode = 0;
      else if (!strcmp(mode, "trigger"))
        preview_mode = 5;
      else if (!strcmp(mode, "wake-trigger"))
        preview_mode = 6;
      else {
        usage(stderr);
        return EXIT_FAILURE;
      }
    } else if (!strcmp(argv[arg], "--window") && arg + 1 < argc) {
      const char *window = argv[++arg];
      if (!strcmp(window, "full"))
        trace_window = TRACE_WINDOW_FULL;
      else if (!strcmp(window, "to-peer"))
        trace_window = TRACE_WINDOW_TO_PEER;
      else if (!strcmp(window, "from-peer"))
        trace_window = TRACE_WINDOW_FROM_PEER;
      else {
        usage(stderr);
        return EXIT_FAILURE;
      }
    } else {
      usage(stderr);
      return EXIT_FAILURE;
    }
  }
  if (allow_overflow && !summary_only) {
    usage(stderr);
    return EXIT_FAILURE;
  }

  const int cpu = pin_to_first_allowed_cpu();
  pthread_t peer;
  check_pthread(pthread_create(&peer, NULL, peer_main, NULL), "pthread_create");
  configure_preview();
  wait_until(&peer_ready, 1);

  printf("TRACE_PREVIEW mode=%s value=%u\n",
         !preview_control ? "legacy" :
         preview_mode == 0 ? "disabled" :
         preview_mode == 5 ? "trigger" : "wake-trigger",
         preview_mode);

  int any_failure = 0;
  for (unsigned sample = 1; sample <= samples; ++sample) {
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

    const unsigned icount = (unsigned)(status & UINT64_C(0x1ff));
    const unsigned dcount = (unsigned)((status >> 9) & UINT64_C(0x1ff));
    const unsigned ioverflow = (unsigned)((status >> 18) & 1);
    const unsigned doverflow = (unsigned)((status >> 19) & 1);
    const unsigned armed = (unsigned)((status >> 20) & 1);
    const uint64_t stop_cycle = trace_window == TRACE_WINDOW_TO_PEER
      ? peer_begin_cycle : resume_cycle;
    if (samples > 1)
      printf("SAMPLE=%u\n", sample);
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
      any_failure = 1;
      continue;
    }

    if (summary_only) {
      if (ioverflow || doverflow) {
        printf("TRACE_TRUNCATED records=%u elapsed=%" PRIu64
               " i_overflow=%u d_overflow=%u\n",
               icount + dcount, stop_cycle - trace_start_cycle,
               ioverflow, doverflow);
        if (!allow_overflow)
          any_failure = 1;
      } else {
        printf("TRACE_PASS records=%u elapsed=%" PRIu64 "\n",
               icount + dcount, stop_cycle - trace_start_cycle);
      }
      continue;
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
      any_failure = 1;
    } else {
      printf("TRACE_PASS records=%u elapsed=%" PRIu64 "\n",
             icount + dcount, stop_cycle - trace_start_cycle);
    }
  }
  check_pthread(pthread_join(peer, NULL), "pthread_join");
  release_preview();
  if (!any_failure)
    printf("TRACE_CAPTURE_PASS samples=%u allow_overflow=%u\n",
           samples, allow_overflow);
  return any_failure ? EXIT_FAILURE : EXIT_SUCCESS;
}
