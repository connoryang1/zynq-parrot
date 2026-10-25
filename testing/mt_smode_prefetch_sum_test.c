/* Test S-mode hints to user data through a warm Sv39 DTLB entry.
 * SUM permits one hint; clearing SUM must suppress the next hint without a
 * fault. The guest checks demand values while the trace checks hint issue.
 */
#include <stdint.h>

#include "bp_utils.h"
#include "bp_prefetch.h"

#define DRAM_BASE 0x80000000ULL
#define DATA_VA 0x40000000ULL
#define FIRST_VALUE 0x12345678ULL
#define HINT_VALUE 0x76543210ULL
#define DENIED_VALUE 0xabcdef01ULL

static const volatile uint64_t user_data[512]
  __attribute__((aligned(4096), used)) = {
    [0] = FIRST_VALUE, [8] = HINT_VALUE, [16] = DENIED_VALUE
  };
static uint64_t root[512] __attribute__((aligned(4096)));
static uint64_t middle[512] __attribute__((aligned(4096)));
static uint64_t leaves[512] __attribute__((aligned(4096)));
static volatile uint64_t first_value, hinted_value, denied_value;
static volatile uint64_t unexpected_trap, trap_cause, trap_pc, trap_value;

static void __attribute__((used, noinline, noreturn)) machine_finish(void)
{
  uint64_t preview_status;
  __asm__ volatile("csrr %0, 0x805" : "=r"(preview_status) : : "memory");
  const unsigned physical = (preview_status >> 21) & 0xff;
  const unsigned admitted = (preview_status >> 29) & 0xff;
  const unsigned issued = (preview_status >> 37) & 0xff;
  const unsigned published = (preview_status >> 45) & 0xff;
  bp_print_string("PREVIEW-EVENTS physical/admitted/issued/published: ");
  bp_hprint_uint64(physical);
  bp_hprint_uint64(admitted);
  bp_hprint_uint64(issued);
  bp_hprint_uint64(published);
  bp_print_string("\n");
  if (!unexpected_trap && first_value == FIRST_VALUE
      && hinted_value == HINT_VALUE && denied_value == DENIED_VALUE
      && physical == 1 && admitted == 1 && issued == 1 && published == 1) {
    bp_print_string("[BSG-PASS] S-mode SUM-gated user-data prefetch\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] S-mode SUM-gated user-data prefetch\n");
    bp_print_string("trap/cause/pc/value/data: ");
    bp_hprint_uint64(unexpected_trap);
    bp_hprint_uint64(trap_cause);
    bp_hprint_uint64(trap_pc);
    bp_hprint_uint64(trap_value);
    bp_hprint_uint64(first_value);
    bp_hprint_uint64(hinted_value);
    bp_hprint_uint64(denied_value);
    bp_print_string("\n");
    bp_finish(1);
  }
  for (;;) ;
}

static void __attribute__((naked, aligned(4))) trap_entry(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "csrr t0, mcause\nli t1, 9\nbne t0, t1, 1f\n"
    "li t1, 3\nbne a0, t1, 1f\n"
    "j 2f\n"
    "1: la t1, unexpected_trap\nli t2, 1\nsd t2, 0(t1)\n"
    "csrr t2, mcause\nla t1, trap_cause\nsd t2, 0(t1)\n"
    "csrr t2, mepc\nla t1, trap_pc\nsd t2, 0(t1)\n"
    "csrr t2, mtval\nla t1, trap_value\nsd t2, 0(t1)\n"
    "2: csrr t0, mstatus\nli t1, 0x1800\nor t0, t0, t1\n"
    "csrw mstatus, t0\nla t0, machine_finish\ncsrw mepc, t0\nmret\n"
    ".option pop\n");
}

static void __attribute__((naked, noinline, noreturn, aligned(4096)))
supervisor_entry(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "li a0, 0x40000000\nli t0, 0x40000\ncsrs sstatus, t0\n"
    /* A demand first primes the readable user leaf in the DTLB. */
    "ld t3, 0(a0)\nla t1, first_value\nsd t3, 0(t1)\n"
    "addi a1, a0, 64\n"
    ".global supervisor_permitted_hint\n"
    "supervisor_permitted_hint:\n" BP_PREFETCH_R_ASM("a1")
    "csrc sstatus, t0\n"
    /* Leave time for the detached request before the same-line demand. */
    "li t2, 128\n1: addi t2, t2, -1\nbnez t2, 1b\n"
    "csrs sstatus, t0\n"
    "ld t3, 64(a0)\nla t1, hinted_value\nsd t3, 0(t1)\n"
    "csrc sstatus, t0\naddi a1, a0, 128\n"
    ".global supervisor_denied_hint\n"
    "supervisor_denied_hint:\n" BP_PREFETCH_R_ASM("a1")
    "csrs sstatus, t0\nld t3, 128(a0)\n"
    "la t1, denied_value\nsd t3, 0(t1)\n"
    "li a0, 3\necall\n2: j 2b\n.option pop\n");
}

int main(void)
{
  uint64_t status;
  uintptr_t supervisor_pc = (uintptr_t)supervisor_entry;
  bp_print_string("[BSG-INFO] S-mode Sv39 SUM prefetch setup\n");
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile(
    "csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:"
    : : : "t0", "memory");
#endif
  __asm__ volatile("csrw medeleg, zero\ncsrw mideleg, zero" : : : "memory");
  /* Code and stack are supervisor mappings; the data leaf is user readable. */
  const uint64_t broad = PTE_V | PTE_R | PTE_W | PTE_X | PTE_A | PTE_D;
  root[0] = ((DRAM_BASE >> 12) << 10) | broad;
  root[2] = root[0];
  root[1] = ((((uint64_t)middle & 0xffffffffULL) >> 12) << 10) | PTE_V;
  middle[0] = ((((uint64_t)leaves & 0xffffffffULL) >> 12) << 10) | PTE_V;
  leaves[0] = ((((uint64_t)user_data & 0xffffffffULL) >> 12) << 10)
    | PTE_V | PTE_R | PTE_U | PTE_A;
  __asm__ volatile("fence rw, rw\ncsrw satp, %0\nsfence.vma"
    : : "r"((8ULL << 60) | (((uint64_t)root & 0xffffffffULL) >> 12)) : "memory");
  supervisor_pc = (supervisor_pc & 0xffffffffULL) - DRAM_BASE;
  __asm__ volatile("csrw mtvec, %0" : : "r"((uint64_t)trap_entry) : "memory");
  __asm__ volatile("csrw mepc, %0" : : "r"(supervisor_pc) : "memory");
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  status &= ~((3ULL << 11) | (1ULL << 19) | (1ULL << 18));
  status |= 1ULL << 11;  /* MPP=S; start with SUM=0. */
  // Count the single permitted hint after translation, queue admission,
  // memory issue, and complete detached response publication.
  __asm__ volatile("csrw 0x805, %0" : : "r"(2ULL) : "memory");
  __asm__ volatile("csrw mstatus, %0\nmret" : : "r"(status) : "memory");
  __builtin_unreachable();
}
