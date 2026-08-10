/**
 * mt_context_cache_l1_service_test.c
 *
 * Exercises the backend context-cache L1 D$ service path through CSR 0x084
 * (data/result) and CSR 0x085 (command/status). This is a hardware-originated
 * doubleword load/store path into the normal L1 D-cache, independent of the
 * software load/store instructions used to verify the result.
 */

#include <stdint.h>

#include "bp_utils.h"

#define CTX_L1_DATA_CSR 0x084
#define CTX_L1_CMD_CSR  0x085
#define CTX_L1_CMD_STORE_BIT (1ULL << 63)
#define CTX_L1_READY_BIT 1ULL

static volatile uint64_t service_words[8] __attribute__((aligned(64)));

static inline void csr_write_084(uint64_t value) {
  __asm__ volatile("csrw 0x084, %0" : : "r"(value) : "memory");
}

static inline void csr_write_085(uint64_t value) {
  __asm__ volatile("csrw 0x085, %0" : : "r"(value) : "memory");
}

static inline uint64_t csr_read_084(void) {
  uint64_t value;
  __asm__ volatile("csrr %0, 0x084" : "=r"(value) :: "memory");
  return value;
}

static inline uint64_t csr_read_085(void) {
  uint64_t value;
  __asm__ volatile("csrr %0, 0x085" : "=r"(value) :: "memory");
  return value;
}

static void wait_ready(void) {
  for (uint64_t i = 0; i < 100000; i++) {
    if (csr_read_085() & CTX_L1_READY_BIT)
      return;
  }

  bp_print_string("[BSG-FAIL] context-cache L1 service timeout\n");
  bp_finish(1);
}

int main(void) {
  const uint64_t store_value = 0x123456789abcdef0ULL;
  const uint64_t load_value = 0x0fedcba987654321ULL;

  service_words[0] = 0;
  service_words[1] = load_value;
  __asm__ volatile("fence" ::: "memory");

  wait_ready();
  csr_write_084(store_value);
  csr_write_085(CTX_L1_CMD_STORE_BIT | (uintptr_t)&service_words[0]);
  wait_ready();
  __asm__ volatile("fence" ::: "memory");

  if (service_words[0] != store_value) {
    bp_print_string("[BSG-FAIL] context-cache L1 service store got=");
    bp_hprint_uint64(service_words[0]);
    bp_print_string(" expected=");
    bp_hprint_uint64(store_value);
    bp_print_string("\n");
    bp_finish(1);
  }

  wait_ready();
  csr_write_085((uintptr_t)&service_words[1]);
  wait_ready();

  uint64_t got = csr_read_084();
  if (got != load_value) {
    bp_print_string("[BSG-FAIL] context-cache L1 service load got=");
    bp_hprint_uint64(got);
    bp_print_string(" expected=");
    bp_hprint_uint64(load_value);
    bp_print_string("\n");
    bp_finish(1);
  }

  bp_print_string("[BSG-PASS] context-cache L1 service load/store verified\n");
  bp_finish(0);
  return 0;
}
