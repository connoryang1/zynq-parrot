/* Compare serial, software-batched, and hardware-context binary searches in
 * one executable. This is an algorithmic port of Gor Nishanov's Nano-
 * coroutines multi-lookup benchmark: independent searches prefetch an
 * unpredictable midpoint, yield, and consume it after other searches issue.
 */
#include <stdint.h>
#include <stddef.h>
#include <coroutine>
#include "bp_utils.h"
#include "mt_seed.h"
#include "bp_prefetch.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 10
#error "Use NUM_THREADS=2 NUM_CONTEXTS=10"
#endif

#define SIGNAL_BASE_ADDR ((volatile uint8_t *)0x00104000)
#define BEGIN_MARKER_BASE 0x60
#define END_MARKER_BASE   0x70
#define STACK_WORDS 256

/* A detached hint supplies two one-shot 8-byte side-buffer words. Read the
 * packed links with one aligned 64-bit load, then select the branch half in
 * registers; the advisory hit path does not shift unaligned subword loads. */
struct index_line {
  uint64_t key;
  uint64_t packed_links;
  uint64_t pad[6];
};
static_assert(sizeof(struct index_line) == 64, "one index key per cache line");
static_assert(offsetof(struct index_line, packed_links) + sizeof(uint64_t) == 16,
              "key and branch links must occupy separate hinted 8-byte words");
extern "C" {
#include "nano_lookup_data.h"
}

enum benchmark_mode {
  MODE_SERIAL_DEMAND = 0,
  MODE_DEMAND_RING = 1,
  MODE_WORKER_PREFETCH = 2,
  MODE_MATCHED_BATCH = 3,
  MODE_SWITCH_ONLY = 4,
  MODE_SERIAL_PREFETCH = 5,
  MODE_CPP_COROUTINE = 6,
  MODE_FIXED_SOA_BATCH = 7,
  MODE_FIXED_RECOMPUTE_BATCH = 8,
  MODE_LEAN_COROUTINE = 9,
  MODE_DIRECT_COROUTINE = 10,
  MODE_COUNT
};

struct lookup_result {
  uint64_t lower_bound;
  uint64_t checksum;
  uint64_t steps;
  uint64_t done;
};

static volatile struct lookup_result results[NANO_LOOKUP_WORKERS]
  __attribute__((aligned(4096), used));
static uint64_t stacks[NANO_LOOKUP_WORKERS][STACK_WORDS]
  __attribute__((aligned(64)));
static const volatile struct index_line *measured_tables[NANO_LOOKUP_WORKERS];
static const volatile struct index_line *warm_tables[NANO_LOOKUP_WORKERS];
static unsigned active_workers = NANO_LOOKUP_WORKERS;

/* The coroutine scheduler uses the same ten-worker round-robin order as the
 * hardware ring. Frames are created before the measured window and destroyed
 * afterward, so the timed interval charges only useful lookup work and actual
 * C++ coroutine suspend/resume scheduling. */
struct coroutine_scheduler {
  std::coroutine_handle<> queue[NANO_LOOKUP_WORKERS];
  unsigned head = 0;
  unsigned tail = 0;
  unsigned count = 0;

  void reset()
  {
    head = tail = count = 0;
  }

  void push(std::coroutine_handle<> handle)
  {
    if (count >= NANO_LOOKUP_WORKERS) {
      bp_print_string((char *)"[BSG-FAIL] nano coroutine queue overflow\n");
      bp_finish(1);
    }
    queue[head] = handle;
    head = (head + 1) % NANO_LOOKUP_WORKERS;
    ++count;
  }

  std::coroutine_handle<> pop()
  {
    if (!count) {
      bp_print_string((char *)"[BSG-FAIL] nano coroutine queue underflow\n");
      bp_finish(1);
    }
    std::coroutine_handle<> handle = queue[tail];
    tail = (tail + 1) % NANO_LOOKUP_WORKERS;
    --count;
    return handle;
  }

  void run()
  {
    while (count) pop().resume();
  }
};

static coroutine_scheduler cpp_scheduler;

/* A power-of-two queue removes the division, count maintenance, and checked
 * push/pop branches from the timed coroutine scheduler. The benchmark never
 * has more than ten live handles, so a sixteen-entry ring cannot become full. */
