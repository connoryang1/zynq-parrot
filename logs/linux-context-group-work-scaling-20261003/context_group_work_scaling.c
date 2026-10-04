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

#include "../../testing/mt_seed.h"

typedef uint64_t u64;

#define MODES 6
#define SAMPLES 64
#define WARMUPS 8
#define TURNS 64
#define PEER_TURNS (MODES * (SAMPLES + WARMUPS) * TURNS)
#define SPECTATOR_BIT 8
#define SOURCE_BIT 1
#define SOURCE_S11 0x13579bdfUL
#define PEER_S11 0x2468ace0UL
#define MAX_SC_FAILURES (2 * PEER_TURNS / 100)
#define STRINGIFY_INNER(value) #value
#define STRINGIFY(value) STRINGIFY_INNER(value)

static const u64 work_iterations[MODES] = {0, 16, 64, 256, 1024, 4096};
static volatile u64 hw_work_iterations __attribute__((aligned(64)));
static volatile u64 ready_word __attribute__((aligned(64)));
static volatile u64 peer_complete[2] __attribute__((aligned(64)));
static volatile u64 peer_context[2] __attribute__((aligned(64)));
static volatile u64 peer_s11[2] __attribute__((aligned(64)));
static volatile u64 peer_failures[2] __attribute__((aligned(64)));
static volatile u64 peer_accumulator[2] __attribute__((aligned(64)));
static u64 hw_source_failures[2];
static u64 hw_source_accumulator[2];
static u64 hw_samples[2][MODES][SAMPLES];
static u64 linux_samples[MODES][SAMPLES];
static u64 work_samples[MODES][SAMPLES];
static volatile u64 work_sink;
static u64 work_accumulator;
static u64 linux_source_accumulator;

struct linux_state {
  _Atomic unsigned turn;
  _Atomic unsigned ready;
  u64 worker_accumulator;
} __attribute__((aligned(64)));

static struct linux_state linux_state;

static inline u64 cycles(void)
{
  u64 value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
  return value;
}

static inline u64 context(void)
{
  u64 value;
  __asm__ volatile("csrr %0, 0x800" : "=r"(value) : : "memory");
  return value;
}

/* A stackless leaf used unchanged by Linux threads and hardware contexts. */
static __attribute__((naked, noinline, used)) u64
do_work(u64 iterations __attribute__((unused)),
        u64 accumulator __attribute__((unused)))
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "beqz a0, 2f\n"
    "1: addi a1, a1, 1\n"
    "addi a0, a0, -1\n"
    "bnez a0, 1b\n"
    "2: mv a0, a1\n"
    "ret\n"
    ".option pop\n");
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

static void yield_cpu(void)
{
  if (syscall(SYS_sched_yield) < 0) {
    perror("sched_yield");
    exit(2);
  }
}

static void wait_turn(unsigned turn)
{
  while (atomic_load_explicit(&linux_state.turn, memory_order_acquire) != turn)
    yield_cpu();
}

static void *linux_worker(void *unused)
{
  (void)unused;
  u64 accumulator = 0x2222;
  pin_cpu0();
  atomic_store_explicit(&linux_state.ready, 1, memory_order_release);
  for (unsigned mode = 0; mode < MODES; ++mode) {
    for (unsigned sample = 0; sample < WARMUPS + SAMPLES; ++sample) {
      for (unsigned turn = 0; turn < TURNS; ++turn) {
        wait_turn(1);
        accumulator = do_work(work_iterations[mode], accumulator);
        atomic_store_explicit(&linux_state.turn, 0, memory_order_release);
        yield_cpu();
      }
    }
  }
  linux_state.worker_accumulator = accumulator;
  return NULL;
}

static void measure_linux(void)
{
  pthread_t worker;
  u64 accumulator = 0x1111;
  atomic_init(&linux_state.turn, 0);
  atomic_init(&linux_state.ready, 0);
  linux_state.worker_accumulator = 0;
  if (pthread_create(&worker, NULL, linux_worker, NULL)) {
    perror("pthread_create");
    exit(2);
  }
  while (!atomic_load_explicit(&linux_state.ready, memory_order_acquire))
    yield_cpu();

  for (unsigned mode = 0; mode < MODES; ++mode) {
    for (unsigned sample = 0; sample < WARMUPS + SAMPLES; ++sample) {
      u64 begin = cycles();
      for (unsigned turn = 0; turn < TURNS; ++turn) {
        accumulator = do_work(work_iterations[mode], accumulator);
        atomic_store_explicit(&linux_state.turn, 1, memory_order_release);
        yield_cpu();
        wait_turn(0);
      }
      u64 elapsed = cycles() - begin;
      if (sample >= WARMUPS)
        linux_samples[mode][sample - WARMUPS] = elapsed;
    }
  }
  if (pthread_join(worker, NULL)) {
    perror("pthread_join");
    exit(2);
  }
  work_sink ^= accumulator ^ linux_state.worker_accumulator;
  linux_source_accumulator = accumulator;
}

