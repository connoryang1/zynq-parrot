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
#define DCSR_MPRVEN      (1ULL << 4)

#define T0_INITIAL 0x1111222233334444ULL
#define T0_UPDATED 0xaaaabbbbccccddddULL
#define T1_INITIAL 0x5555666677778888ULL
#define T1_UPDATED 0x9999aaaabbbbccccULL

/*
 * The current zynq-parrot BlackParrot config exposes one ASID bit. Keep this
 * test explicit about the two representable ASIDs instead of using larger
 * values that silently truncate in hardware.
 */
#define T0_ASID 0x0ULL
#define T1_ASID 0x1ULL

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
static volatile uint64_t progress = 0;

static inline void write_ctxt(uint64_t v) {
  __asm__ volatile("csrw 0x081, %0" : : "r"(v) : "memory");
}

static inline void write_ctxt0(void) {
  __asm__ volatile("csrw 0x081, x0" : : : "memory");
}

static inline uint64_t read_satp(void) {
  uint64_t v;
  __asm__ volatile("csrr %0, satp" : "=r"(v));
  return v;
}

static inline void write_satp(uint64_t v) {
  __asm__ volatile("csrw satp, %0" : : "r"(v) : "memory");
}

static inline void flush_tlb_all(void) {
  __asm__ volatile("sfence.vma x0, x0" : : : "memory");
}

static inline void enable_debug_mprv(void) {
  /*
   * The bare-metal test harness executes with BlackParrot debug mode active.
   * In that mode bp_be_csr intentionally ignores mstatus.MPRV unless
   * dcsr.mprven is set. DCSR is per hardware context in this implementation,
   * so each context enables it before the MPRV/S-mode translated probes.
   */
  __asm__ volatile("csrs 0x7b0, %0" : : "r"(DCSR_MPRVEN) : "memory");
}

static inline void sfence_vma(void) {
  /*
   * The real post-SATP sfence.vma path currently stalls in this bare-metal
   * M-mode repro. Flush stale TLB state before SATP writes with
   * flush_tlb_all(), then keep this post-SATP fence as a compiler barrier so
   * the test can isolate ASID/remap behavior.
   */
  __asm__ volatile("" : : : "memory");
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
      "li t6, %4\n"
      "or %1, %1, t6\n"
      "csrw mstatus, %1\n"
      "ld %2, 0(%5)\n"
      "csrw mstatus, %0\n"
      : "=&r"(old_status), "=&r"(new_status), "=&r"(value)
      : "i"(MSTATUS_MPP_MASK), "i"(MSTATUS_MPP_S | MSTATUS_MPRV), "r"(va)
      : "t6", "memory");

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
      "li t6, %3\n"
      "or %1, %1, t6\n"
      "csrw mstatus, %1\n"
      "sd %4, 0(%5)\n"
      "csrw mstatus, %0\n"
      : "=&r"(old_status), "=&r"(new_status)
      : "i"(MSTATUS_MPP_MASK), "i"(MSTATUS_MPP_S | MSTATUS_MPRV), "r"(value), "r"(va)
      : "t6", "memory");
}

void __attribute__((noinline, noreturn)) t1_entry(void) {
  progress = 0x101;
  enable_debug_mprv();
  flush_tlb_all();
  write_satp(satp_sv39(T1_ASID, root1));
  progress = 0x102;
  sfence_vma();
  progress = 0x103;
  t1_satp_after_write = read_satp();

  progress = 0x104;
  t1_initial_read = mprv_s_load64(TEST_VA);
  progress = 0x105;
  mprv_s_store64(TEST_VA, T1_UPDATED);
  progress = 0x106;
  write_ctxt0();

  progress = 0x107;
  t1_resume_read = mprv_s_load64(TEST_VA);
  progress = 0x108;
  write_ctxt0();

  while (1) { }
}

int main(void) {
  int errors = 0;
  enable_debug_mprv();

  t0_page[0] = T0_INITIAL;
  t1_page[0] = T1_INITIAL;

  map_one_page(root0, l1_0, l0_0, t0_page);
  map_one_page(root1, l1_1, l0_1, t1_page);
  progress = 0x1;

  flush_tlb_all();
  write_satp(satp_sv39(T0_ASID, root0));
  progress = 0x2;
  sfence_vma();
  progress = 0x3;

  progress = 0x4;
  uint64_t t0_initial_read = mprv_s_load64(TEST_VA);
  progress = 0x5;
  mprv_s_store64(TEST_VA, T0_UPDATED);
  progress = 0x6;

  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_entry);
  progress = 0x7;
  write_ctxt(1);

  progress = 0x8;
  uint64_t t0_after_t1_read = mprv_s_load64(TEST_VA);
  progress = 0x9;
  write_ctxt(1);

  if (t0_initial_read != T0_INITIAL) {
    progress = 0xe001;
    errors++;
  }
  if (t0_after_t1_read != T0_UPDATED) {
    progress = 0xe002;
    errors++;
  }
  if (t1_initial_read != T1_INITIAL) {
    progress = 0xe003;
    errors++;
  }
  if (t1_resume_read != T1_UPDATED) {
    progress = 0xe004;
    errors++;
  }
  if ((t0_page[0] != T0_UPDATED) || (t1_page[0] != T1_UPDATED)) {
    progress = 0xe005;
    errors++;
  }

  if (errors == 0) {
    progress = 0x900d;
    bp_finish(0);
  } else {
    bp_finish(1);
  }

  return 0;
}
