/* Compare independent Linux request threads with a single batched load loop.
 * The same deterministic request streams and checksums are used in both modes.
 * Hardware-context modes require an explicit --hardware and a fresh Linux boot.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifndef BP_REQUEST_LOAD_AHEAD
#define BP_REQUEST_LOAD_AHEAD 0
#endif
#if BP_REQUEST_LOAD_AHEAD != 0 && BP_REQUEST_LOAD_AHEAD != 1
#error "BP_REQUEST_LOAD_AHEAD must be zero (prefetch hint) or one (faulting load control)"
#endif

#if defined(__riscv) && __riscv_xlen == 64
#include "../testing/mt_seed.h"
#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "The Linux hardware candidate requires two resident slots and four logical contexts"
#endif
#if BP_REQUEST_LOAD_AHEAD
#include "../software/include/bp_load_ahead.h"
#define BACKEND "blackparrot-faulting-lbu-x0"
#define REQUEST_AHEAD_ASM(base) BP_LOAD_AHEAD_ASM(base)
static inline void request_prefetch(const volatile void *p) { bp_load_ahead(p); }
#else
#include "../software/include/bp_prefetch.h"
#define BACKEND "blackparrot-zicbop-prefetch-r-l2"
#define REQUEST_AHEAD_ASM(base) BP_PREFETCH_R_ASM(base)
static inline void request_prefetch(const volatile void *p) { bp_prefetch_r(p); }
#endif
#elif defined(__x86_64__) || defined(__i386__)
#if BP_REQUEST_LOAD_AHEAD
#error "The faulting-load control requires BlackParrot RV64"
#endif
#define BACKEND "x86-prefetcht0"
static inline void request_prefetch(const volatile void *p)
{
  __asm__ volatile ("prefetcht0 (%0)" : : "r"(p) : "memory");
}
#else
#error "No verified prefetch backend for this architecture"
#endif

#if BP_REQUEST_LOAD_AHEAD
#define BATCH_MODE "batched-load-ahead-load"
#define RESIDENT_AHEAD_MODE "resident-load-ahead-yield-load"
#else
#define BATCH_MODE "batched-prefetch-load"
#define RESIDENT_AHEAD_MODE "resident-prefetch-yield-load"
#endif

#define MAX_WORKERS 64u
#define LINE_BYTES 64u
#define MAX_ALLOCATION (UINT64_C(512) * 1024 * 1024)
struct options { unsigned workers, requests, samples, data_kib; int cpu, hardware; };
struct worker { unsigned id; uint64_t sum; };
static struct options opt = {2, 4096, 5, 2048, -1, 0};
static unsigned char *data, *eviction;
static uint32_t *requests;
static size_t data_bytes, line_count;
static uint64_t expected[MAX_WORKERS];
/* A runtime zero gives each next index a real dependency on the previous
 * response. It prevents out-of-order CPUs from quietly batching the baseline.
 * It is read once per worker/trial, not once per request. */
static volatile uint64_t dependency_zero;
static volatile uint64_t eviction_sink;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t work_ready = PTHREAD_COND_INITIALIZER;
static pthread_cond_t work_done = PTHREAD_COND_INITIALIZER;
static pthread_barrier_t startup;
static unsigned generation, completed;
static int stopping;
struct timing { uint64_t ns, cycles; };
static struct timing threaded_end;

static void fail(const char *what, int error)
{
  fprintf(stderr, "request_benchmark: %s: %s\n", what, strerror(error));
  exit(EXIT_FAILURE);
}
static void check(int error, const char *what) { if (error) fail(what, error); }
static uint64_t now_ns(void)
{
  struct timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t)) fail("clock_gettime", errno);
  return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}
static uint64_t core_cycles(void)
{
#if defined(__riscv) && __riscv_xlen == 64
  uint64_t value;
  __asm__ volatile ("csrr %0, 0xcc0" : "=r"(value) : : "memory");
  return value;
#else
  return 0;
#endif
}
/* The cycle interval is nested inside the wall-clock interval. It excludes
 * clock_gettime itself; both cover the complete request operation. */
