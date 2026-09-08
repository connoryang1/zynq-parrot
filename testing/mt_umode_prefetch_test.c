/* Check that U-mode prefetch hints preserve Sv39 permissions and never trap.
 * A permitted load primes one 4 KiB translation; an explicitly denied demand
 * must fault before a hint accesses that same page. Trace evidence, rather
 * than successful execution alone, establishes hint issuance or rejection.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "bp_prefetch.h"

#define DRAM_BASE 0x80000000ULL
#define DATA_VA 0x40000000ULL
#define FIRST_VALUE 0x12345678ULL
#define HINT_VALUE 0x76543210ULL

static const volatile uint64_t readable_page[512]
  __attribute__((aligned(4096), used)) = {[0] = FIRST_VALUE, [8] = HINT_VALUE};
static const volatile uint64_t execute_only_page[512]
  __attribute__((aligned(4096), used)) = {[0] = 0xabcdef};
static uint64_t root[512] __attribute__((aligned(4096)));
static uint64_t middle[512] __attribute__((aligned(4096)));
static uint64_t leaves[512] __attribute__((aligned(4096)));
static volatile uint64_t value_before, value_after, hints_completed, denied_faults;
static volatile uint64_t unexpected_trap, trap_cause, trap_pc, trap_value, exit_satp;

static void __attribute__((used, noinline, noreturn)) machine_finish(void)
{
  if (!unexpected_trap && denied_faults == 1 && hints_completed == 5
      && value_before == FIRST_VALUE && value_after == HINT_VALUE
      && exit_satp == ((8ULL << 60) | (((uint64_t)root & 0xffffffffULL) >> 12))) {
    bp_print_string("[BSG-PASS] U-mode Sv39 nonfaulting prefetch permissions\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] U-mode Sv39 prefetch permissions\n");
    bp_print_string("unexpected/cause/pc/tval/denied/hints/values/satp: ");
    bp_hprint_uint64(unexpected_trap);
    bp_hprint_uint64(trap_cause);
    bp_hprint_uint64(trap_pc);
    bp_hprint_uint64(trap_value);
    bp_hprint_uint64(denied_faults);
    bp_hprint_uint64(hints_completed);
    bp_hprint_uint64(value_before);
    bp_hprint_uint64(value_after);
    bp_hprint_uint64(exit_satp);
    bp_print_string("\n");
    bp_finish(1);
  }
  for (;;) ;
}

/* Only the labelled ordinary denied load may page-fault. Any exception from
 * a hint, or any other instruction, immediately fails with its actual inputs.
 * t0/t1/t2 are scratch; the U-mode leaf keeps live addresses in a0/a1.
 */
static void __attribute__((naked, aligned(4))) trap_entry(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "csrr t0, mcause\nli t1, 13\nbne t0, t1, 2f\n"
    "csrr t0, mepc\nla t1, user_denied_load\nli t2, 0x80000000\n"
    "subw t1, t1, t2\nbne t0, t1, 4f\n"
    "csrr t0, mtval\nli t1, 0x40001000\nbne t0, t1, 4f\n"
    "la t0, denied_faults\nld t1, 0(t0)\naddi t1, t1, 1\nsd t1, 0(t0)\n"
    "csrr t0, mepc\naddi t0, t0, 4\ncsrw mepc, t0\nmret\n"
    "2: li t1, 8\nbne t0, t1, 4f\nli t1, 3\nbne a0, t1, 4f\n"
    "csrr t0, satp\nla t1, exit_satp\nsd t0, 0(t1)\n"
    "3: csrr t0, mstatus\nli t1, 0x1800\nor t0, t0, t1\ncsrw mstatus, t0\n"
    "la t0, machine_finish\ncsrw mepc, t0\nmret\n"
    "4: la t0, unexpected_trap\nli t1, 1\nsd t1, 0(t0)\n"
    "csrr t0, mcause\nla t1, trap_cause\nsd t0, 0(t1)\n"
    "csrr t0, mepc\nla t1, trap_pc\nsd t0, 0(t1)\n"
    "csrr t0, mtval\nla t1, trap_value\nsd t0, 0(t1)\nj 3b\n"
    ".option pop\n");
}

