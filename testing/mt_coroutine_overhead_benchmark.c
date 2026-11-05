/* Isolate hot C++20 coroutine mechanics from memory latency and hardware
 * context switching. Frames are constructed before each timed window.
 */
#include <coroutine>
#include <stddef.h>
#include <stdint.h>
#include "bp_utils.h"

#define OPERATIONS 8192
#define WARM_OPERATIONS 128
#define RING_TASKS 8
#define FRAME_BYTES 256
#define SIGNAL_BASE_ADDR ((volatile uint8_t *)0x00104000)

enum mode {
  MODE_INLINE = 0,
  MODE_MANUAL = 1,
  MODE_SINGLE_COROUTINE = 2,
  MODE_DIRECT_RING = 3,
  MODE_COUNT
};

static volatile uint64_t outputs[MODE_COUNT];
static volatile uint64_t ring_outputs[RING_TASKS];

static inline uint64_t payload(uint64_t value)
{
  __asm__ volatile("" : "+r"(value));
  return value + 1;
}

struct manual_counter {
  uint64_t remaining;
  uint64_t value;
};

static __attribute__((noinline)) bool manual_resume(manual_counter *counter)
{
  counter->value = payload(counter->value);
  return --counter->remaining == 0;
}

alignas(16) static uint8_t frame_storage[RING_TASKS][FRAME_BYTES];
static unsigned frame_next;

struct hot_task {
  struct promise_type;
  using handle_type = std::coroutine_handle<promise_type>;