#define LRSC_STEP(source_bit)                                               \
    "2: lr.d.aq t4, (t2)\n"                                               \
    "beqz t4, 2b\n"                                                       \
    ".option arch, +zbb\n"                                                \
    "ctz t5, t4\n"                                                        \
    "li t6, 1\n"                                                          \
    "sll t6, t6, t5\n"                                                    \
    "not t6, t6\n"                                                        \
    "and t6, t4, t6\n"                                                    \
    "ori t6, t6, " STRINGIFY(source_bit) "\n"                             \
    "sc.d.rl t3, t6, (t2)\n"                                              \
    "beqz t3, 3f\n"                                                       \
    "addi a6, a6, 1\n"                                                    \
    "j 2b\n"                                                              \
    "3: csrw 0x800, t5\n"

#define PEER(name, peer_bit, result_index)                                  \
static __attribute__((naked, noinline, noreturn, used, aligned(8)))          \
void name(void)                                                             \
{                                                                           \
  __asm__ volatile(                                                         \
    ".option push\n.option norvc\n"                                        \
    "li s10, 0x2222\n"                                                     \
    "li t0, " STRINGIFY(PEER_TURNS) "\n"                                  \
    "li a6, 0\n"                                                           \
    "1:\n"                                                                 \
    "lla t1, hw_work_iterations\n"                                         \
    "ld a0, 0(t1)\n"                                                       \
    "mv a1, s10\n"                                                         \
    "call do_work\n"                                                       \
    "mv s10, a0\n"                                                         \
    "lla t2, ready_word\n"                                                 \
    LRSC_STEP(peer_bit)                                                      \
    "addi t0, t0, -1\n"                                                    \
    "bnez t0, 1b\n"                                                        \
    "lla t2, peer_failures\n"                                              \
    "sd a6, " STRINGIFY(8 * result_index) "(t2)\n"                        \
    "lla t2, peer_context\n"                                               \
    "csrr t3, 0x800\n"                                                     \
    "sd t3, " STRINGIFY(8 * result_index) "(t2)\n"                        \
    "lla t2, peer_s11\n"                                                   \
    "sd s11, " STRINGIFY(8 * result_index) "(t2)\n"                       \
    "lla t2, peer_accumulator\n"                                           \
    "sd s10, " STRINGIFY(8 * result_index) "(t2)\n"                       \
    "lla t2, peer_complete\n"                                              \
    "li t3, 1\n"                                                           \
    "sd t3, " STRINGIFY(8 * result_index) "(t2)\n"                        \
    "fence rw, rw\n"                                                       \
    "csrw 0x800, zero\n"                                                   \
    "4: j 4b\n"                                                            \
    ".option pop\n");                                                      \
}

PEER(peer_resident, 2, 0)
PEER(peer_nonresident, 4, 1)

static inline u64 selector_step(void)
{
  u64 failures;
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "lla t2, ready_word\n"
    "li a6, 0\n"
    LRSC_STEP(SOURCE_BIT)
    "mv %0, a6\n"
    ".option pop\n"
    : "=r"(failures)
    :
    : "t2", "t3", "t4", "t5", "t6", "a6", "memory");
  return failures;
}

static u64 hw_ring(u64 iterations, u64 *accumulator)
{
  u64 failures = 0;
  u64 value = *accumulator;
  for (unsigned turn = 0; turn < TURNS; ++turn) {
    value = do_work(iterations, value);
    failures += selector_step();
  }
  *accumulator = value;
  return failures;
}

static int measure_hardware_phase(unsigned index, u64 target, u64 target_bit,
                                  void (*peer)(void))
{
  u64 accumulator = 0x1111;
  ready_word = target_bit | SPECTATOR_BIT;
  peer_complete[index] = 0;
  peer_context[index] = ~0ULL;
  peer_s11[index] = 0;
  peer_failures[index] = ~0ULL;
  peer_accumulator[index] = 0;
  hw_source_failures[index] = 0;
  seed_reg(target, 27, PEER_S11);
  seed_npc(target, (u64)peer);
  __asm__ volatile("fence rw, rw" : : : "memory");

  for (unsigned mode = 0; mode < MODES; ++mode) {
    hw_work_iterations = work_iterations[mode];
    __asm__ volatile("fence rw, rw" : : : "memory");
    for (unsigned sample = 0; sample < WARMUPS + SAMPLES; ++sample) {
      u64 begin = cycles();
      hw_source_failures[index] += hw_ring(work_iterations[mode], &accumulator);
      u64 elapsed = cycles() - begin;
      if (sample >= WARMUPS)
        hw_samples[index][mode][sample - WARMUPS] = elapsed;
    }
  }

  __asm__ volatile("csrw 0x800, %0" : : "r"(target) : "memory");
  work_sink ^= accumulator;
  hw_source_accumulator[index] = accumulator;
  return context() == 0 && ready_word == (target_bit | SPECTATOR_BIT)
      && peer_complete[index] == 1 && peer_context[index] == target
      && peer_s11[index] == PEER_S11
      && hw_source_failures[index] <= MAX_SC_FAILURES
      && peer_failures[index] <= MAX_SC_FAILURES;
}

