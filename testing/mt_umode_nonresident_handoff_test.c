/*
 * Reproduce the Linux userspace nonresident-handoff boundary in bare metal.
 * A U-mode ECALL returns immediately before the switch, context 2 begins on a
 * cold instruction line and completes its own ECALL, and any stale sequential
 * execution is reported. This covers ordinary trap redirects around the
 * nonresident handoff without requiring Linux or a new FPGA bitstream.
 */

#include <stdint.h>

#include "bp_utils.h"
#define MSTATUS_MPP_MASK (3ULL << 11)
#define CTXT_SHIFT 39
#define REG_SHIFT 41
#define LOW39_MASK 0x7fffffffffULL
#define DRAM_BASE 0x80000000ULL
#define PAGE_WORDS 512
#define SV39_SATP_MODE (8ULL << 60)

#ifndef BP_ENABLE_SV39
#define BP_ENABLE_SV39 0
#endif

#ifndef BP_TARGET_PRE_ECALL_STORE
#define BP_TARGET_PRE_ECALL_STORE 0
#endif

static inline uint64_t encode_context_reg2(uint64_t reg, uint64_t value)
{
  return (value & LOW39_MASK) | (2ULL << CTXT_SHIFT) | (reg << REG_SHIFT);
}

static inline uint64_t encode_context_npc2(uint64_t pc)
{
  return (pc & LOW39_MASK) | (2ULL << CTXT_SHIFT);
}

static inline uint64_t sv39_low_alias(uint64_t paddr)
{
  /* medany code pointers in the 0x80000000 region are sign-extended.  Reduce
   * them to the FPGA's 32-bit physical address before forming the low alias. */
  return (paddr & 0xffffffffULL) - DRAM_BASE;
}

static volatile uint64_t target_seen;
static volatile uint64_t target_entered;
static volatile uint64_t result_context;
static volatile uint64_t result_code;
static volatile uint64_t unexpected_mcause;
static uint64_t root_page_table[PAGE_WORDS] __attribute__((aligned(4096)));

static void __attribute__((used, noinline, noreturn)) machine_finish(void)
{
  if ((result_code == 0) && (target_seen == 1)
      && (!BP_TARGET_PRE_ECALL_STORE || (target_entered == 1))
      && (result_context == 0)) {
    bp_print_string("[BSG-PASS] U-mode nonresident handoff redirected before sequential issue\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] U-mode nonresident handoff leaked sequential execution\n");
    bp_print_string("target seen: ");
    bp_hprint_uint64(target_seen);
    bp_print_string("\ntarget entered: ");
    bp_hprint_uint64(target_entered);
    bp_print_string("\nresumed context: ");
    bp_hprint_uint64(result_context);
    bp_print_string("\nunexpected mcause: ");
    bp_hprint_uint64(unexpected_mcause);
    bp_print_string("\n");
    bp_finish(1);
  }

  for (;;)
    ;
}

static void __attribute__((naked, aligned(4))) machine_trap_entry(void)
{
  __asm__ volatile(
    "csrr t0, mcause\n\t"
    "li t1, 8\n\t"
    "bne t0, t1, 4f\n\t"
    "li t1, 2\n\t"
    "beq a0, t1, 2f\n\t"
    "li t1, 3\n\t"
    "beq a0, t1, 3f\n\t"
    "1:\n\t"
    "csrr t0, mepc\n\t"
    "addi t0, t0, 4\n\t"
    "csrw mepc, t0\n\t"
    "mret\n\t"
    "2:\n\t"
    "la t0, target_seen\n\t"
    "li t1, 1\n\t"
    "sd t1, 0(t0)\n\t"
    "j 1b\n\t"
    "3:\n\t"
    "csrr t0, mstatus\n\t"
    "li t1, 0x1800\n\t"
    "or t0, t0, t1\n\t"
    "csrw mstatus, t0\n\t"
    "la t0, machine_finish\n\t"
    "csrw mepc, t0\n\t"
    "mret\n\t"
    "4:\n\t"
    "la t1, unexpected_mcause\n\t"
    "sd t0, 0(t1)\n\t"
    "li a0, 3\n\t"
    "j 3b\n\t"
  );
}