static void __attribute__((naked, noinline, noreturn, aligned(4096))) user_entry(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    /* This ordinary demand primes the readable page's DTLB entry and only
     * its first cache line. The permitted hint targets a different line.
     */
    "li a0, 0x40000000\nld t3, 0(a0)\nla t0, value_before\nsd t3, 0(t0)\n"
    "li a1, 0x40001000\n.global user_denied_load\nuser_denied_load:\nld t3, 0(a1)\n"
    /* The prior demand verifies that the execute-only leaf is not readable.
     * A trace must establish whether its denied translation remains cached.
     */
    ".global user_denied_hint\nuser_denied_hint:\n" BP_PREFETCH_R_ASM("a1")
    "li a1, 0x40003000\n.global user_unmapped_hint\nuser_unmapped_hint:\n" BP_PREFETCH_R_ASM("a1")
    "li a1, 0x8000000000000000\n.global user_noncanonical_hint\nuser_noncanonical_hint:\n" BP_PREFETCH_R_ASM("a1")
    /* This mapped VA names CLINT mtime, but no ordinary MMIO read is used
     * to prime it. A cold DTLB drop is sufficient for functional acceptance;
     * a PMA-hit rejection claim requires separate waveform evidence.
     */
    "li a1, 0x40002ff8\n.global user_mmio_hint\nuser_mmio_hint:\n" BP_PREFETCH_R_ASM("a1")
    "addi a1, a0, 64\n.global user_readable_hint\nuser_readable_hint:\n" BP_PREFETCH_R_ASM("a1")
    "ld t3, 64(a0)\nla t0, value_after\nsd t3, 0(t0)\n"
    "la t0, hints_completed\nli t3, 5\nsd t3, 0(t0)\nfence rw, rw\n"
    "li a0, 3\necall\n1: j 1b\n.option pop\n");
}

int main(void)
{
  uint64_t status;
  volatile uint64_t user_pc = (uint64_t)user_entry;
  bp_print_string("[BSG-INFO] U-mode Sv39 prefetch permission setup\n");
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile(
    "csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:"
    : : : "t0", "memory");
#endif
  __asm__ volatile("csrw medeleg, zero\ncsrw mideleg, zero" : : : "memory");
  /* Retain the accepted low code and high stack aliases. Data uses explicit
   * three-level Sv39 page tables; all remaining leaves stay invalid.
   */
  const uint64_t broad = PTE_V | PTE_R | PTE_W | PTE_X | PTE_U | PTE_A | PTE_D;
  root[0] = ((DRAM_BASE >> 12) << 10) | broad;
  root[2] = root[0];
  root[1] = ((((uint64_t)middle & 0xffffffffULL) >> 12) << 10) | PTE_V;
  middle[0] = ((((uint64_t)leaves & 0xffffffffULL) >> 12) << 10) | PTE_V;
  leaves[0] = ((((uint64_t)readable_page & 0xffffffffULL) >> 12) << 10)
    | PTE_V | PTE_R | PTE_U | PTE_A;
  leaves[1] = ((((uint64_t)execute_only_page & 0xffffffffULL) >> 12) << 10)
    | PTE_V | PTE_X | PTE_U | PTE_A;
  leaves[2] = ((0x0030b000ULL >> 12) << 10) | PTE_V | PTE_R | PTE_U | PTE_A;
  __asm__ volatile("fence rw, rw\ncsrw satp, %0\nsfence.vma"
    : : "r"((8ULL << 60) | (((uint64_t)root & 0xffffffffULL) >> 12)) : "memory");
  user_pc = (user_pc & 0xffffffffULL) - DRAM_BASE;
  __asm__ volatile("csrw mtvec, %0" : : "r"((uint64_t)trap_entry) : "memory");
  __asm__ volatile("csrw mepc, %0" : : "r"(user_pc) : "memory");
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  /* MXR must be zero so an execute-only page cannot satisfy the denied load. */
  status &= ~((3ULL << 11) | (1ULL << 19) | (1ULL << 17));
  __asm__ volatile("csrw mstatus, %0\nmret" : : "r"(status) : "memory");
  __builtin_unreachable();
}
