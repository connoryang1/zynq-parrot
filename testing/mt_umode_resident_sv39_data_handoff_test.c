/*
 * Exercise first-time initialization of an already-resident context in U-mode.
 * Low virtual instruction/data addresses map to DRAM through Sv39, so leaving
 * context 1 in reset M-mode/Bare state cannot accidentally pass. The target's
 * ECALL must report U-mode cause 8; seeded and restored s11 values check that
 * initializing its CSR bank does not overwrite either context's integer state.
 */

#include <stdint.h>
#include "bp_utils.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "This regression requires the accepted two-resident/four-logical topology"
#endif

#define DRAM_BASE 0x80000000ULL
#define LOW39_MASK 0x7fffffffffULL
#define TARGET_SEED 0x12345678ULL
#define SOURCE_SEED 0x76543210ULL

static volatile uint64_t target_entered;
static volatile uint64_t target_context;
static volatile uint64_t target_register;
static volatile uint64_t trap_seen;
static volatile uint64_t result_context;
static volatile uint64_t result_register;
static volatile uint64_t unexpected_mcause;
static uint64_t root_page_table[512] __attribute__((aligned(4096)));

static uint64_t context_reg1(uint64_t reg, uint64_t value)
{
  return (value & LOW39_MASK) | (1ULL << 39) | (reg << 41);
}

static void __attribute__((used, noinline, noreturn)) machine_finish(void)
{
  if (target_entered == 1 && target_context == 1
      && target_register == TARGET_SEED && trap_seen == 3
      && result_context == 0 && result_register == SOURCE_SEED
      && unexpected_mcause == 0) {
    bp_print_string("[BSG-PASS] resident U-mode Sv39 instruction/data handoff and ECALL preserved state\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] resident U-mode Sv39 initialization\n");
    bp_print_string("target entered/context/register: ");
    bp_hprint_uint64(target_entered);
    bp_hprint_uint64(target_context);
    bp_hprint_uint64(target_register);
    bp_print_string("\ntrap mask/resumed context/register/cause: ");
    bp_hprint_uint64(trap_seen);
    bp_hprint_uint64(result_context);
    bp_hprint_uint64(result_register);
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
    "li t1, 3\n\t"
    "beq a0, t1, 3f\n\t"
    /* a0=1 for the source, a0=2 for the target; both must ECALL from U. */
    "la t0, trap_seen\n\t"
    "ld t1, 0(t0)\n\t"
    "or t1, t1, a0\n\t"
    "sd t1, 0(t0)\n\t"
    "csrr t0, mepc\n\t"
    "addi t0, t0, 4\n\t"
    "csrw mepc, t0\n\t"
    "mret\n\t"
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
    "j 3b\n\t"
  );
}

static void __attribute__((naked, noinline, noreturn, aligned(4096))) target_entry(void)
{
  __asm__ volatile(
    /* PC-relative symbols are low virtual addresses here, forcing DTLB use. */
    "la t0, target_entered\n\t"
    "li t1, 1\n\t"
    "sd t1, 0(t0)\n\t"
    "la t0, target_context\n\t"
    "csrr t1, 0x800\n\t"
    "sd t1, 0(t0)\n\t"
    "la t0, target_register\n\t"
    "sd s11, 0(t0)\n\t"
    "li s11, 0x1111\n\t"
    "ecall\n\t"
    "csrwi 0x800, 0\n\t"
    "1: j 1b\n\t"
  );
}

static void __attribute__((noinline, noreturn, aligned(4096))) user_entry(void)
{
  uint64_t gp_value, resumed_context, resumed_register;
  /* The PC-relative pointer is already a low VA while executing this alias. */
  volatile uint64_t target_pc = (uint64_t)target_entry;
  __asm__ volatile("mv %0, gp" : "=r"(gp_value));
  __asm__ volatile("csrw 0x802, %0" : : "r"(context_reg1(3, gp_value)) : "memory");
  __asm__ volatile("csrw 0x802, %0" : : "r"(context_reg1(10, 2)) : "memory");
  __asm__ volatile("csrw 0x802, %0" : : "r"(context_reg1(27, TARGET_SEED)) : "memory");

  register uint64_t a0 __asm__("a0") = 1;
  __asm__ volatile("ecall" : "+r"(a0) : : "t0", "t1", "memory");
  uint64_t encoded_npc = (target_pc & LOW39_MASK) | (1ULL << 39);
  __asm__ volatile(
    "li s11, 0x76543210\n\t"
    "csrw 0x801, %2\n\t"
    "csrwi 0x800, 1\n\t"
    "csrr %0, 0x800\n\t"
    "mv %1, s11\n\t"
    : "=&r"(resumed_context), "=&r"(resumed_register)
    : "r"(encoded_npc)
    : "s11", "memory"
  );
  result_context = resumed_context;
  result_register = resumed_register;
  register uint64_t finish_a0 __asm__("a0") = 3;
  __asm__ volatile("ecall" : "+r"(finish_a0) : : "t0", "t1", "memory");
  for (;;)
    ;
}

int main(void)
{
  uint64_t status;
  volatile uint64_t user_pc = (uint64_t)user_entry;
  bp_print_string("[BSG-INFO] resident U-mode Sv39 initialization setup\n");
#ifndef BP_FPGA_PROGRAM
  /* The minimal simulator CRT starts in debug mode, unlike the FPGA CRT. */
  __asm__ volatile(
    "csrr t0, dcsr\n\tori t0, t0, 3\n\tcsrw dcsr, t0\n\t"
    "la t0, 1f\n\tcsrw dpc, t0\n\tdret\n\t1:"
    : : : "t0", "memory"
  );
#endif
  __asm__ volatile("csrw medeleg, zero\n\tcsrw mideleg, zero" : : : "memory");
  const uint64_t leaf = ((DRAM_BASE >> 12) << 10)
    | PTE_V | PTE_R | PTE_W | PTE_X | PTE_U | PTE_A | PTE_D;
  root_page_table[0] = leaf;
  root_page_table[2] = leaf;
  __asm__ volatile("csrw satp, %0\n\tsfence.vma"
    : : "r"((8ULL << 60) | ((uint64_t)root_page_table >> 12)) : "memory");
  user_pc = (user_pc & 0xffffffffULL) - DRAM_BASE;
  __asm__ volatile("csrw mtvec, %0" : : "r"((uint64_t)machine_trap_entry) : "memory");
  __asm__ volatile("csrw mepc, %0" : : "r"(user_pc) : "memory");
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  __asm__ volatile("csrw mstatus, %0" : : "r"(status & ~(3ULL << 11)) : "memory");
  __asm__ volatile("mret" : : : "memory");
  __builtin_unreachable();
}