static struct timing timer_start(void)
{
  struct timing stamp;
  stamp.ns = now_ns(); stamp.cycles = core_cycles();
  return stamp;
}
static struct timing timer_end(void)
{
  struct timing stamp;
  stamp.cycles = core_cycles(); stamp.ns = now_ns();
  return stamp;
}
static struct timing elapsed(struct timing start, struct timing end)
{
  if (end.ns < start.ns || end.cycles < start.cycles) {
    fprintf(stderr, "measurement clock moved backwards\n"); exit(EXIT_FAILURE);
  }
  return (struct timing){end.ns - start.ns, end.cycles - start.cycles};
}
static unsigned number(const char *text, unsigned maximum)
{
  /* The SDK's GNU headers redirect strtoul to GLIBC_2.38. Parse bounded
   * decimal directly so this ELF also works with the boot image's libc. */
  unsigned value = 0;
  if (!text[0]) {
    fprintf(stderr, "invalid unsigned decimal: %s\n", text); exit(EXIT_FAILURE);
  }
  for (const char *p = text; *p; ++p) {
    if (*p < '0' || *p > '9') {
      fprintf(stderr, "invalid unsigned decimal: %s\n", text); exit(EXIT_FAILURE);
    }
    unsigned digit = (unsigned)(*p - '0');
    if (value > maximum / 10 ||
        (value == maximum / 10 && digit > maximum % 10)) {
      fprintf(stderr, "argument out of range: %s\n", text); exit(EXIT_FAILURE);
    }
    value = value * 10 + digit;
  }
  return value;
}
static void usage(FILE *f)
{
  fprintf(f, "usage: request_benchmark [--workers 1..64] [--requests 1..1048576]\n"
             "       [--samples 1..1000] [--data-kib power-of-two: 1..262144]\n"
             "       [--cpu CPU] [--hardware] [--help]\n"
             "Defaults: workers=2 requests=4096 samples=5 data-kib=2048;\n"
             "CPU defaults to the first allowed CPU. Requests are per worker.\n");
}
static void parse(int argc, char **argv)
{
  for (int i = 1; i < argc; ++i) {
    const char *name = argv[i];
    if (!strcmp(name, "--help")) { usage(stdout); exit(EXIT_SUCCESS); }
    if (!strcmp(name, "--hardware")) { opt.hardware = 1; continue; }
    if (i + 1 == argc) { usage(stderr); exit(EXIT_FAILURE); }
    const char *value = argv[++i];
    if (!strcmp(name, "--workers")) opt.workers = number(value, MAX_WORKERS);
    else if (!strcmp(name, "--requests")) opt.requests = number(value, 1048576);
    else if (!strcmp(name, "--samples")) opt.samples = number(value, 1000);
    else if (!strcmp(name, "--data-kib")) opt.data_kib = number(value, 262144);
    else if (!strcmp(name, "--cpu")) opt.cpu = (int)number(value, CPU_SETSIZE - 1);
    else { usage(stderr); exit(EXIT_FAILURE); }
  }
  if (!opt.workers || !opt.requests || !opt.samples || !opt.data_kib ||
      (opt.data_kib & (opt.data_kib - 1))) {
    usage(stderr); exit(EXIT_FAILURE);
  }
  if (opt.hardware) {
#if !defined(__riscv) || __riscv_xlen != 64
    fprintf(stderr, "--hardware requires BlackParrot RV64\n"); exit(EXIT_FAILURE);
#endif
    if (opt.workers != 2) {
      fprintf(stderr, "--hardware requires exactly two workers\n"); exit(EXIT_FAILURE);
    }
  }
  data_bytes = (size_t)opt.data_kib * 1024;
  line_count = data_bytes / LINE_BYTES;
  if ((uint64_t)data_bytes * 3 +
      (uint64_t)opt.workers * opt.requests * sizeof(*requests) > MAX_ALLOCATION) {
    fprintf(stderr, "requested data, eviction, and index arrays exceed 512 MiB\n");
    exit(EXIT_FAILURE);
  }
}
static void pin_cpu(void)
{
  cpu_set_t allowed, selected;
  if (sched_getaffinity(0, sizeof(allowed), &allowed)) fail("sched_getaffinity", errno);
  if (opt.cpu < 0) {
    for (int i = 0; i < CPU_SETSIZE; ++i)
      if (CPU_ISSET(i, &allowed)) { opt.cpu = i; break; }
  }
  if (opt.cpu < 0 || !CPU_ISSET(opt.cpu, &allowed)) {
    fprintf(stderr, "selected CPU is outside the allowed affinity mask\n");
    exit(EXIT_FAILURE);
  }
  CPU_ZERO(&selected);
  CPU_SET(opt.cpu, &selected);
  if (sched_setaffinity(0, sizeof(selected), &selected)) fail("sched_setaffinity", errno);
  if (sched_getaffinity(0, sizeof(allowed), &allowed)) fail("verify affinity", errno);
  if (CPU_COUNT(&allowed) != 1 || !CPU_ISSET(opt.cpu, &allowed)) {
    fprintf(stderr, "affinity verification failed\n"); exit(EXIT_FAILURE);
  }
}
static uint32_t next_random(uint32_t x)
{
  x ^= x << 13; x ^= x >> 17; x ^= x << 5;
  return x;
}
static void prepare(void)
{
  check(posix_memalign((void **)&data, LINE_BYTES, data_bytes), "allocate data");
  check(posix_memalign((void **)&eviction, LINE_BYTES, data_bytes * 2), "allocate eviction");
  requests = malloc((size_t)opt.workers * opt.requests * sizeof(*requests));
  if (!requests) fail("allocate indices", errno);
  memset(data, 0, data_bytes);
  memset(eviction, 0, data_bytes * 2);
  for (size_t i = 0; i < line_count; ++i)
    *(uint64_t *)(data + i * LINE_BYTES) = (uint64_t)i + 1;
  for (unsigned w = 0; w < opt.workers; ++w) {
    uint32_t state = UINT32_C(0x9e3779b9) ^ (w + 1);
    for (unsigned r = 0; r < opt.requests; ++r) {
      state = next_random(state);
      uint32_t index = state & (uint32_t)(line_count - 1);
      requests[(size_t)w * opt.requests + r] = index;
      expected[w] += (uint64_t)index + 1;
    }
  }
}
/* Best-effort cache displacement, not an architectural cache flush. Random
 * streams can revisit lines; cache misses must be measured, never assumed. */
