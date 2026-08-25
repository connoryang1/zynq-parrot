/**
 * Minimal translated load-page-fault and M-mode recovery probe.
 *
 * MPRV makes one load use S-mode translation through an empty SV39 root.  A
 * naked M-mode handler clears MPRV before touching memory, records the trap
 * CSRs, skips the faulting 32-bit load, and returns with MRET.
 */

#include <stdint.h>
#include "bp_utils.h"

#define SV39_SATP_MODE  (8ULL << 60)
#define MSTATUS_MPP_MASK (3ULL << 11)
#define MSTATUS_MPP_S    (1ULL << 11)
#define MSTATUS_MPRV     (1ULL << 17)
#define DCSR_MPRVEN      (1ULL << 4)
#define LOAD_PAGE_FAULT  13ULL
#define TEST_VA          0x0000000040000000ULL
#define PAGE_WORDS       512

typedef struct {
  uint64_t mcause;
  uint64_t mepc;
  uint64_t mtval;
  uint64_t mstatus;
  uint64_t seen;
} trap_record_s;

static uint64_t empty_root[PAGE_WORDS] __attribute__((aligned(4096)));
static volatile trap_record_s trap_record;

void __attribute__((naked, aligned(4))) page_fault_entry(void) {
  __asm__ volatile(
      "csrrw t0, mscratch, t0\n"
      "csrw sscratch, t1\n"
      "li t1, 0x20000\n"
      "csrc mstatus, t1\n"
      "csrr t1, mcause\n"
      "sd t1, 0(t0)\n"
      "csrr t1, mepc\n"
      "sd t1, 8(t0)\n"
      "addi t1, t1, 4\n"
      "csrw mepc, t1\n"
      "csrr t1, mtval\n"
      "sd t1, 16(t0)\n"
      "csrr t1, mstatus\n"
      "sd t1, 24(t0)\n"
      "li t1, 1\n"
      "sd t1, 32(t0)\n"
      "csrr t1, sscratch\n"
      "csrrw t0, mscratch, t0\n"
      "mret\n");
}

int main(void) {
  uint64_t satp = SV39_SATP_MODE | ((uint64_t)empty_root >> 12);
  uint64_t status;

  __asm__ volatile("csrw mtvec, %0" : : "r"((uint64_t)page_fault_entry) : "memory");
  __asm__ volatile("csrw mscratch, %0" : : "r"((uint64_t)&trap_record) : "memory");
  __asm__ volatile("csrs 0x7b0, %0" : : "r"(DCSR_MPRVEN) : "memory");
  __asm__ volatile("csrw satp, %0" : : "r"(satp) : "memory");
  __asm__ volatile("sfence.vma x0, x0" : : : "memory");

  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  status = (status & ~MSTATUS_MPP_MASK) | MSTATUS_MPP_S | MSTATUS_MPRV;
  __asm__ volatile("csrw mstatus, %0" : : "r"(status) : "memory");
  __asm__ volatile(
      ".option push\n"
      ".option norvc\n"
      "ld zero, 0(%0)\n"
      ".option pop\n"
      : : "r"(TEST_VA) : "memory");

  bp_print_string("=== MPRV Load Page Fault Test ===\n");
  bp_print_string("seen:         ");
  bp_hprint_uint64(trap_record.seen);
  bp_print_string("\nmcause:       ");
  bp_hprint_uint64(trap_record.mcause);
  bp_print_string("\nmepc:         ");
  bp_hprint_uint64(trap_record.mepc);
  bp_print_string("\nmtval:        ");
  bp_hprint_uint64(trap_record.mtval);
  bp_print_string("\nmstatus:      ");
  bp_hprint_uint64(trap_record.mstatus);
  bp_print_string("\n");

  if ((trap_record.seen == 1)
      && (trap_record.mcause == LOAD_PAGE_FAULT)
      && (trap_record.mtval == TEST_VA)) {
    bp_print_string("[BSG-PASS] translated load page fault recovered\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] translated load page fault mismatch\n");
    bp_finish(1);
  }

  return 0;
}
