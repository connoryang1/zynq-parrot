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
#include <sys/resource.h>
#include <sys/syscall.h>
#include <unistd.h>

#define SAMPLES 512
#define WARMUPS 64

struct sample {
  uint64_t cycles;
  uint64_t instructions;
};

struct shared_state {
  _Atomic int turn;
  _Atomic int ready;
  uint64_t sent_cycles;
  uint64_t sent_instructions;
  struct sample to_main[SAMPLES];
  struct sample to_worker[SAMPLES];
} __attribute__((aligned(64)));

static struct shared_state shared;

static inline uint64_t cycles(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
  return value;
}

static inline uint64_t instructions(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xc02" : "=r"(value) : : "memory");
  return value;
}

static void pin_cpu0(void)
{
  cpu_set_t set;
  CPU_ZERO(&set);
  CPU_SET(0, &set);
  int error = pthread_setaffinity_np(pthread_self(), sizeof(set), &set);
  if (error) {
    errno = error;
    perror("pthread_setaffinity_np");
    exit(2);
  }
}

static void futex_wait_value(int expected)
{
  long rc = syscall(SYS_futex, &shared.turn, FUTEX_WAIT_PRIVATE, expected,
                    NULL, NULL, 0);
  if (rc < 0 && errno != EAGAIN && errno != EINTR) {
    perror("futex wait");
    exit(2);
  }
}

static void futex_wake_one(void)
{
  long rc = syscall(SYS_futex, &shared.turn, FUTEX_WAKE_PRIVATE, 1,
                    NULL, NULL, 0);
  if (rc < 0) {
    perror("futex wake");
    exit(2);
  }
}

static void wait_turn(int id)
{
  for (;;) {
    int observed = atomic_load_explicit(&shared.turn, memory_order_acquire);
    if (observed == id)
      return;
    futex_wait_value(observed);
  }
}

static void send_to(int target)
{
  shared.sent_cycles = cycles();
  shared.sent_instructions = instructions();
  atomic_store_explicit(&shared.turn, target, memory_order_release);
  futex_wake_one();
}

static struct sample receive(int id)
{
  wait_turn(id);
  uint64_t now_cycles = cycles();
  uint64_t now_instructions = instructions();
  return (struct sample) {
    .cycles = now_cycles - shared.sent_cycles,
    .instructions = now_instructions - shared.sent_instructions
  };
}

static void *worker(void *unused)
{
  (void)unused;
  pin_cpu0();
  atomic_store_explicit(&shared.ready, 1, memory_order_release);
  for (unsigned iteration = 0; iteration < WARMUPS + SAMPLES; ++iteration) {
    struct sample elapsed = receive(1);
    if (iteration >= WARMUPS)
      shared.to_worker[iteration - WARMUPS] = elapsed;
    send_to(0);
  }
  return NULL;
}

static int compare_u64(const void *left, const void *right)
{
  uint64_t a = *(const uint64_t *)left;
  uint64_t b = *(const uint64_t *)right;
  return (a > b) - (a < b);
}

static void report(const char *direction, const struct sample *samples, int instructions_metric)
{
  uint64_t sorted[SAMPLES];
  for (unsigned i = 0; i < SAMPLES; ++i)
    sorted[i] = instructions_metric ? samples[i].instructions : samples[i].cycles;
  qsort(sorted, SAMPLES, sizeof(sorted[0]), compare_u64);
  double median = ((double)sorted[SAMPLES / 2 - 1] + sorted[SAMPLES / 2]) / 2.0;
  printf("RESULT direction=%s metric=%s samples=%d min=%" PRIu64
         " p25=%" PRIu64 " median=%.1f p75=%" PRIu64 " p95=%" PRIu64
         " p99=%" PRIu64 " max=%" PRIu64 "\n",
         direction, instructions_metric ? "instructions" : "cycles", SAMPLES,
         sorted[0], sorted[SAMPLES / 4], median, sorted[3 * SAMPLES / 4],
         sorted[(95 * SAMPLES) / 100], sorted[(99 * SAMPLES) / 100],
         sorted[SAMPLES - 1]);
}

int main(void)
{
  pthread_t peer;
  struct rusage before_usage, after_usage;
  pin_cpu0();
  if (getrusage(RUSAGE_SELF, &before_usage)) {
    perror("getrusage");
    return 2;
  }
  atomic_init(&shared.turn, 0);
  atomic_init(&shared.ready, 0);
  if (pthread_create(&peer, NULL, worker, NULL)) {
    perror("pthread_create");
    return 2;
  }
  while (!atomic_load_explicit(&shared.ready, memory_order_acquire))
    sched_yield();
  for (unsigned iteration = 0; iteration < WARMUPS + SAMPLES; ++iteration) {
    send_to(1);
    struct sample elapsed = receive(0);
    if (iteration >= WARMUPS)
      shared.to_main[iteration - WARMUPS] = elapsed;
  }
  if (pthread_join(peer, NULL)) {
    perror("pthread_join");
    return 2;
  }
  if (getrusage(RUSAGE_SELF, &after_usage)) {
    perror("getrusage");
    return 2;
  }

  printf("LINUX_FUTEX_HANDOFF samples=%d warmups=%d same_mm=1 cpu=0\n",
         SAMPLES, WARMUPS);
  report("to_main", shared.to_main, 0);
  report("to_main", shared.to_main, 1);
  report("to_worker", shared.to_worker, 0);
  report("to_worker", shared.to_worker, 1);
  long minor_faults = after_usage.ru_minflt - before_usage.ru_minflt;
  long major_faults = after_usage.ru_majflt - before_usage.ru_majflt;
  printf("FAULTS minor=%ld major=%ld\n", minor_faults, major_faults);
  if (major_faults != 0 || minor_faults > 16) {
    puts("[LINUX-FUTEX-HANDOFF] FAIL faults");
    return 1;
  }
  puts("[LINUX-FUTEX-HANDOFF] PASS");
  return 0;
}
