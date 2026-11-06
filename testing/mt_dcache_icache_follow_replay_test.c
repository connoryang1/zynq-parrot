/* Validate integrated instruction-then-data replay from one tagged command.
 * A trigger with bit two set must replay the shared I-cache prefix, wait for
 * its detached responses to retire, and then start the configured D-cache
 * footprint without a second architectural CSR write.
 */
#include <stdint.h>
#include "bp_utils.h"

#define REPLAY_SLOT 1
#define FOLLOW_INSTRUCTION_PREFIX 4

struct cache_line { uint64_t value, padding[7]; };

static volatile struct cache_line data_target
  __attribute__((aligned(64), used)) = {.value = 0x123456789abcdef0ULL};

#define REPLAY_TARGET(name, delta)                                      \
  static uint64_t __attribute__((naked, noinline, aligned(64), used))    \
  name(uint64_t value)                                                   \
  {                                                                      \
    __asm__ volatile("addi a0, a0, " #delta "\nret\n");                 \
  }

REPLAY_TARGET(instruction_target_a, 17)
REPLAY_TARGET(instruction_target_b, 29)

static inline void prefix_set(unsigned index, const void *paddr)
{
  uint64_t payload = ((uint64_t)index << 56) | (uintptr_t)paddr;
  __asm__ volatile("csrw 0x7c1, %0" : : "r"(payload) : "memory");
}

static inline uint64_t prefix_status(void)
{
  uint64_t status;
  __asm__ volatile("csrr %0, 0x7c2" : "=r"(status));
  return status;
}

static inline void data_entry_set(unsigned index, const void *paddr)
{
  uint64_t payload = ((uint64_t)REPLAY_SLOT << 45)
                     | ((uint64_t)index << 40)
                     | ((uintptr_t)paddr & ((1ULL << 40) - 1));
  __asm__ volatile("csrw 0x9c1, %0" : : "r"(payload) : "memory");
}

static inline uint64_t data_status(void)
{
  uint64_t status;
  __asm__ volatile("csrr %0, 0x9c3" : "=r"(status));
  return status;
}

static void fail(const char *message, uint64_t data, uint64_t instruction)
{
  bp_print_string("[BSG-FAIL] instruction-followed-by-data replay: ");
  bp_print_string(message);
  bp_print_string(" data/instruction-status=");
  bp_hprint_uint64(data);
  bp_hprint_uint64(instruction);
  bp_print_string("\n");
  bp_finish(1);
  for (;;) ;
}

int main(void)
{
  prefix_set(0, instruction_target_a);
  prefix_set(1, instruction_target_b);
  __asm__ volatile("csrw 0x7c2, %0" : : "r"(2UL | (1ULL << 63))
                    : "memory");

  data_entry_set(0, (const void *)&data_target);
  uint64_t config = REPLAY_SLOT | (1ULL << 2) | (1ULL << 63);
  __asm__ volatile("csrw 0x9c2, %0" : : "r"(config) : "memory");

  /* Bit two requests the hardware follow. No architectural 0x5c0 trigger is
   * issued anywhere in this test. */
  __asm__ volatile("csrw 0x9c3, %0"
                    : : "r"((uint64_t)(REPLAY_SLOT
                                       | FOLLOW_INSTRUCTION_PREFIX))
                    : "memory");

  uint64_t dstatus = 0, istatus = 0;
  unsigned timeout = 100000;
  do {
    dstatus = data_status();
    istatus = prefix_status();
    if (!--timeout)
      fail("timeout", dstatus, istatus);
  } while ((dstatus & 1) || ((dstatus >> 1) & 3)
           || ((dstatus >> 60) & 0xf) || (istatus & (1ULL << 1))
           || (((istatus >> 38) & 0xff) == 0));

  if (((dstatus >> 10) & 0xffff) != 1
      || ((dstatus >> 26) & 0xffff) != 0
      || ((dstatus >> 42) & 0xff) != 1
      || ((dstatus >> 50) & 0xff) != 0
      || ((istatus >> 22) & 0xffff) != 2
      || ((istatus >> 38) & 0xff) != 1
      || ((istatus >> 46) & 0xff) != 0)
    fail("counter mismatch", dstatus, istatus);

  if (data_target.value != 0x123456789abcdef0ULL
      || instruction_target_a(100) != 117
      || instruction_target_b(100) != 129)
    fail("replayed contents corrupted", dstatus, istatus);

  bp_print_string("[BSG-PASS] hardware-sequenced instruction then data replay\n");
  bp_finish(0);
  return 0;
}
