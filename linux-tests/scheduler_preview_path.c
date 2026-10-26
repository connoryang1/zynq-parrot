#define _GNU_SOURCE

/* Identify the scheduler predecessor seen by a task with a preview descriptor.
 * This is a path diagnostic, not a latency or cache-warming benchmark.
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
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#if !defined(__riscv) || __riscv_xlen != 64
#error "This diagnostic requires RV64 BlackParrot Linux"
#endif

#define PR_BP_PREVIEW_SET 0x42505056
#define PR_BP_PREVIEW_GET_COUNT 0x42505057
#define PR_BP_PREVIEW_GET_GUARD 0x42505058

enum { repetitions = 8, guards = 5 };
enum { same_mm, idle, different_mm, cases };

struct counts {
  unsigned long guard[guards], hook;
  unsigned stable;
};
struct sample {
  struct counts before, after;
};
struct thread_case {
  unsigned mode;
  _Atomic uint32_t ready, phase, done;
  struct sample samples[repetitions];
};

static volatile uint64_t target_line[8] __attribute__((aligned(64)));

static void fail(const char *what)
{
  perror(what);
  exit(EXIT_FAILURE);
}

static void pin_first_cpu(void)
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
}

static void register_descriptor(void)
{
  if (prctl(PR_BP_PREVIEW_SET, (unsigned long)&target_line[0],
            0UL, 0UL, 0UL)) fail("set preview descriptor");
}

static unsigned long read_guard(unsigned index)
{
  int value = prctl(PR_BP_PREVIEW_GET_GUARD, (unsigned long)index,
                    0UL, 0UL, 0UL);
  if (value < 0) fail("read preview guard");
  return (unsigned long)value;
}

static struct counts snapshot(void)
{
  struct counts out = {0};
  out.guard[0] = read_guard(0);
  for (unsigned i = 1; i < guards; ++i) out.guard[i] = read_guard(i);
  int hook = prctl(PR_BP_PREVIEW_GET_COUNT, 0UL, 0UL, 0UL, 0UL);
  if (hook < 0) fail("read preview hook count");
  out.hook = (unsigned long)hook;
  out.stable = out.guard[0] == read_guard(0);
  return out;
}

static void futex_wait_until(_Atomic uint32_t *word, uint32_t wanted)
{
  for (;;) {
    uint32_t current = atomic_load_explicit(word, memory_order_acquire);
    if (current >= wanted) return;
    if (syscall(SYS_futex, (uint32_t *)word, FUTEX_WAIT_PRIVATE,
                current, NULL, NULL, 0) < 0 && errno != EAGAIN && errno != EINTR)
      fail("futex wait");
  }
}

static void futex_wake(_Atomic uint32_t *word)
{
  if (syscall(SYS_futex, (uint32_t *)word, FUTEX_WAKE_PRIVATE, 1,
              NULL, NULL, 0) < 0) fail("futex wake");
}

static void sleep_ms(long ms)
{
  struct timespec delay = { .tv_sec = 0, .tv_nsec = ms * 1000000L };
  while (nanosleep(&delay, &delay) && errno == EINTR) {}
}

static void *thread_peer(void *arg)
{
  struct thread_case *test = arg;
  pin_first_cpu();
  register_descriptor();
  for (uint32_t trial = 1; trial <= repetitions; ++trial) {
    struct sample *sample = &test->samples[trial - 1];
    sample->before = snapshot();
    atomic_store_explicit(&test->ready, trial, memory_order_release);
    futex_wake(&test->ready);
    if (test->mode == idle) sleep_ms(5);
    else futex_wait_until(&test->phase, trial);
    sample->after = snapshot();
    atomic_store_explicit(&test->done, trial, memory_order_release);
    futex_wake(&test->done);
  }
  return NULL;
}

static unsigned report(unsigned mode, unsigned trial, const struct sample *sample)
{
  unsigned long delta[guards];
  for (unsigned i = 0; i < guards; ++i) {
    if (sample->after.guard[i] < sample->before.guard[i])
      fail("preview guard count reversed");
    delta[i] = sample->after.guard[i] - sample->before.guard[i];
  }
  if (sample->after.hook < sample->before.hook)
    fail("preview hook count reversed");
  unsigned long hook = sample->after.hook - sample->before.hook;
  unsigned stable = sample->before.stable && sample->after.stable;
  unsigned pure = stable && delta[0] == 1 &&
    delta[1] == (mode == idle) && delta[2] == (mode == different_mm) &&
    delta[3] == 0 && delta[4] == 0 && hook == (mode == same_mm);
  printf("PREVIEW_PATH mode=%u trial=%u selected=%lu idle=%lu different_mm=%lu descriptor=%lu empty=%lu hook=%lu stable=%u pure=%u\n",
         mode, trial, delta[0], delta[1], delta[2], delta[3], delta[4],
         hook, stable, pure);
  return pure;
}

static unsigned run_thread_case(unsigned mode)
{
  struct thread_case test = { .mode = mode };
  pthread_t peer;
  int rc = pthread_create(&peer, NULL, thread_peer, &test);
  if (rc) { errno = rc; fail("pthread create"); }
  for (uint32_t trial = 1; trial <= repetitions; ++trial) {
    futex_wait_until(&test.ready, trial);
    if (mode == idle) sleep_ms(10);
    else {
      atomic_store_explicit(&test.phase, trial, memory_order_release);
      futex_wake(&test.phase);
    }
    futex_wait_until(&test.done, trial);
  }
  rc = pthread_join(peer, NULL);
  if (rc) { errno = rc; fail("pthread join"); }
  unsigned pure = 0;
  for (unsigned trial = 0; trial < repetitions; ++trial)
    pure += report(mode, trial + 1, &test.samples[trial]);
  return pure;
}

static void read_all(int fd, void *buffer, size_t size)
{
  char *cursor = buffer;
  while (size) {
    ssize_t got = read(fd, cursor, size);
    if (got <= 0) fail("read pipe");
    cursor += got;
    size -= (size_t)got;
  }
}

static void write_all(int fd, const void *buffer, size_t size)
{
  const char *cursor = buffer;
  while (size) {
    ssize_t sent = write(fd, cursor, size);
    if (sent <= 0) fail("write pipe");
    cursor += sent;
    size -= (size_t)sent;
  }
}

static unsigned run_different_mm(void)
{
  int parent_to_child[2], child_to_parent[2];
  if (pipe(parent_to_child) || pipe(child_to_parent)) fail("pipe");
  pid_t child = fork();
  if (child < 0) fail("fork");
  if (child == 0) {
    close(parent_to_child[1]);
    close(child_to_parent[0]);
    pin_first_cpu();
    register_descriptor();
    for (unsigned trial = 0; trial < repetitions; ++trial) {
      struct sample sample = { .before = snapshot() };
      char token = 'R';
      write_all(child_to_parent[1], &token, 1);
      read_all(parent_to_child[0], &token, 1);
      sample.after = snapshot();
      write_all(child_to_parent[1], &sample, sizeof(sample));
    }
    _exit(0);
  }
  close(parent_to_child[0]);
  close(child_to_parent[1]);
  unsigned pure = 0;
  for (unsigned trial = 0; trial < repetitions; ++trial) {
    char token;
    struct sample sample;
    read_all(child_to_parent[0], &token, 1);
    if (token != 'R') fail("child ready token");
    write_all(parent_to_child[1], &token, 1);
    read_all(child_to_parent[0], &sample, sizeof(sample));
    pure += report(different_mm, trial + 1, &sample);
  }
  close(parent_to_child[1]);
  close(child_to_parent[0]);
  int status;
  if (waitpid(child, &status, 0) != child || !WIFEXITED(status) ||
      WEXITSTATUS(status) != 0) fail("child failed");
  return pure;
}

int main(void)
{
  pin_first_cpu();
  target_line[0] = 1;
  unsigned same = run_thread_case(same_mm);
  unsigned from_idle = run_thread_case(idle);
  unsigned from_other_mm = run_different_mm();
  printf("PREVIEW_PATH_RESULT same=%u idle=%u different_mm=%u of=%u\n",
         same, from_idle, from_other_mm, repetitions);
  if (!same || !from_idle || !from_other_mm) return EXIT_FAILURE;
  puts("PREVIEW_PATH PASS");
  return EXIT_SUCCESS;
}