static void displace_cache(void)
{
  uint64_t sum = 0;
  for (size_t i = 0; i < data_bytes * 2; i += LINE_BYTES)
    sum += *(volatile uint64_t *)(eviction + i);
  eviction_sink = sum;
}
static void barrier_wait(void)
{
  int rc = pthread_barrier_wait(&startup);
  if (rc != 0 && rc != PTHREAD_BARRIER_SERIAL_THREAD) fail("startup barrier", rc);
}
static void *worker_main(void *argument)
{
  struct worker *worker = argument;
  unsigned seen = 0;
  /* Children inherit the parent's singleton affinity. Verify it individually. */
  pin_cpu();
  barrier_wait();
  check(pthread_mutex_lock(&lock), "worker lock");
  for (;;) {
    while (!stopping && seen == generation)
      check(pthread_cond_wait(&work_ready, &lock), "worker wait");
    if (stopping) break;
    seen = generation;
    check(pthread_mutex_unlock(&lock), "worker unlock");
    uint64_t sum = 0, zero = dependency_zero;
    const uint32_t *stream = requests + (size_t)worker->id * opt.requests;
    for (unsigned r = 0; r < opt.requests; ++r) {
      uint32_t index = stream[r + (sum & zero)];
      sum += *(volatile uint64_t *)(data + (size_t)index * LINE_BYTES);
    }
    worker->sum = sum;
    check(pthread_mutex_lock(&lock), "worker finish lock");
    if (++completed == opt.workers) {
      threaded_end = timer_end();
      check(pthread_cond_signal(&work_done), "worker done signal");
    }
  }
  check(pthread_mutex_unlock(&lock), "worker exit unlock");
  return NULL;
}
static struct timing run_threads(struct worker *workers, uint64_t *sums)
{
  check(pthread_mutex_lock(&lock), "start lock");
  completed = 0;
  ++generation;
  struct timing start = timer_start();
  check(pthread_cond_broadcast(&work_ready), "start broadcast");
  while (completed != opt.workers)
    check(pthread_cond_wait(&work_done, &lock), "completion wait");
  struct timing duration = elapsed(start, threaded_end);
  for (unsigned w = 0; w < opt.workers; ++w) sums[w] = workers[w].sum;
  check(pthread_mutex_unlock(&lock), "finish unlock");
  return duration;
}
static struct timing run_batched(uint64_t *sums)
{
  const volatile uint64_t *addresses[MAX_WORKERS];
  memset(sums, 0, opt.workers * sizeof(*sums));
  uint64_t zero = dependency_zero;
  struct timing start = timer_start();
  for (unsigned r = 0; r < opt.requests; ++r) {
    for (unsigned w = 0; w < opt.workers; ++w) {
      uint32_t index = requests[(size_t)w * opt.requests + r + (sums[w] & zero)];
      addresses[w] = (volatile uint64_t *)(data + (size_t)index * LINE_BYTES);
      request_prefetch(addresses[w]);
    }
    for (unsigned w = 0; w < opt.workers; ++w) sums[w] += *addresses[w];
  }
  return elapsed(start, timer_end());
}