static int compare_u64(const void *left, const void *right)
{
  u64 a = *(const u64 *)left;
  u64 b = *(const u64 *)right;
  return (a > b) - (a < b);
}

static u64 median(const u64 *values)
{
  u64 sorted[SAMPLES];
  memcpy(sorted, values, sizeof(sorted));
  qsort(sorted, SAMPLES, sizeof(sorted[0]), compare_u64);
  return (sorted[SAMPLES / 2 - 1] + sorted[SAMPLES / 2]) / 2;
}

static void measure_work(void)
{
  u64 accumulator = 0x3333;
  for (unsigned mode = 0; mode < MODES; ++mode) {
    for (unsigned sample = 0; sample < SAMPLES; ++sample) {
      u64 begin = cycles();
      for (unsigned turn = 0; turn < TURNS; ++turn)
        accumulator = do_work(work_iterations[mode], accumulator);
      work_samples[mode][sample] = cycles() - begin;
    }
  }
  work_sink ^= accumulator;
  work_accumulator = accumulator;
}

static void report_mode(unsigned mode)
{
  u64 work = median(work_samples[mode]);
  u64 linux_cycles = median(linux_samples[mode]);
  u64 resident = median(hw_samples[0][mode]);
  u64 nonresident = median(hw_samples[1][mode]);
  printf("WORK_SCALING iterations=%" PRIu64
         " work_aggregate=%" PRIu64 " work_x100_per_call=%" PRIu64
         " linux_aggregate=%" PRIu64 " linux_x100_per_handoff=%" PRIu64
         " resident_aggregate=%" PRIu64 " resident_x100_per_handoff=%" PRIu64
         " nonresident_aggregate=%" PRIu64 " nonresident_x100_per_handoff=%" PRIu64
         "\n",
         work_iterations[mode], work, work * 100 / TURNS,
         linux_cycles, linux_cycles * 100 / (2 * TURNS),
         resident, resident * 100 / (2 * TURNS),
         nonresident, nonresident * 100 / (2 * TURNS));
}

int main(void)
{
  struct rusage before, after;
  if (context() != 0) return 2;
  pin_cpu0();
  if (getrusage(RUSAGE_SELF, &before)) return 2;
  measure_work();
  measure_linux();
  __asm__ volatile("mv s11, %0" : : "r"(SOURCE_S11) : "s11", "memory");
  int resident_ok = measure_hardware_phase(0, 1, 2, peer_resident);
  int nonresident_ok = measure_hardware_phase(1, 2, 4, peer_nonresident);
  if (getrusage(RUSAGE_SELF, &after)) return 2;

  printf("CONTEXT_GROUP_WORK_SCALING samples=%d warmups=%d turns=%d sink=%" PRIu64 "\n",
         SAMPLES, WARMUPS, TURNS, work_sink);
  for (unsigned mode = 0; mode < MODES; ++mode) report_mode(mode);
  printf("SC_FAILURES resident_source=%" PRIu64 " resident_peer=%" PRIu64
         " nonresident_source=%" PRIu64 " nonresident_peer=%" PRIu64 "\n",
         hw_source_failures[0], peer_failures[0],
         hw_source_failures[1], peer_failures[1]);
  long minor = after.ru_minflt - before.ru_minflt;
  long major = after.ru_majflt - before.ru_majflt;
  u64 iteration_sum = 0;
  for (unsigned mode = 0; mode < MODES; ++mode)
    iteration_sum += work_iterations[mode];
  u64 expected_linux_delta = iteration_sum * (SAMPLES + WARMUPS) * TURNS;
  u64 expected_hw_delta = expected_linux_delta;
  u64 expected_work_delta = iteration_sum * SAMPLES * TURNS;
  int work_ok = work_accumulator == 0x3333 + expected_work_delta
      && linux_source_accumulator == 0x1111 + expected_linux_delta
      && linux_state.worker_accumulator == 0x2222 + expected_linux_delta
      && hw_source_accumulator[0] == 0x1111 + expected_hw_delta
      && hw_source_accumulator[1] == 0x1111 + expected_hw_delta
      && peer_accumulator[0] == 0x2222 + expected_hw_delta
      && peer_accumulator[1] == 0x2222 + expected_hw_delta;
  printf("WORK_CHECK status=%s expected_delta=%" PRIu64 "\n",
         work_ok ? "PASS" : "FAIL", expected_hw_delta);
  printf("FAULTS minor=%ld major=%ld\n", minor, major);
  if (!work_ok || !resident_ok || !nonresident_ok || major != 0 || minor > 24) {
    puts("[CONTEXT-GROUP-WORK-SCALING] FAIL");
    return 1;
  }
  puts("[CONTEXT-GROUP-WORK-SCALING] PASS");
  return 0;
}
