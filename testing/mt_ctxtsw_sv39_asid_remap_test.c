/**
 * mt_ctxtsw_sv39_asid_remap_test.c
 *
 * Banyan-parity dTLB/ASID remap test. It keeps control flow in M-mode, but
 * uses mstatus.MPRV with MPP=S for the actual data access. That makes the
 * load/store use the active context's SATP translation without depending on
 * S-mode instruction fetch/trap setup.
 *
 * T0 and T1 map the same virtual address to different physical pages using
 * different ASIDs. After switching both ways, each context must still see its
 * own backing page through the shared virtual address.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512
#define PAGE_WORDS  512

#define TEST_VA 0x0000000040000000ULL

#define SV39_PTE_V 0x001ULL
#define SV39_PTE_R 0x002ULL
#define SV39_PTE_W 0x004ULL
#define SV39_PTE_A 0x040ULL
#define SV39_PTE_D 0x080ULL

#define SV39_SATP_MODE (8ULL << 60)
#define SATP_ASID_SHIFT 44
#define SATP_ASID_MASK  0xFFFFULL
#define MSTATUS_MPP_MASK 0x1800ULL
#define MSTATUS_MPP_S    0x0800ULL
#define MSTATUS_MPRV     0x20000ULL

#define T0_INITIAL 0x1111222233334444ULL
#define T0_UPDATED 0xaaaabbbbccccddddULL
#define T1_INITIAL 0x5555666677778888ULL
#define T1_UPDATED 0x9999aaaabbbbccccULL

static uint64_t t1_stack[STACK_WORDS] __attribute__((aligned(16)));

static uint64_t root0[PAGE_WORDS] __attribute__((aligned(4096)));
static uint64_t l1_0[PAGE_WORDS] __attribute__((aligned(4096)));
static uint64_t l0_0[PAGE_WORDS] __attribute__((aligned(4096)));
static uint64_t root1[PAGE_WORDS] __attribute__((aligned(4096)));
static uint64_t l1_1[PAGE_WORDS] __attribute__((aligned(4096)));
static uint64_t l0_1[PAGE_WORDS] __attribute__((aligned(4096)));

static uint64_t t0_page[PAGE_WORDS] __attribute__((aligned(4096)));
static uint64_t t1_page[PAGE_WORDS] __attribute__((aligned(4096)));

static volatile uint64_t t1_initial_read = 0;
static volatile uint64_t t1_resume_read = 0;
static volatile uint64_t t1_satp_after_write = 0;

static inline void write_ctxt(uint64_t v) {
  __asm__ volatile("csrw 0x081, %0" : : "r"(v) : "memory");
}

static inline uint64_t read_satp(void) {
  uint64_t v;
  __asm__ volatile("csrr %0, satp" : "=r"(v));
  return v;
}

static inline void write_satp(uint64_t v) {
  __asm__ volatile("csrw satp, %0" : : "r"(v) : "memory");
}

static inline void sfence_vma(void) {
  __asm__ volatile("sfence.vma x0, x0" : : : "memory");
}

static inline uint64_t pte_table(void *page) {
  return (((uint64_t)page >> 12) << 10) | SV39_PTE_V;
}

static inline uint64_t pte_leaf(void *page) {
  return (((uint64_t)page >> 12) << 10) | SV39_PTE_V | SV39_PTE_R | SV39_PTE_W | SV39_PTE_A | SV39_PTE_D;
}

static inline uint64_t satp_sv39(uint64_t asid, void *root) {
  return SV39_SATP_MODE | ((asid & SATP_ASID_MASK) << SATP_ASID_SHIFT) | ((uint64_t)root >> 12);
}

static void map_one_page(uint64_t *root, uint64_t *l1, uint64_t *l0, void *phys_page) {
  uint64_t vpn2 = (TEST_VA >> 30) & 0x1ffULL;
  uint64_t vpn1 = (TEST_VA >> 21) & 0x1ffULL;
  uint64_t vpn0 = (TEST_VA >> 12) & 0x1ffULL;

  for (uint64_t i = 0; i < PAGE_WORDS; i++) {
    root[i] = 0;
    l1[i] = 0;
    l0[i] = 0;
  }

  root[vpn2] = pte_table(l1);
  l1[vpn1] = pte_table(l0);
  l0[vpn0] = pte_leaf(phys_page);
}

static inline uint64_t mprv_s_load64(uint64_t va) {
  uint64_t old_status;
  uint64_t new_status;
  uint64_t value;

  __asm__ volatile(
      "csrr %0, mstatus\n"
      "li %1, %3\n"
      "not %1, %1\n"
      "and %1, %0, %1\n"
      "or %1, %1, %4\n"
      "csrw mstatus, %1\n"
      "ld %2, 0(%5)\n"
      "csrw mstatus, %0\n"
      : "=&r"(old_status), "=&r"(new_status), "=&r"(value)
      : "i"(MSTATUS_MPP_MASK), "r"(MSTATUS_MPP_S | MSTATUS_MPRV), "r"(va)
      : "memory");

  return value;
}

static inline void mprv_s_store64(uint64_t va, uint64_t value) {
  uint64_t old_status;
  uint64_t new_status;

  __asm__ volatile(
      "csrr %0, mstatus\n"
      "li %1, %2\n"
      "not %1, %1\n"
      "and %1, %0, %1\n"
      "or %1, %1, %3\n"
      "csrw mstatus, %1\n"
      "sd %4, 0(%5)\n"
      "csrw mstatus, %0\n"
      : "=&r"(old_status), "=&r"(new_status)
      : "i"(MSTATUS_MPP_MASK), "r"(MSTATUS_MPP_S | MSTATUS_MPRV), "r"(value), "r"(va)
      : "memory");
}

void __attribute__((noinline, noreturn)) t1_entry(void) {
  write_satp(satp_sv39(0x22, root1));
  sfence_vma();
  t1_satp_after_write = read_satp();

  t1_initial_read = mprv_s_load64(TEST_VA);
  mprv_s_store64(TEST_VA, T1_UPDATED);
  write_ctxt(0);

  t1_resume_read = mprv_s_load64(TEST_VA);
  write_ctxt(0);

  while (1) { }
}

int main(void) {
  bp_print_string("=== Ctxtsw SV39 ASID Remap Test ===\n");

  int errors = 0;
  t0_page[0] = T0_INITIAL;
  t1_page[0] = T1_INITIAL;

  map_one_page(root0, l1_0, l0_0, t0_page);
  map_one_page(root1, l1_1, l0_1, t1_page);

  write_satp(satp_sv39(0x11, root0));
  sfence_vma();

  uint64_t t0_initial_read = mprv_s_load64(TEST_VA);
  mprv_s_store64(TEST_VA, T0_UPDATED);

  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_entry);
  write_ctxt(1);

  uint64_t t0_after_t1_read = mprv_s_load64(TEST_VA);
  write_ctxt(1);

  bp_print_string("T0 initial VA read: ");
  bp_hprint_uint64(t0_initial_read);
  bp_print_string("\nT0 after T1 VA read: ");
  bp_hprint_uint64(t0_after_t1_read);
  bp_print_string("\nT1 initial VA read: ");
  bp_hprint_uint64(t1_initial_read);
  bp_print_string("\nT1 resume VA read: ");
  bp_hprint_uint64(t1_resume_read);
  bp_print_string("\nT1 SATP after write: ");
  bp_hprint_uint64(t1_satp_after_write);
  bp_print_string("\n");

  if (t0_initial_read != T0_INITIAL) {
    bp_print_string("FAIL: T0 translated VA did not read T0 page\n");
    errors++;
  }
  if (t0_after_t1_read != T0_UPDATED) {
    bp_print_string("FAIL: T0 translated VA changed after T1 mapping\n");
    errors++;
  }
  if (t1_initial_read != T1_INITIAL) {
    bp_print_string("FAIL: T1 translated VA did not read T1 page\n");
    errors++;
  }
  if (t1_resume_read != T1_UPDATED) {
    bp_print_string("FAIL: T1 translated VA changed after resume\n");
    errors++;
  }
  if ((t0_page[0] != T0_UPDATED) || (t1_page[0] != T1_UPDATED)) {
    bp_print_string("FAIL: physical backing pages do not match translated stores\n");
    errors++;
  }

  if (errors == 0) {
    bp_print_string("[BSG-PASS] SV39 ASID remap verified\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] SV39 ASID remap failed\n");
    bp_finish(1);
  }

  return 0;
}