#if defined(__riscv) && __riscv_xlen == 64
/* Both source and peer are leaf assembly: no C calls, stack use, TLS access,
 * or syscalls occur in context 1. Each address depends on the worker's own
 * prior response through the same runtime-zero mask as the pthread baseline.
 * a0=data, a1=stream, a2=count, a3=zero; peer a4=completion record. */
#define REQUEST_ADDRESS \
  "and t0, t3, a3\nslli t0, t0, 2\nadd t0, a1, t0\n" \
  "lwu t0, 0(t0)\nslli t0, t0, 6\nadd t0, a0, t0\n"
#define REQUEST_CONSUME "ld t1, 0(t0)\nadd t3, t3, t1\n"
#define REQUEST_ADVANCE "addi a1, a1, 4\naddi a2, a2, -1\n"
#define HARDWARE_LOOPS(name, source_work, peer_work) \
static __attribute__((naked, noinline, used, aligned(8))) \
uint64_t source_##name(const void *base __attribute__((unused)), \
                      const uint32_t *stream __attribute__((unused)), \
                      uint64_t count __attribute__((unused)), \
                      uint64_t zero __attribute__((unused))) \
{ \
  __asm__ volatile (".option push\n.option norvc\nli t3, 0\n1:\n" \
    REQUEST_ADDRESS source_work REQUEST_ADVANCE "bnez a2, 1b\n" \
    /* Complete the peer's last response and collect its record before return. */ \
    "csrwi 0x800, 1\nmv a0, t3\nret\n.option pop\n"); \
} \
static __attribute__((naked, noinline, noreturn, used, aligned(8))) \
void peer_##name(void) \
{ \
  __asm__ volatile (".option push\n.option norvc\nli t3, 0\nli t4, 0\n1:\n" \
    REQUEST_ADDRESS peer_work REQUEST_ADVANCE "addi t4, t4, 1\nbnez a2, 1b\n" \
    "sd t3, 0(a4)\nsd t4, 8(a4)\ncsrr t0, 0x800\nsd t0, 16(a4)\n" \
    "fence rw, rw\ncsrwi 0x800, 0\n2: j 2b\n.option pop\n"); \
}
HARDWARE_LOOPS(demand, "csrwi 0x800, 1\n" REQUEST_CONSUME,
                       "csrwi 0x800, 0\n" REQUEST_CONSUME)
HARDWARE_LOOPS(ahead, REQUEST_AHEAD_ASM("t0") "csrwi 0x800, 1\n" REQUEST_CONSUME,
                      REQUEST_AHEAD_ASM("t0") "csrwi 0x800, 0\n" REQUEST_CONSUME)

static uint64_t current_context(void)
{
  uint64_t id;
  __asm__ volatile ("csrr %0, 0x800" : "=r"(id) : : "memory");
  return id;
}
static struct timing run_hardware(unsigned ahead, uint64_t *sums)
{
  volatile uint64_t result[3] = {0, 0, 0};
  uint64_t (*source)(const void *, const uint32_t *, uint64_t, uint64_t) =
    ahead ? source_ahead : source_demand;
  void (*peer)(void) = ahead ? peer_ahead : peer_demand;
  if (current_context() != 0) {
    fprintf(stderr, "hardware mode requires source context zero\n"); exit(EXIT_FAILURE);
  }
  seed_reg(1, 10, (uintptr_t)data);
  seed_reg(1, 11, (uintptr_t)(requests + opt.requests));
  seed_reg(1, 12, opt.requests);
  seed_reg(1, 13, dependency_zero);
  seed_reg(1, 14, (uintptr_t)result);
  /* Sample wall time before installing the peer's inherited Linux state.
   * Keep the proven NPC-seed -> counter-read -> handoff launch sequence free
   * of deliberate syscalls. Wall time includes this final seed; cycles do not.
   */
  struct timing start;
  start.ns = now_ns();
  seed_npc(1, (uintptr_t)peer);
  start.cycles = core_cycles();
  sums[0] = source(data, requests, opt.requests, dependency_zero);
  struct timing duration = elapsed(start, timer_end());
  if (current_context() != 0 || result[1] != opt.requests || result[2] != 1) {
    fprintf(stderr, "hardware context/completion verification failed\n"); exit(EXIT_FAILURE);
  }
  sums[1] = result[0];
  return duration;
}
#endif

