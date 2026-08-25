/**
 * Enter S-mode with SV39 enabled and execute through an identity-mapped 1 GiB
 * leaf.  This isolates translated instruction fetch and MRET privilege entry
 * from delegated page-fault handling.
 */

#include <stdint.h>
#include "bp_utils.h"

#define SV39_SATP_MODE   (8ULL << 60)
#define MSTATUS_MPP_MASK (3ULL << 11)
#define MSTATUS_MPP_S    (1ULL << 11)
#define DRAM_BASE        0x80000000ULL
#define PAGE_WORDS       512

#define PTE_V (1ULL << 0)
#define PTE_R (1ULL << 1)
#define PTE_W (1ULL << 2)
#define PTE_X (1ULL << 3)
#define PTE_A (1ULL << 6)
#define PTE_D (1ULL << 7)

static uint64_t root_page_table[PAGE_WORDS] __attribute__((aligned(4096)));
typedef struct {
  uint64_t mcause;
  uint64_t mepc;
  uint64_t mtval;
} trap_record_s;
static volatile trap_record_s trap_record;

void __attribute__((noinline, noreturn)) machine_recovery(void) {
  bp_print_string("=== S-mode SV39 Entry Trap ===\n");
  bp_print_string("mcause:       ");
  bp_hprint_uint64(trap_record.mcause);
  bp_print_string("\nmepc:         ");
  bp_hprint_uint64(trap_record.mepc);
  bp_print_string("\nmtval:        ");
  bp_hprint_uint64(trap_record.mtval);
  bp_print_string("\n[BSG-FAIL] translated S-mode entry trapped\n");
  bp_finish(1);
  while (1) { }
}

void __attribute__((naked, aligned(4))) machine_trap_entry(void) {
  __asm__ volatile(
      "la t0, trap_record\n"
      "csrr t1, mcause\n"
      "sd t1, 0(t0)\n"
      "csrr t1, mepc\n"
      "sd t1, 8(t0)\n"
      "csrr t1, mtval\n"
      "sd t1, 16(t0)\n"
      "csrr t1, mstatus\n"
      "li t2, 0x1800\n"
      "or t1, t1, t2\n"
      "csrw mstatus, t1\n"
      "la t1, machine_recovery\n"
      "csrw mepc, t1\n"
      "mret\n");
}

void __attribute__((noinline, noreturn)) supervisor_entry(void) {
  uint64_t satp;
  uint64_t sstatus;

  __asm__ volatile("csrr %0, satp" : "=r"(satp));
  __asm__ volatile("csrr %0, sstatus" : "=r"(sstatus));
  bp_print_string("=== S-mode SV39 Entry Test ===\n");
  bp_print_string("satp:         ");
  bp_hprint_uint64(satp);
  bp_print_string("\nsstatus:      ");
  bp_hprint_uint64(sstatus);
  bp_print_string("\n[BSG-PASS] translated S-mode instruction fetch completed\n");
  bp_finish(0);
  while (1) { }
}

int main(void) {
  uint64_t root_ppn = (uint64_t)root_page_table >> 12;
  uint64_t dram_ppn = DRAM_BASE >> 12;
  uint64_t status;

  root_page_table[(DRAM_BASE >> 30) & 0x1ff] =
      (dram_ppn << 10) | PTE_V | PTE_R | PTE_W | PTE_X | PTE_A | PTE_D;
  root_page_table[0] = PTE_V | PTE_R | PTE_W | PTE_X | PTE_A | PTE_D;

  __asm__ volatile("csrw mtvec, %0" : : "r"((uint64_t)machine_trap_entry) : "memory");
  __asm__ volatile("csrw satp, %0" : : "r"(SV39_SATP_MODE | root_ppn) : "memory");
  __asm__ volatile("sfence.vma x0, x0" : : : "memory");
  __asm__ volatile("csrw mepc, %0" : : "r"((uint64_t)supervisor_entry) : "memory");
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  status = (status & ~MSTATUS_MPP_MASK) | MSTATUS_MPP_S;
  __asm__ volatile("csrw mstatus, %0" : : "r"(status) : "memory");
  __asm__ volatile("mret" : : : "memory");
  __builtin_unreachable();
}