struct lean_coroutine_scheduler {
  std::coroutine_handle<> queue[16];
  unsigned head = 0;
  unsigned tail = 0;

  void reset() { head = tail = 0; }
  void push(std::coroutine_handle<> handle)
  {
    queue[head] = handle;
    head = (head + 1) & 15;
  }
  std::coroutine_handle<> pop()
  {
    std::coroutine_handle<> handle = queue[tail];
    tail = (tail + 1) & 15;
    return handle;
  }
  void run()
  {
    while (head != tail) pop().resume();
  }
};

static lean_coroutine_scheduler lean_scheduler;

/* Avoid pulling the hosted C++ allocator and exception runtime into this
 * freestanding benchmark. All ten frames coexist, are created outside the
 * timed window, and are reclaimed together after the scheduler drains. */
#define CPP_COROUTINE_FRAME_BYTES 512
alignas(16) static uint8_t cpp_frame_storage[NANO_LOOKUP_WORKERS]
  [CPP_COROUTINE_FRAME_BYTES];
static unsigned cpp_frame_next;

struct nano_task {
  struct promise_type;
  using handle_type = std::coroutine_handle<promise_type>;

  struct promise_type {
    static void *operator new(size_t size)
    {
      if (size > CPP_COROUTINE_FRAME_BYTES || cpp_frame_next >= NANO_LOOKUP_WORKERS) {
        bp_print_string((char *)"[BSG-FAIL] nano coroutine frame pool exhausted\n");
        bp_finish(1);
      }
      return cpp_frame_storage[cpp_frame_next++];
    }
    static void operator delete(void *, size_t) noexcept {}

    nano_task get_return_object()
    {
      return nano_task{handle_type::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    void return_void() noexcept {}
    void unhandled_exception() noexcept
    {
      bp_print_string((char *)"[BSG-FAIL] nano coroutine exception\n");
      bp_finish(1);
    }
  };

  handle_type handle = nullptr;

  nano_task() = default;
  explicit nano_task(handle_type value) : handle(value) {}
  nano_task(const nano_task &) = delete;
  nano_task &operator=(const nano_task &) = delete;
  nano_task(nano_task &&other) noexcept : handle(other.handle)
  {
    other.handle = nullptr;
  }
  nano_task &operator=(nano_task &&other) noexcept
  {
    if (handle) handle.destroy();
    handle = other.handle;
    other.handle = nullptr;
    return *this;
  }
  void destroy()
  {
    if (handle) handle.destroy();
    handle = nullptr;
  }
};

static nano_task cpp_tasks[NANO_LOOKUP_WORKERS];

template <unsigned ScheduleMode>
struct prefetch_and_yield {
  const volatile struct index_line *line;
  unsigned next;

