/* Exercise ten independent nonfaulting hints before their matching loads.
 * Correctness checks every demand value; waveform evidence establishes how
 * many UCE reservations coexist before any hint response completes.
 */
#include <stdint.h>
#include "bp_prefetch.h"
#include "bp_utils.h"

#define HINTS 10

struct cache_line {
  uint64_t value;
  uint64_t padding[7];
};

#define LINE(n) { (n), {0} }
static const volatile struct cache_line warm_data[HINTS]
  __attribute__((aligned(4096), used)) = {
    LINE(1), LINE(2), LINE(3), LINE(4), LINE(5),
    LINE(6), LINE(7), LINE(8), LINE(9), LINE(10)
  };
static const volatile struct cache_line depth_data[HINTS]
  __attribute__((aligned(4096), used)) = {
    LINE(11), LINE(12), LINE(13), LINE(14), LINE(15),
    LINE(16), LINE(17), LINE(18), LINE(19), LINE(20)
  };

static __attribute__((noinline))
uint64_t hint_then_load(const volatile struct cache_line *lines)
{
  for (unsigned i = 0; i < HINTS; i++)
    bp_prefetch_r(&lines[i].value);

  uint64_t sum = 0;
  for (unsigned i = 0; i < HINTS; i++)
    sum += lines[i].value;
  return sum;
}

int main(void)
{
  if (hint_then_load(warm_data) != 55)
    bp_finish(1);
  if (hint_then_load(depth_data) != 155)
    bp_finish(1);

  bp_print_string("[BSG-PASS] ten queued prefetch hints\n");
  bp_finish(0);
  return 0;
}