int main(int argc, char **argv)
{
  pthread_t threads[MAX_WORKERS];
  struct worker workers[MAX_WORKERS];
  uint64_t sums[MAX_WORKERS], total_expected = 0;
  parse(argc, argv);
  pin_cpu();
  prepare();
  check(pthread_barrier_init(&startup, NULL, opt.workers + 1), "startup barrier init");
  for (unsigned w = 0; w < opt.workers; ++w) {
    workers[w] = (struct worker){w, 0};
    total_expected += expected[w];
    check(pthread_create(&threads[w], NULL, worker_main, &workers[w]), "create worker");
  }
  barrier_wait();
  const unsigned modes = opt.hardware ? 4 : 2;
  const char *mode_names[] = {"linux-threads-demand", BATCH_MODE,
                             "resident-demand-handoff", RESIDENT_AHEAD_MODE};
  printf("REQUEST_BENCH backend=%s cpu=%d workers=%u hardware=%d requests_per_worker=%u "
         "data_bytes=%zu samples=%u seed=xorshift32-9e3779b9 checksum=%" PRIu64 "\n",
         BACKEND, opt.cpu, opt.workers, opt.hardware, opt.requests, data_bytes, opt.samples, total_expected);
  printf("TIMING clock=monotonic unit=ns setup=excluded thread_release_and_drain=included "
         "cache=2x-data-displacement-no-flush\n");
  fflush(stdout);
  /* Trial zero warms and checks every path. Measured order rotates. */
  for (unsigned trial = 0; trial <= opt.samples; ++trial) {
    for (unsigned order = 0; order < modes; ++order) {
      unsigned mode = (order + trial) % modes;
      if (!trial) {
        printf("WARMUP_BEGIN mode=%s\n", mode_names[mode]);
        fflush(stdout);
      }
      displace_cache();
      struct timing duration;
      if (mode == 0) duration = run_threads(workers, sums);
      else if (mode == 1) duration = run_batched(sums);
#if defined(__riscv) && __riscv_xlen == 64
      else duration = run_hardware(mode == 3, sums);
#else
      else { fprintf(stderr, "unsupported hardware mode\n"); return EXIT_FAILURE; }
#endif
      uint64_t total = 0;
      for (unsigned w = 0; w < opt.workers; ++w) {
        if (sums[w] != expected[w]) {
          fprintf(stderr, "CHECKSUM_FAIL mode=%s worker=%u got=%" PRIu64 " expected=%" PRIu64 "\n",
                  mode_names[mode], w, sums[w], expected[w]);
          return EXIT_FAILURE;
        }
        total += sums[w];
      }
      if (!trial) {
        printf("WARMUP_PASS mode=%s\n", mode_names[mode]);
        fflush(stdout);
      }
      if (trial) {
        printf("RESULT sample=%u order=%u mode=%s ns=%" PRIu64 " requests=%" PRIu64
               " checksum=%" PRIu64, trial, order,
               mode_names[mode], duration.ns,
               (uint64_t)opt.workers * opt.requests, total);
#if defined(__riscv) && __riscv_xlen == 64
        printf(" cycles=%" PRIu64, duration.cycles);
#endif
        putchar('\n');
        fflush(stdout);
      }
    }
  }
  check(pthread_mutex_lock(&lock), "stop lock");
  stopping = 1;
  check(pthread_cond_broadcast(&work_ready), "stop broadcast");
  check(pthread_mutex_unlock(&lock), "stop unlock");
  for (unsigned w = 0; w < opt.workers; ++w)
    check(pthread_join(threads[w], NULL), "join worker");
  check(pthread_barrier_destroy(&startup), "destroy startup barrier");
  check(pthread_cond_destroy(&work_ready), "destroy work condition");
  check(pthread_cond_destroy(&work_done), "destroy completion condition");
  check(pthread_mutex_destroy(&lock), "destroy mutex");
  free(requests); free(eviction); free(data);
  puts("[REQUEST-BENCH] PASS");
  return EXIT_SUCCESS;
}