  bool await_ready() const noexcept { return false; }
  void await_resume() const noexcept {}
  std::coroutine_handle<> await_suspend(std::coroutine_handle<> current) const
  {
    bp_prefetch_r(line);
    if constexpr (ScheduleMode == MODE_DIRECT_COROUTINE) {
      return cpp_tasks[next].handle;
    } else if constexpr (ScheduleMode == MODE_LEAN_COROUTINE) {
      lean_scheduler.push(current);
      return lean_scheduler.pop();
    } else {
      cpp_scheduler.push(current);
      return cpp_scheduler.pop();
    }
  }
};

/* Patched in the unchanged ELF/NBF before the processor is released. */
volatile uint64_t benchmark_mode __attribute__((section(".data"))) = UINT64_MAX;

static inline void switch_to(uint64_t next)
{
  __asm__ volatile("csrw 0x800, %0" : : "r"(next) : "memory");
}

static inline void publish(volatile struct lookup_result *out, uint64_t lower,
                           uint64_t checksum, uint64_t steps)
{
  out->lower_bound = lower;
  out->checksum = checksum;
  out->steps = steps;
  out->done = 1;
}

/* Every hardware context runs this body with context-private arguments:
 *   a0 table, a1 entries, a2 key, a3 result, a4 mode, a5 next context,
 *   a6 park after the terminal lap, a7 fixed search depth.
 *
 * Demand and prefetch workers calculate identical midpoints and hand off once
 * before every consuming load. The candidate alone issues the nonfaulting
 * hint before yielding. The switch-only control executes the same number of
 * handoffs and publishes through the same result block without data accesses.
 */
static __attribute__((noinline, noclone, aligned(64),
                      optimize("no-unroll-loops"))) void lookup_worker(
  const volatile struct index_line *table, uint64_t entries, uint64_t key,
  volatile struct lookup_result *out, uint64_t mode, uint64_t next,
  uint64_t park, uint64_t levels)
{
  uint64_t lower = 0, length = entries, checksum = 0, steps = 0, node = 0;

  if (mode == MODE_SWITCH_ONLY) {
    while (steps++ < levels) switch_to(next);
    publish(out, 0, 0, levels);
  } else {
    while (length) {
      uint64_t half = length >> 1;
      uint64_t middle = lower + half;
      const volatile struct index_line *line = &table[node];
      if (mode == MODE_WORKER_PREFETCH) bp_prefetch_r(line);
      switch_to(next);
      uint64_t value;
      __asm__ volatile(
        ".ifndef nano_worker_consume_load\n"
        ".global nano_worker_consume_load\n"
        "nano_worker_consume_load:\n"
        ".endif\n"
        "ld %0, 0(%1)\n" : "=r"(value) : "r"(line) : "memory");
      uint64_t links = line->packed_links;
      checksum += value;
      ++steps;
      if (value < key) {
        node = (uint32_t)links;
        lower = middle + 1;
        length -= half + 1;
      } else {
        node = links >> 32;
        length = half;
      }
    }
    publish(out, lower, checksum, steps);
  }

  /* Context zero returns only after the other nine workers publish and pass
   * control around the terminal lap. Other workers are never resumed. */
  /* Keep a parked worker's post-switch path unconditional.  Testing park
   * after the CSR lets the frontend predict through the following return and
   * start an irrelevant blocking I-cache refill before redirect acceptance. */
  if (park) {
    __asm__ volatile(
      "csrw 0x800, %0\n"
      "1: j 1b\n" : : "r"(next) : "memory");
  }
  switch_to(next);
}

static __attribute__((noinline, noclone,
                      optimize("no-unroll-loops"))) void serial_lookup(
  const volatile struct index_line *const *tables, uint64_t entries,
  const uint64_t *queries, unsigned prefetch)
{
  for (unsigned worker = 0; worker < active_workers; ++worker) {
    uint64_t lower = 0, length = entries, checksum = 0, steps = 0, node = 0;
    while (length) {
      uint64_t half = length >> 1;
      uint64_t middle = lower + half;
      const volatile struct index_line *line = &tables[worker][node];
      if (prefetch) bp_prefetch_r(line);
      uint64_t value;
      __asm__ volatile(
        ".ifndef nano_serial_consume_load\n"
        ".global nano_serial_consume_load\n"
        "nano_serial_consume_load:\n"
        ".endif\n"
        "ld %0, 0(%1)\n" : "=r"(value) : "r"(line) : "memory");
      uint64_t links = line->packed_links;
      checksum += value;
      ++steps;
      if (value < queries[worker]) {
        node = (uint32_t)links;
        lower = middle + 1;
        length -= half + 1;
      } else {
        node = links >> 32;
        length = half;
      }
    }
    publish(&results[worker], lower, checksum, steps);
  }
}

/* This is a compiler-generated C++20 coroutine frame, not a hand-written
 * state machine. Symmetric transfer selects the next queued search directly
 * at every prefetch suspension, matching Nishanov's Nano-coroutine schedule. */
template <unsigned ScheduleMode>
static nano_task coroutine_lookup(
  const volatile struct index_line *table, uint64_t entries, uint64_t key,
  volatile struct lookup_result *out, unsigned next, uint64_t levels)
{
  uint64_t lower = 0, length = entries, checksum = 0, node = 0;
  while (length) {
    const volatile struct index_line *line = &table[node];
    co_await prefetch_and_yield<ScheduleMode>{line, next};
    // Keep derived search state out of the coroutine frame. Recomputing these
    // cheap values after resumption avoids preserving them across every
    // suspension and matches the explicit batch's consume phase.
    uint64_t half = length >> 1;
    uint64_t middle = lower + half;
    uint64_t value;
    if constexpr (ScheduleMode == MODE_CPP_COROUTINE) {
      __asm__ volatile(
        ".ifndef nano_coroutine_checked_consume_load\n"
        ".global nano_coroutine_checked_consume_load\n"
        "nano_coroutine_checked_consume_load:\n"
        ".endif\n"
        "ld %0, 0(%1)\n" : "=r"(value) : "r"(line) : "memory");
    } else if constexpr (ScheduleMode == MODE_LEAN_COROUTINE) {
      __asm__ volatile(
        ".ifndef nano_coroutine_lean_consume_load\n"
        ".global nano_coroutine_lean_consume_load\n"
        "nano_coroutine_lean_consume_load:\n"
        ".endif\n"
        "ld %0, 0(%1)\n" : "=r"(value) : "r"(line) : "memory");
    } else {
      __asm__ volatile(
        ".ifndef nano_coroutine_direct_consume_load\n"
        ".global nano_coroutine_direct_consume_load\n"
        "nano_coroutine_direct_consume_load:\n"
        ".endif\n"
        "ld %0, 0(%1)\n" : "=r"(value) : "r"(line) : "memory");
    }
    uint64_t links = line->packed_links;
    checksum += value;
    if (value < key) {
      node = (uint32_t)links;
      lower = middle + 1;
      length -= half + 1;
    } else {
      node = links >> 32;
      length = half;
    }
  }
  publish(out, lower, checksum, levels);
}

/* This is both the explicit-state-machine baseline and the ideal matched
 * batch: issue one hint for each live search, then consume the same ten
 * midpoints under the processor's actual request-capacity/arbitration rules. */
static __attribute__((noinline, noclone,
                      optimize("no-unroll-loops"))) void matched_batch(
  const volatile struct index_line *const *tables, uint64_t entries,
  const uint64_t *queries, uint64_t levels)
{
  uint64_t lower[NANO_LOOKUP_WORKERS] = {0};
  uint64_t length[NANO_LOOKUP_WORKERS];
  uint64_t checksum[NANO_LOOKUP_WORKERS] = {0};
  uint64_t node[NANO_LOOKUP_WORKERS] = {0};
  const volatile struct index_line *lines[NANO_LOOKUP_WORKERS];

  for (unsigned i = 0; i < active_workers; ++i) length[i] = entries;
  for (uint64_t step = 0; step < levels; ++step) {
    for (unsigned i = 0; i < active_workers; ++i) {
      lines[i] = &tables[i][node[i]];
      bp_prefetch_r(lines[i]);
    }
    for (unsigned i = 0; i < active_workers; ++i) {
      uint64_t value;
      __asm__ volatile(
        ".ifndef nano_batch_consume_load\n"
        ".global nano_batch_consume_load\n"
        "nano_batch_consume_load:\n"
        ".endif\n"
        "ld %0, 0(%1)\n" : "=r"(value) : "r"(lines[i]) : "memory");
      uint64_t links = lines[i]->packed_links;
      uint64_t half = length[i] >> 1;
      uint64_t middle = lower[i] + half;
      checksum[i] += value;
      if (value < queries[i]) {
        node[i] = (uint32_t)links;
        lower[i] = middle + 1;
        length[i] -= half + 1;
      } else {
        node[i] = links >> 32;
        length[i] = half;
      }
    }
  }
  for (unsigned i = 0; i < active_workers; ++i)
    publish(&results[i], lower[i], checksum[i], levels);
}

/* Compile-time worker counts let the compiler unroll both phases and keep
 * per-search state in registers where profitable. This is the optimized form
 * of the same N-prefetches-then-N-loads schedule as matched_batch. */
template <unsigned N>
static __attribute__((noinline)) void fixed_soa_batch(
  const volatile struct index_line *const *tables, uint64_t entries,
  const uint64_t *queries, uint64_t levels)
{
  uint64_t lower[N] = {0};
  uint64_t length[N];
  uint64_t checksum[N] = {0};
  uint64_t node[N] = {0};
  const volatile struct index_line *lines[N];

#pragma GCC unroll 16
  for (unsigned i = 0; i < N; ++i) length[i] = entries;
  for (uint64_t step = 0; step < levels; ++step) {
#pragma GCC unroll 16
    for (unsigned i = 0; i < N; ++i) {
      lines[i] = &tables[i][node[i]];
      bp_prefetch_r(lines[i]);
    }
#pragma GCC unroll 16
    for (unsigned i = 0; i < N; ++i) {
      uint64_t value;
      __asm__ volatile("ld %0, 0(%1)" : "=r"(value) : "r"(lines[i]) : "memory");
      uint64_t links = lines[i]->packed_links;
      uint64_t half = length[i] >> 1;
      uint64_t middle = lower[i] + half;
      checksum[i] += value;
      if (value < queries[i]) {
        node[i] = (uint32_t)links;
        lower[i] = middle + 1;
        length[i] -= half + 1;
      } else {
        node[i] = links >> 32;
        length[i] = half;
      }
    }
  }
#pragma GCC unroll 16
  for (unsigned i = 0; i < N; ++i)
    publish(&results[i], lower[i], checksum[i], levels);
}

struct software_search_state {
  uint64_t lower;
  uint64_t length;
  uint64_t checksum;
  uint64_t node;
};

/* This version avoids the line-pointer array. It recomputes each address in
 * the consume phase, trading cheap arithmetic for one less explicit spill. */
template <unsigned N>
static __attribute__((noinline)) void fixed_recompute_batch(
  const volatile struct index_line *const *tables, uint64_t entries,
  const uint64_t *queries, uint64_t levels)
{
  software_search_state state[N];
#pragma GCC unroll 16
  for (unsigned i = 0; i < N; ++i) state[i] = {0, entries, 0, 0};
  for (uint64_t step = 0; step < levels; ++step) {
#pragma GCC unroll 16
    for (unsigned i = 0; i < N; ++i)
      bp_prefetch_r(&tables[i][state[i].node]);
#pragma GCC unroll 16
    for (unsigned i = 0; i < N; ++i) {
      const volatile struct index_line *line = &tables[i][state[i].node];
      uint64_t value;
      __asm__ volatile("ld %0, 0(%1)" : "=r"(value) : "r"(line) : "memory");
      uint64_t links = line->packed_links;
      uint64_t half = state[i].length >> 1;
      uint64_t middle = state[i].lower + half;
      state[i].checksum += value;
      if (value < queries[i]) {
        state[i].node = (uint32_t)links;
        state[i].lower = middle + 1;
        state[i].length -= half + 1;
      } else {
        state[i].node = links >> 32;
        state[i].length = half;
      }
    }
  }
#pragma GCC unroll 16
  for (unsigned i = 0; i < N; ++i)
    publish(&results[i], state[i].lower, state[i].checksum, levels);
}

static void clear_results(void)
{
  for (unsigned i = 0; i < NANO_LOOKUP_WORKERS; ++i) {
    results[i].lower_bound = 0;
    results[i].checksum = 0;
    results[i].steps = 0;
    results[i].done = 0;
  }
}

static void destroy_coroutines(void)
{
  for (unsigned i = 0; i < NANO_LOOKUP_WORKERS; ++i) cpp_tasks[i].destroy();
  cpp_scheduler.reset();
  lean_scheduler.reset();
  cpp_frame_next = 0;
}

/* Seed identical context state for every mode. Serial and batch modes do not
 * launch the parked contexts, but still pay the same untimed setup. */
static void prepare(const volatile struct index_line *const *tables, uint64_t entries,
                    const uint64_t *queries, unsigned mode, uint64_t levels)
{
  destroy_coroutines();
  clear_results();
  for (unsigned i = 1; i < active_workers; ++i) {
    uint64_t gp_value;
    __asm__ volatile("mv %0, gp" : "=r"(gp_value));
    seed_reg(i, 3, gp_value);
    seed_reg(i, 2, (uint64_t)&stacks[i][STACK_WORDS]);
    seed_reg(i, 10, (uint64_t)tables[i]);
    seed_reg(i, 11, entries);
    seed_reg(i, 12, queries[i]);
    seed_reg(i, 13, (uint64_t)&results[i]);
    seed_reg(i, 14, mode);
    seed_reg(i, 15, (i + 1) % active_workers);
    seed_reg(i, 16, 1);
    seed_reg(i, 17, levels);
    seed_npc(i, (uint64_t)lookup_worker);
    __asm__ volatile("fence rw, rw" ::: "memory");
  }
  if (mode == MODE_CPP_COROUTINE || mode == MODE_LEAN_COROUTINE
      || mode == MODE_DIRECT_COROUTINE) {
    for (unsigned i = 0; i < active_workers; ++i) {
      unsigned next = (i + 1) % active_workers;
      if (mode == MODE_CPP_COROUTINE)
        cpp_tasks[i] = coroutine_lookup<MODE_CPP_COROUTINE>(
          tables[i], entries, queries[i], &results[i], next, levels);
      else if (mode == MODE_LEAN_COROUTINE)
        cpp_tasks[i] = coroutine_lookup<MODE_LEAN_COROUTINE>(
          tables[i], entries, queries[i], &results[i], next, levels);
      else
        cpp_tasks[i] = coroutine_lookup<MODE_DIRECT_COROUTINE>(
          tables[i], entries, queries[i], &results[i], next, levels);
      if (mode == MODE_LEAN_COROUTINE)
        lean_scheduler.push(cpp_tasks[i].handle);
      else if (mode == MODE_CPP_COROUTINE)
        cpp_scheduler.push(cpp_tasks[i].handle);
    }
  }
}

template <unsigned Mode>
static __attribute__((noinline)) void ring_operation(
  const volatile struct index_line *const *tables, uint64_t entries,
  const uint64_t *queries, uint64_t levels)
{
  lookup_worker(tables[0], entries, queries[0], &results[0], Mode,
                active_workers > 1 ? 1 : 0, 0, levels);
}

template <unsigned Prefetch>
static __attribute__((noinline)) void serial_operation(
  const volatile struct index_line *const *tables, uint64_t entries,
  const uint64_t *queries, uint64_t)
{
  serial_lookup(tables, entries, queries, Prefetch);
}

static __attribute__((noinline)) void matched_batch_operation(
  const volatile struct index_line *const *tables, uint64_t entries,
  const uint64_t *queries, uint64_t levels)
{
  matched_batch(tables, entries, queries, levels);
}

static __attribute__((noinline)) void checked_coroutine_operation(
  const volatile struct index_line *const *, uint64_t, const uint64_t *, uint64_t)
{
  cpp_scheduler.run();
}

static __attribute__((noinline)) void lean_coroutine_operation(
  const volatile struct index_line *const *, uint64_t, const uint64_t *, uint64_t)
{
  lean_scheduler.run();
}

static __attribute__((noinline)) void direct_coroutine_operation(
  const volatile struct index_line *const *, uint64_t, const uint64_t *, uint64_t)
{
  // Resuming frame zero transfers directly around the ring until it reaches
  // final suspend. The remaining frames then need one terminal resume each;
  // no checked FIFO or modulo operation is required for this fixed schedule.
  for (unsigned i = 0; i < active_workers; ++i) cpp_tasks[i].handle.resume();
}

using operation_fn = void (*)(const volatile struct index_line *const *,
                              uint64_t, const uint64_t *, uint64_t);

#define SELECT_FIXED_BATCH(function) \
  switch (active_workers) { \
    case 2: return function<2>; \
    case 3: return function<3>; \
    case 4: return function<4>; \
    case 5: return function<5>; \
    case 6: return function<6>; \
    case 7: return function<7>; \
    case 8: return function<8>; \
    case 9: return function<9>; \
    case 10: return function<10>; \
  }

static operation_fn select_operation(unsigned mode)
{
  switch (mode) {
    case MODE_SERIAL_DEMAND: return serial_operation<0>;
    case MODE_DEMAND_RING: return ring_operation<MODE_DEMAND_RING>;
    case MODE_WORKER_PREFETCH: return ring_operation<MODE_WORKER_PREFETCH>;
    case MODE_MATCHED_BATCH: return matched_batch_operation;
    case MODE_SWITCH_ONLY: return ring_operation<MODE_SWITCH_ONLY>;
    case MODE_SERIAL_PREFETCH: return serial_operation<1>;
    case MODE_CPP_COROUTINE: return checked_coroutine_operation;
    case MODE_FIXED_SOA_BATCH: SELECT_FIXED_BATCH(fixed_soa_batch); break;
    case MODE_FIXED_RECOMPUTE_BATCH:
      SELECT_FIXED_BATCH(fixed_recompute_batch);
      break;
    case MODE_LEAN_COROUTINE: return lean_coroutine_operation;
    case MODE_DIRECT_COROUTINE: return direct_coroutine_operation;
  }
  return nullptr;
}

static void expected_result(uint64_t entries, uint64_t key,
                            uint64_t *expected_lower,
                            uint64_t *expected_checksum,
                            uint64_t *expected_steps)
{
  uint64_t lower = 0, length = entries, checksum = 0, steps = 0;
  while (length) {
    uint64_t half = length >> 1;
    uint64_t middle = lower + half;
    uint64_t value = middle * 2;
    checksum += value;
    ++steps;
    if (value < key) {
      lower = middle + 1;
      length -= half + 1;
    } else {
      length = half;
    }
  }
  *expected_lower = lower;
  *expected_checksum = checksum;
  *expected_steps = steps;
}

static void check_results(unsigned mode, uint64_t entries,
                          const uint64_t *queries, uint64_t levels)
{
  for (unsigned i = 0; i < active_workers; ++i) {
    uint64_t lower = 0, checksum = 0, steps = levels;
    if (mode != MODE_SWITCH_ONLY)
      expected_result(entries, queries[i], &lower, &checksum, &steps);
    if (results[i].lower_bound != lower || results[i].checksum != checksum
        || results[i].steps != steps || results[i].done != 1) {
      bp_print_string("[BSG-FAIL] nano lookup result mismatch; worker=");
      bp_hprint_uint64(i);
      bp_print_string(" lower="); bp_hprint_uint64(results[i].lower_bound);
      bp_print_string(" checksum="); bp_hprint_uint64(results[i].checksum);
      bp_print_string(" steps="); bp_hprint_uint64(results[i].steps);
      bp_print_string(" done="); bp_hprint_uint64(results[i].done);
      bp_print_string("\n");
      bp_finish(1);
    }
  }
}

static inline uint64_t read_global_cycle(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
  return value;
}

#ifdef NANO_DIAGNOSTIC_INSTRET
static uint64_t diagnostic_instret;
static inline uint64_t read_instret(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xb02" : "=r"(value) : : "memory");
  return value;
}
#endif

static void emit_marker(unsigned id)
{
  *SIGNAL_BASE_ADDR = id;
  __asm__ volatile("fence ow, ow" ::: "memory");
}

extern "C" __attribute__((noinline, noclone, aligned(64))) uint64_t run_window(
  operation_fn operation, const volatile struct index_line *const *tables,
  uint64_t entries,
  const uint64_t *queries, uint64_t levels,
  unsigned begin_marker, unsigned end_marker)
{
  emit_marker(begin_marker);
  uint64_t begin = read_global_cycle();
#ifdef NANO_DIAGNOSTIC_INSTRET
  uint64_t instret_begin = read_instret();
#endif
  operation(tables, entries, queries, levels);
#ifdef NANO_DIAGNOSTIC_INSTRET
  diagnostic_instret = read_instret() - instret_begin;
#endif
  uint64_t end = read_global_cycle();
  emit_marker(end_marker);
  return end - begin;
}

static void drain_traffic(void)
{
  __asm__ volatile("fence rw, rw" ::: "memory");
}

static void initialize_table_pointers(void)
{
  for (uint64_t worker = 0; worker < NANO_LOOKUP_WORKERS; ++worker) {
    measured_tables[worker] = nano_measured_indexes[worker];
    warm_tables[worker] = nano_warm_indexes[worker];
  }
  drain_traffic();
}

/* Run every body in one fixed order on distinct, already-small data, then
 * finish with switch-only. Every measured mode therefore starts with the same
 * instruction/data-cache history, predictor history, and frontend state while
 * the measured nodes remain untouched. */
static void warm_instruction_paths(void)
{
  for (unsigned mode = 0; mode < MODE_COUNT; ++mode) {
    prepare(warm_tables, NANO_LOOKUP_WARM_ENTRIES,
            nano_warm_queries, mode, NANO_LOOKUP_WARM_LEVELS);
    drain_traffic();
    run_window(select_operation(mode), warm_tables, NANO_LOOKUP_WARM_ENTRIES,
               nano_warm_queries, NANO_LOOKUP_WARM_LEVELS,
               0x90 + mode, 0x80 + mode);
    drain_traffic();
    destroy_coroutines();
    check_results(mode, NANO_LOOKUP_WARM_ENTRIES, nano_warm_queries,
                  NANO_LOOKUP_WARM_LEVELS);
  }
  prepare(warm_tables, NANO_LOOKUP_WARM_ENTRIES,
          nano_warm_queries, MODE_SWITCH_ONLY, NANO_LOOKUP_WARM_LEVELS);
  drain_traffic();
  run_window(select_operation(MODE_SWITCH_ONLY), warm_tables,
             NANO_LOOKUP_WARM_ENTRIES,
             nano_warm_queries, NANO_LOOKUP_WARM_LEVELS, 0xaf, 0xbf);
  drain_traffic();
  check_results(MODE_SWITCH_ONLY, NANO_LOOKUP_WARM_ENTRIES,
                nano_warm_queries, NANO_LOOKUP_WARM_LEVELS);
}

static const char *mode_name(unsigned mode)
{
  static const char *const names[MODE_COUNT] = {
    "serial demand", "demand ring", "worker prefetch",
    "matched batch", "switch-only", "serial prefetch", "C++20 coroutines",
    "fixed unrolled SoA batch", "fixed unrolled recompute batch",
    "lean queue C++20 coroutines", "direct C++20 coroutines"
  };
  return names[mode];
}

int main(void)
{
  uint64_t config = benchmark_mode;
  unsigned mode = config & 0xff;
  active_workers = (config >> 8) & 0xff;
  if (!active_workers) active_workers = NANO_LOOKUP_WORKERS;
  if (mode >= MODE_COUNT || active_workers < 2
      || active_workers > NANO_LOOKUP_WORKERS) {
    bp_print_string((char *)"[BSG-FAIL] nano lookup mode/workers invalid\n");
    bp_finish(1);
  }

  initialize_table_pointers();
  emit_marker(0x8f);
  warm_instruction_paths();
#ifdef NANO_PREWARM_MEASURED
  // Diagnostic only: make the measured paths resident without changing the
  // selected timed body, then repeat the ordinary preparation contract.
  prepare(measured_tables, NANO_LOOKUP_MEASURED_ENTRIES,
          nano_measured_queries, MODE_SERIAL_DEMAND,
          NANO_LOOKUP_MEASURED_LEVELS);
  serial_lookup(measured_tables, NANO_LOOKUP_MEASURED_ENTRIES,
                nano_measured_queries, 0);
  drain_traffic();
  check_results(MODE_SERIAL_DEMAND, NANO_LOOKUP_MEASURED_ENTRIES,
                nano_measured_queries, NANO_LOOKUP_MEASURED_LEVELS);
#endif
  prepare(measured_tables, NANO_LOOKUP_MEASURED_ENTRIES,
          nano_measured_queries, mode, NANO_LOOKUP_MEASURED_LEVELS);
  operation_fn operation = select_operation(mode);
  drain_traffic();

  uint64_t cycles = run_window(
    operation, measured_tables, NANO_LOOKUP_MEASURED_ENTRIES,
    nano_measured_queries, NANO_LOOKUP_MEASURED_LEVELS,
    BEGIN_MARKER_BASE + mode, END_MARKER_BASE + mode);

  destroy_coroutines();
  check_results(mode, NANO_LOOKUP_MEASURED_ENTRIES,
                nano_measured_queries, NANO_LOOKUP_MEASURED_LEVELS);
  uint64_t checksum = 0;
  for (unsigned i = 0; i < active_workers; ++i)
    checksum += results[i].checksum;

  bp_print_string("Benchmark: NANO_LOOKUP mode="); bp_hprint_uint64(mode);
  bp_print_string(" queries="); bp_hprint_uint64(active_workers);
  bp_print_string(" levels="); bp_hprint_uint64(NANO_LOOKUP_MEASURED_LEVELS);
  bp_print_string(" cycles="); bp_hprint_uint64(cycles);
  bp_print_string(" checksum="); bp_hprint_uint64(checksum);
#ifdef NANO_DIAGNOSTIC_INSTRET
  bp_print_string(" instret="); bp_hprint_uint64(diagnostic_instret);
#endif
  bp_print_string("\nMode: "); bp_print_string((char *)mode_name(mode));
  bp_print_string("; checks: pass\n");
  bp_print_string("[BSG-PASS] Nano-style binary index lookups\n");
  bp_finish(0);
  return 0;
}