  struct promise_type {
    static void *operator new(size_t size)
    {
      if (size > FRAME_BYTES || frame_next >= RING_TASKS) {
        bp_print_string("[BSG-FAIL] coroutine overhead frame pool exhausted\n");
        bp_finish(1);
      }
      return frame_storage[frame_next++];
    }
    static void operator delete(void *, size_t) noexcept {}
    hot_task get_return_object()
    {
      return hot_task{handle_type::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    void return_void() noexcept {}
    void unhandled_exception() noexcept
    {
      bp_print_string("[BSG-FAIL] coroutine overhead exception\n");
      bp_finish(1);
    }
  };

  handle_type handle = nullptr;
  hot_task() = default;
  explicit hot_task(handle_type value) : handle(value) {}
  hot_task(const hot_task &) = delete;
  hot_task &operator=(const hot_task &) = delete;
  hot_task(hot_task &&other) noexcept : handle(other.handle)
  {
    other.handle = nullptr;
  }
  hot_task &operator=(hot_task &&other) noexcept
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

static hot_task tasks[RING_TASKS];

struct transfer_next {
  unsigned next;
  bool await_ready() const noexcept { return false; }
  void await_resume() const noexcept {}
  std::coroutine_handle<> await_suspend(std::coroutine_handle<>) const noexcept
  {
    return tasks[next].handle;
  }
};

template <bool Ring>
static hot_task counter(uint64_t operations, uint64_t seed,
                        volatile uint64_t *output, unsigned next)
{
  uint64_t value = seed;
  for (uint64_t i = 0; i < operations; ++i) {
    value = payload(value);
    if (i + 1 != operations) {
      if constexpr (Ring)
        co_await transfer_next{next};
      else
        co_await std::suspend_always{};
    }
  }
  *output = value;
}

static void destroy_tasks(void)
{
  for (unsigned i = 0; i < RING_TASKS; ++i) tasks[i].destroy();
  frame_next = 0;
}

static uint64_t active_operations;

static __attribute__((noinline)) void inline_operation(void)
{
  uint64_t value = 1;
  for (uint64_t i = 0; i < active_operations; ++i) value = payload(value);
  outputs[MODE_INLINE] = value;
}

static __attribute__((noinline)) void manual_operation(void)
{
  manual_counter state{active_operations, 1};
  while (!manual_resume(&state)) {}
  outputs[MODE_MANUAL] = state.value;
}

static void prepare_single(void)
{
  destroy_tasks();
  tasks[0] = counter<false>(active_operations, 1,
                            &outputs[MODE_SINGLE_COROUTINE], 0);
}

static __attribute__((noinline)) void single_coroutine_operation(void)
{
  while (!tasks[0].handle.done()) tasks[0].handle.resume();
}

static void prepare_ring(void)
{
  destroy_tasks();
  const uint64_t per_task = active_operations / RING_TASKS;
  for (unsigned i = 0; i < RING_TASKS; ++i) {
    ring_outputs[i] = 0;
    tasks[i] = counter<true>(per_task, i + 1, &ring_outputs[i],
                             (i + 1) % RING_TASKS);
  }
}

static __attribute__((noinline)) void direct_ring_operation(void)
{
  uint64_t sum = 0;
  for (unsigned i = 0; i < RING_TASKS; ++i) {
    while (!tasks[i].handle.done()) tasks[i].handle.resume();
    sum += ring_outputs[i];
  }
  outputs[MODE_DIRECT_RING] = sum;
}

using operation_fn = void (*)(void);

static inline uint64_t read_global_cycle(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
  return value;
}

static void emit_marker(unsigned id)
{
  *SIGNAL_BASE_ADDR = id;
  __asm__ volatile("fence ow, ow" ::: "memory");
}

static uint64_t run_window(operation_fn operation, unsigned mode)
{
  emit_marker(0x40 + mode);
  uint64_t begin = read_global_cycle();
  operation();
  uint64_t end = read_global_cycle();
  emit_marker(0x50 + mode);
  return end - begin;
}

static operation_fn operation(unsigned mode)
{
  static const operation_fn operations[MODE_COUNT] = {
    inline_operation, manual_operation, single_coroutine_operation,
    direct_ring_operation
  };
  return operations[mode];
}

static void prepare(unsigned mode)
{
  if (mode == MODE_SINGLE_COROUTINE) prepare_single();
  else if (mode == MODE_DIRECT_RING) prepare_ring();
}

static uint64_t expected(unsigned mode, uint64_t operations)
{
  if (mode != MODE_DIRECT_RING) return operations + 1;
  return operations + RING_TASKS * (RING_TASKS + 1) / 2;
}

int main(void)
{
  static const char *const names[MODE_COUNT] = {
    "inline payload", "manual noinline resume", "single coroutine",
    "eight-frame direct ring"
  };
  uint64_t cycles[MODE_COUNT];

  for (unsigned mode = 0; mode < MODE_COUNT; ++mode) {
    active_operations = WARM_OPERATIONS;
    prepare(mode);
    operation(mode)();
    if (outputs[mode] != expected(mode, WARM_OPERATIONS)) {
      bp_print_string("[BSG-FAIL] coroutine overhead warmup mismatch\n");
      bp_finish(1);
    }
    destroy_tasks();

    active_operations = OPERATIONS;
    outputs[mode] = 0;
    prepare(mode);
    __asm__ volatile("fence rw, rw" ::: "memory");
    cycles[mode] = run_window(operation(mode), mode);
    __asm__ volatile("fence rw, rw" ::: "memory");
    if (outputs[mode] != expected(mode, OPERATIONS)) {
      bp_print_string("[BSG-FAIL] coroutine overhead result mismatch\n");
      bp_finish(1);
    }
    destroy_tasks();
  }

  bp_print_string("Benchmark: hot C++20 coroutine overhead; operations=");
  bp_hprint_uint64(OPERATIONS);
  bp_print_string(" ring_tasks="); bp_hprint_uint64(RING_TASKS);
  bp_print_string("\n");
  for (unsigned mode = 0; mode < MODE_COUNT; ++mode) {
    bp_print_string((char *)names[mode]);
    bp_print_string(" cycles: "); bp_hprint_uint64(cycles[mode]);
    bp_print_string("\n");
  }
  bp_print_string("[BSG-PASS] hot coroutine overhead benchmark completed\n");
  bp_finish(0);
  return 0;
}
