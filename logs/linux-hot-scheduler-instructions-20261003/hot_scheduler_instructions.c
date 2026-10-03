#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
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

struct shared_state {
  _Atomic int turn;
  _Atomic int ready;
  uint64_t sent_instruction;
  uint64_t to_main[SAMPLES];
  uint64_t to_worker[SAMPLES];
} __attribute__((aligned(64)));

static struct shared_state shared;
static uint64_t empty_samples[SAMPLES];
static uint64_t gettid_samples[SAMPLES];
static uint64_t self_yield_samples[SAMPLES];

static inline uint64_t instructions(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xc02" : "=r"(value) : : "memory");
  return value;
}

static long checked_syscall(long number)
{
  long result = syscall(number);
  if (result < 0) {
    perror("syscall");
    exit(2);
  }
  return result;
}

static void yield_cpu(void)
{
  (void)checked_syscall(SYS_sched_yield);
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

static void sample_local_paths(void)
{
  for (unsigned iteration = 0; iteration < WARMUPS + SAMPLES; ++iteration) {
    uint64_t before = instructions();
    uint64_t after = instructions();
    if (iteration >= WARMUPS)
      empty_samples[iteration - WARMUPS] = after - before;

    before = instructions();
    (void)checked_syscall(SYS_gettid);
    after = instructions();
    if (iteration >= WARMUPS)
      gettid_samples[iteration - WARMUPS] = after - before;

    before = instructions();
    yield_cpu();
    after = instructions();
    if (iteration >= WARMUPS)
      self_yield_samples[iteration - WARMUPS] = after - before;
  }
}

static void wait_turn(int id)
{
  while (atomic_load_explicit(&shared.turn, memory_order_acquire) != id)
    yield_cpu();
}

static void send_to(int target)
{
  shared.sent_instruction = instructions();
  atomic_store_explicit(&shared.turn, target, memory_order_release);
  yield_cpu();
}

static uint64_t receive(int id)
{
  wait_turn(id);
  return instructions() - shared.sent_instruction;
}

static void *worker(void *unused)
{
  (void)unused;
  pin_cpu0();
  atomic_store_explicit(&shared.ready, 1, memory_order_release);
  for (unsigned iteration = 0; iteration < WARMUPS + SAMPLES; ++iteration) {
    uint64_t elapsed = receive(1);
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

static void report(const char *metric, const uint64_t *samples)
{
  uint64_t sorted[SAMPLES];
  memcpy(sorted, samples, sizeof(sorted));
  qsort(sorted, SAMPLES, sizeof(sorted[0]), compare_u64);
  double median = ((double)sorted[SAMPLES / 2 - 1] + sorted[SAMPLES / 2]) / 2.0;
  printf("RESULT metric=%s samples=%d min=%" PRIu64 " p25=%" PRIu64
         " median=%.1f p75=%" PRIu64 " p95=%" PRIu64 " p99=%" PRIu64
         " max=%" PRIu64 "\n", metric, SAMPLES, sorted[0], sorted[SAMPLES / 4],
         median, sorted[3 * SAMPLES / 4], sorted[(95 * SAMPLES) / 100],
         sorted[(99 * SAMPLES) / 100], sorted[SAMPLES - 1]);
  printf("SAMPLES metric=%s", metric);
  for (unsigned i = 0; i < SAMPLES; ++i)
    printf(" %" PRIu64, samples[i]);
  putchar('\n');
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

  /* No competing user thread exists during these three matched measurements. */
  sample_local_paths();

  atomic_init(&shared.turn, 0);
  atomic_init(&shared.ready, 0);
  if (pthread_create(&peer, NULL, worker, NULL)) {
    perror("pthread_create");
    return 2;
  }
  while (!atomic_load_explicit(&shared.ready, memory_order_acquire))
    yield_cpu();
  for (unsigned iteration = 0; iteration < WARMUPS + SAMPLES; ++iteration) {
    send_to(1);
    uint64_t elapsed = receive(0);
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

  printf("HOT_SCHEDULER_INSTRUCTIONS retired_instructions samples=%d warmups=%d same_mm=1 cpu=0\n",
         SAMPLES, WARMUPS);
  report("cycle_read_pair", empty_samples);
  report("gettid_syscall", gettid_samples);
  report("sched_yield_no_user_peer", self_yield_samples);
  report("handoff_to_main", shared.to_main);
  report("handoff_to_worker", shared.to_worker);
  long minor_faults = after_usage.ru_minflt - before_usage.ru_minflt;
  long major_faults = after_usage.ru_majflt - before_usage.ru_majflt;
  printf("FAULTS minor=%ld major=%ld\n", minor_faults, major_faults);
  if (major_faults != 0 || minor_faults > 16) {
    puts("[HOT-SCHEDULER-INSTRUCTIONS] FAIL faults");
    return 1;
  }
  puts("[HOT-SCHEDULER-INSTRUCTIONS] PASS");
  return 0;
}
