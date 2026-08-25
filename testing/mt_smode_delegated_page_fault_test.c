/**
 * Delegate an S-mode translated load-page-fault to stvec, recover with SRET,
 * and verify scause/sepc/stval.  DRAM and host-I/O are identity-mapped while
 * TEST_VA is intentionally left unmapped.
 */

#include <stdint.h>
#include "bp_utils.h"

#define SV39_SATP_MODE   (8ULL << 60)
#define MSTATUS_MPP_MASK (3ULL << 11)
#define MSTATUS_MPP_S    (1ULL << 11)
#define DRAM_BASE        0x80000000ULL
#define TEST_VA          0x0000000040000000ULL
#define LOAD_PAGE_FAULT  13ULL
#define PAGE_WORDS       512

#define PTE_V (1ULL << 0)
#define PTE_R (1ULL << 1)
#define PTE_W (1ULL << 2)
#define PTE_X (1ULL << 3)
#define PTE_A (1ULL << 6)
#define PTE_D (1ULL << 7)

typedef struct {
  uint64_t scause;
  uint64_t sepc;
  uint64_t stval;
  uint64_t sstatus;
  uint64_t seen;
  uint64_t saved_t1;
} trap_record_s;

static uint64_t root_page_table[PAGE_WORDS] __attribute__((aligned(4096)));
static volatile trap_record_s trap_record;

void __attribute__((naked, aligned(4))) supervisor_trap_entry(void) {
  __asm__ volatile(
      "csrrw t0, sscratch, t0\n"
      "sd t1, 40(t0)\n"
      "csrr t1, scause\n"
      "sd t1, 0(t0)\n"
      "csrr t1, sepc\n"
      "sd t1, 8(t0)\n"
      "addi t1, t1, 4\n"
      "csrw sepc, t1\n"
      "csrr t1, stval\n"
      "sd t1, 16(t0)\n"
      "csrr t1, sstatus\n"
      "sd t1, 24(t0)\n"
      "li t1, 1\n"
      "sd t1, 32(t0)\n"
      "ld t1, 40(t0)\n"
      "csrrw t0, sscratch, t0\n"
      "sret\n");
}

void __attribute__((noinline, noreturn)) supervisor_entry(void) {
  __asm__ volatile(
      ".option push\n"
      ".option norvc\n"
      "ld zero, 0(%0)\n"
      ".option pop\n"
      : : "r"(TEST_VA) : "memory");

  bp_print_string("=== Delegated S-mode Page Fault Test ===\n");
  bp_print_string("seen:         ");
  bp_hprint_uint64(trap_record.seen);
  bp_print_string("\nscause:       ");
  bp_hprint_uint64(trap_record.scause);
  bp_print_string("\nsepc:         ");
  bp_hprint_uint64(trap_record.sepc);
  bp_print_string("\nstval:        ");
  bp_hprint_uint64(trap_record.stval);
  bp_print_string("\nsstatus:      ");
  bp_hprint_uint64(trap_record.sstatus);
  bp_print_string("\n");

  if ((trap_record.seen == 1)
      && (trap_record.scause == LOAD_PAGE_FAULT)
      && (trap_record.stval == TEST_VA)) {
    bp_print_string("[BSG-PASS] delegated S-mode page fault recovered\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] delegated S-mode page fault mismatch\n");
    bp_finish(1);
  }
  while (1) { }
}

int main(void) {
  uint64_t root_ppn = (uint64_t)root_page_table >> 12;
  uint64_t dram_ppn = DRAM_BASE >> 12;
  uint64_t status;
  uint64_t delegation = 1ULL << LOAD_PAGE_FAULT;

  root_page_table[0] = PTE_V | PTE_R | PTE_W | PTE_X | PTE_A | PTE_D;
  root_page_table[(DRAM_BASE >> 30) & 0x1ff] =
      (dram_ppn << 10) | PTE_V | PTE_R | PTE_W | PTE_X | PTE_A | PTE_D;

  __asm__ volatile("csrw stvec, %0" : : "r"((uint64_t)supervisor_trap_entry) : "memory");
  __asm__ volatile("csrw sscratch, %0" : : "r"((uint64_t)&trap_record) : "memory");
  __asm__ volatile("csrs medeleg, %0" : : "r"(delegation) : "memory");
  __asm__ volatile("csrw satp, %0" : : "r"(SV39_SATP_MODE | root_ppn) : "memory");
  __asm__ volatile("sfence.vma x0, x0" : : : "memory");
  __asm__ volatile("csrw mepc, %0" : : "r"((uint64_t)supervisor_entry) : "memory");
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  status = (status & ~MSTATUS_MPP_MASK) | MSTATUS_MPP_S;
  __asm__ volatile("csrw mstatus, %0" : : "r"(status) : "memory");
  __asm__ volatile("mret" : : : "memory");
  __builtin_unreachable();
}