static void __attribute__((naked, noinline, noreturn, aligned(4096))) target_entry(void)
{
  __asm__ volatile(
#if BP_TARGET_PRE_ECALL_STORE
    /* Force translated target data access and DTLB replay before the trap. */
    "la t0, target_entered\n\t"
    "li t1, 1\n\t"
    "sd t1, 0(t0)\n\t"
#endif
    /* Context 2 starts with a0=2, so the shared M-mode trap handler records
     * target_seen, advances MEPC, and returns here. */
    "ecall\n\t"
    "csrwi 0x800, 0\n\t"
    "1: j 1b\n\t"
  );
}

static void __attribute__((noinline, noreturn, aligned(4096))) user_entry(void)
{
  uint64_t context;
  uint64_t encoded_npc;
  uint64_t gp_value;
  volatile uint64_t target_pc = (uint64_t)target_entry;

  target_seen = 0;
  target_entered = 0;
  result_context = ~0ULL;
  result_code = 1;
  unexpected_mcause = 0;

  __asm__ volatile("mv %0, gp" : "=r"(gp_value));
  __asm__ volatile(
    "csrw 0x802, %0"
    :
    : "r"(encode_context_reg2(3, gp_value))
    : "memory"
  );
  __asm__ volatile(
    "csrw 0x802, %0"
    :
    : "r"(encode_context_reg2(10, 2))
    : "memory"
  );

  register uint64_t a0 __asm__("a0") = 1;
  __asm__ volatile("ecall" : "+r"(a0) : : "t0", "t1", "memory");

  /* In the Sv39 case this function is already executing at its low alias, so
   * the PC-relative target pointer is already a low virtual address. */
  encoded_npc = encode_context_npc2((uint64_t)target_pc);
  __asm__ volatile(
    "csrw 0x801, %1\n\t"
    "csrwi 0x800, 2\n\t"
    "csrr %0, 0x800\n\t"
    : "=&r"(context)
    : "r"(encoded_npc)
    : "memory"
  );

  result_context = context;
  result_code = !((target_seen == 1)
                  && (!BP_TARGET_PRE_ECALL_STORE || (target_entered == 1))
                  && (context == 0));

  register uint64_t finish_a0 __asm__("a0") = 3;
  __asm__ volatile("ecall" : "+r"(finish_a0) : : "t0", "t1", "memory");
  for (;;)
    ;
}

int main(void)
{
  uint64_t status;
  volatile uint64_t user_pc = (uint64_t)user_entry;

  bp_print_string("[BSG-INFO] U-mode handoff test reached M-mode setup\n");
  /* The minimal Verilator wrapper enters through debug mode.  Leave it before
   * provoking an ECALL so architectural exceptions use mtvec, as on Linux. */
  __asm__ volatile(
    "csrr t0, dcsr\n\t"
    "ori t0, t0, 3\n\t"
    "csrw dcsr, t0\n\t"
    "la t0, 1f\n\t"
    "csrw dpc, t0\n\t"
    "dret\n\t"
    "1:"
    :
    :
    : "t0", "memory"
  );
  /* Bare-metal startup may delegate U-mode ECALLs to S-mode.  This test owns
   * the trap path, so route all exceptions and interrupts directly to M-mode. */
  __asm__ volatile("csrw medeleg, zero\n\tcsrw mideleg, zero" ::: "memory");
  if (BP_ENABLE_SV39) {
    const uint64_t dram_ppn = DRAM_BASE >> 12;
    const uint64_t user_leaf = (dram_ppn << 10)
                               | PTE_V | PTE_R | PTE_W | PTE_X | PTE_U | PTE_A | PTE_D;
    root_page_table[0] = user_leaf;
    root_page_table[(DRAM_BASE >> 30) & 0x1ff] = user_leaf;
    __asm__ volatile("csrw satp, %0\n\tsfence.vma"
                     :
                     : "r"(SV39_SATP_MODE | ((uint64_t)root_page_table >> 12))
                     : "memory");
    user_pc = sv39_low_alias(user_pc);
  } else {
    __asm__ volatile("csrw satp, zero\n\tsfence.vma" ::: "memory");
  }
  __asm__ volatile("csrw mtvec, %0" : : "r"((uint64_t)machine_trap_entry) : "memory");
  __asm__ volatile("csrw mepc, %0" : : "r"(user_pc) : "memory");
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  status &= ~MSTATUS_MPP_MASK;
  __asm__ volatile("csrw mstatus, %0" : : "r"(status) : "memory");
  __asm__ volatile("mret" : : : "memory");
  __builtin_unreachable();
}
