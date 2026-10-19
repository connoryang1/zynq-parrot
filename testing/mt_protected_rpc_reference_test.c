/*
 * Establish a software protected-RPC reference before adding a hardware fast
 * path. Two U-mode domains use distinct Sv39 page tables; an M-mode reference
 * monitor validates a capability, switches address spaces at a fixed entry,
 * protects the return continuation, and restores the caller's ABI state.
 */

#include <stdint.h>

#include "bp_utils.h"

#ifndef RPC_FLUSH_ON_SWITCH
#define RPC_FLUSH_ON_SWITCH 0
#endif

#define MSTATUS_MPP_MASK (UINT64_C(3) << 11)
#define MSTATUS_MPP_M    (UINT64_C(3) << 11)
#define SV39_MODE        (UINT64_C(8) << 60)
#define SATP_ASID_SHIFT  44

#define RPC_OP_CALL      UINT64_C(0x71)
#define RPC_OP_RETURN    UINT64_C(0x72)
#define RPC_OP_FINISH    UINT64_C(0x73)
#define RPC_CAP_ADD      UINT64_C(1)
#define RPC_ERR_CAP      UINT64_C(-1)

#define CALLER_ENTRY_VA  UINT64_C(0x10000)
#define SERVER_ENTRY_VA  UINT64_C(0x20000)
#define PRIVATE_VA       UINT64_C(0x40000)
#define SHARED_VA        UINT64_C(0x50000)
#define STACK_VA         UINT64_C(0x60000)
#define STACK_TOP_VA     (STACK_VA + UINT64_C(0xff0))

#define CALLER_PRIVATE_VALUE UINT64_C(0x1111222233334444)
#define SERVER_PRIVATE_VALUE UINT64_C(0x5555666677778888)
#define SHARED_INPUT         UINT64_C(0x33)
#define RPC_EXPECTED_RESULT  UINT64_C(0x43)

struct rpc_saved_state {
  uint64_t ra, sp, gp, tp;
  uint64_t s0, s1, s2, s3, s4, s5;
  uint64_t s6, s7, s8, s9, s10, s11;
  uint64_t mepc, satp;
};

static struct rpc_saved_state caller_state __attribute__((used));
static volatile uint64_t current_domain;
static volatile uint64_t return_active;
static volatile uint64_t call_count;
static volatile uint64_t unexpected_mcause;
static uint64_t caller_satp_value;
static uint64_t server_satp_value __attribute__((used));
static uint64_t monitor_sp __attribute__((used));

static uint64_t caller_root[512] __attribute__((aligned(4096)));
static uint64_t caller_middle[512] __attribute__((aligned(4096)));
static uint64_t caller_leaf[512] __attribute__((aligned(4096)));
static uint64_t server_root[512] __attribute__((aligned(4096)));
static uint64_t server_middle[512] __attribute__((aligned(4096)));
static uint64_t server_leaf[512] __attribute__((aligned(4096)));

static uint64_t caller_private[512] __attribute__((aligned(4096)));
static uint64_t server_private[512] __attribute__((aligned(4096)));
static uint64_t shared_page[512] __attribute__((aligned(4096)));
static uint64_t caller_stack[512] __attribute__((aligned(4096)));
static uint64_t server_stack[512] __attribute__((aligned(4096)));

static inline uint64_t physical_address(const void *ptr)
{
  return (uint64_t)ptr & UINT64_C(0xffffffff);
}

static inline uint64_t pointer_pte(const void *ptr)
{
  return ((physical_address(ptr) >> 12) << 10) | PTE_V;
}

static inline uint64_t leaf_pte(const void *ptr, uint64_t flags)
{
  return ((physical_address(ptr) >> 12) << 10) | flags;
}

static void map_low_page(uint64_t *leaf, uint64_t va, const void *pa,
                         uint64_t flags)
{
  leaf[(va >> 12) & UINT64_C(0x1ff)] = leaf_pte(pa, flags);
}

static void __attribute__((naked, noinline, used, aligned(4096))) caller_entry(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "li t0, 0x40000\n"
    "li t1, 0x1111222233334444\n"
    "sd t1, 0(t0)\n"
    "li t0, 0x50000\n"
    "li t1, 0x33\n"
    "sd t1, 0(t0)\n"

    /* An invalid capability must return an error without entering the server. */
    "li a6, 2\n"
    "li a7, 0x71\n"
    "ecall\n"
    "mv s2, a0\n"

    /* Match the server's useful work with an ordinary same-domain call. */
    "li t0, 0x50000\n"
    "sd zero, 8(t0)\n"
    "csrr s3, 0xcc0\n"
    "li a0, 7\n"
    "li a1, 9\n"
    "call local_service\n"
    "csrr s4, 0xcc0\n"
    "sub s4, s4, s3\n"
    "li t0, 0x50000\n"
    "sd s4, 32(t0)\n"
    "sd zero, 8(t0)\n"

    /* The valid call transfers four argument registers and one return value. */
    "csrr s0, 0xcc0\n"
    "li a0, 7\n"
    "li a1, 9\n"
    "li a2, 0x123\n"
    "li a3, 0x456\n"
    "li a6, 1\n"
    "li a7, 0x71\n"
    "ecall\n"
    "csrr s1, 0xcc0\n"
    "sub s1, s1, s0\n"

    "li t0, 0x50000\n"
    "sd s1, 16(t0)\n"
    "li t1, 0x43\n"
    "bne a0, t1, 1f\n"
    "li t1, -1\n"
    "bne s2, t1, 2f\n"
    "ld t1, 8(t0)\n"
    "li t2, 0x5555666677778888\n"
    "bne t1, t2, 3f\n"
    "li t1, 0x40000\n"
    "ld t2, 0(t1)\n"
    "li t3, 0x1111222233334444\n"
    "bne t2, t3, 4f\n"
    /* Repeat the same protected call to expose a steady-state measurement. */
    "li t0, 0x50000\n"
    "sd zero, 8(t0)\n"
    "csrr s3, 0xcc0\n"
    "li a0, 7\n"
    "li a1, 9\n"
    "li a2, 0x123\n"
    "li a3, 0x456\n"
    "li a6, 1\n"
    "li a7, 0x71\n"
    "ecall\n"
    "csrr s4, 0xcc0\n"
    "sub s4, s4, s3\n"
    "li t0, 0x50000\n"
    "sd s4, 40(t0)\n"
    "li t1, 0x43\n"
    "bne a0, t1, 6f\n"
    "ld t1, 8(t0)\n"
    "li t2, 0x5555666677778888\n"
    "bne t1, t2, 7f\n"
    "li t1, 1\n"
    "sd t1, 24(t0)\n"
    "j 8f\n"
    "1: li t1, 0x101\nsd t1, 24(t0)\nj 8f\n"
    "2: li t1, 0x102\nsd t1, 24(t0)\nj 8f\n"
    "3: li t1, 0x103\nsd t1, 24(t0)\nj 8f\n"
    "4: li t1, 0x104\nsd t1, 24(t0)\n"
    "j 8f\n"
    "6: li t1, 0x106\nsd t1, 24(t0)\nj 8f\n"
    "7: li t1, 0x107\nsd t1, 24(t0)\n"
    "8:\n"
    "li a7, 0x73\n"
    "ecall\n"
    "9: j 9b\n"
    /* Keep the direct-call control in the caller's one mapped code page. */
    "local_service:\n"
    "li t0, 0x40000\n"
    "li t1, 0x1111222233334444\n"
    "sd t1, 0(t0)\n"
    "li t0, 0x50000\n"
    "ld t1, 0(t0)\n"
    "add a0, a0, a1\n"
    "add a0, a0, t1\n"
    "li t1, 0x5555666677778888\n"
    "sd t1, 8(t0)\n"
    "jalr zero, 0(ra)\n"
    ".option pop\n"
  );
}

static void __attribute__((naked, noinline, used, aligned(4096))) server_entry(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    /* PRIVATE_VA names a different physical page in the server domain. */
    "li t0, 0x40000\n"
    "li t1, 0x5555666677778888\n"
    "sd t1, 0(t0)\n"
    "li t0, 0x50000\n"
    "ld t1, 0(t0)\n"
    "add a0, a0, a1\n"
    "add a0, a0, t1\n"
    "li t1, 0x5555666677778888\n"
    "sd t1, 8(t0)\n"
    "li a7, 0x72\n"
    "ecall\n"
    "1: j 1b\n"
    ".option pop\n"
  );
}

static void __attribute__((used, noinline, noreturn)) machine_finish(void)
{
  const uint64_t verdict = shared_page[3];
  const int pass = verdict == 1
                   && caller_private[0] == CALLER_PRIVATE_VALUE
                   && server_private[0] == SERVER_PRIVATE_VALUE
                   && shared_page[1] == SERVER_PRIVATE_VALUE
                   && call_count == 2
                   && current_domain == 0
                   && return_active == 0
                   && unexpected_mcause == 0;
  if (pass) {
    bp_print_string("Ordinary same-domain call cycles: ");
    bp_hprint_uint64(shared_page[4]);
    bp_print_string("\nProtected RPC first call+reply cycles: ");
    bp_hprint_uint64(shared_page[2]);
    bp_print_string("\nProtected RPC repeat call+reply cycles: ");
    bp_hprint_uint64(shared_page[5]);
    bp_print_string("\n[BSG-PASS] protected RPC capability, isolation and return\n");
    bp_finish(0);
  }

  bp_print_string("[BSG-FAIL] protected RPC reference\nverdict: ");
  bp_hprint_uint64(verdict);
  bp_print_string("\ncaller private: ");
  bp_hprint_uint64(caller_private[0]);
  bp_print_string("\nserver private: ");
  bp_hprint_uint64(server_private[0]);
  bp_print_string("\ncall count: ");
  bp_hprint_uint64(call_count);
  bp_print_string("\nunexpected mcause: ");
  bp_hprint_uint64(unexpected_mcause);
  bp_print_string("\n");
  bp_finish(1);
  for (;;)
    ;
}

static void __attribute__((naked, aligned(4))) machine_trap_entry(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "csrr t0, mcause\n"
    "li t1, 8\n"
    "bne t0, t1, 9f\n"
    "li t0, 0x71\n"
    "beq a7, t0, 1f\n"
    "li t0, 0x72\n"
    "beq a7, t0, 4f\n"
    "li t0, 0x73\n"
    "beq a7, t0, 8f\n"
    "j 9f\n"

    /* pcall(cap, a0..a3): validate the sole capability and save the caller. */
    "1:\n"
    "la t0, current_domain\n"
    "ld t1, 0(t0)\n"
    "bnez t1, 3f\n"
    "li t1, 1\n"
    "bne a6, t1, 3f\n"
    "la t0, return_active\n"
    "ld t1, 0(t0)\n"
    "bnez t1, 3f\n"
    "la t0, caller_state\n"
    "sd ra, 0(t0)\nsd sp, 8(t0)\nsd gp, 16(t0)\nsd tp, 24(t0)\n"
    "sd s0, 32(t0)\nsd s1, 40(t0)\nsd s2, 48(t0)\nsd s3, 56(t0)\n"
    "sd s4, 64(t0)\nsd s5, 72(t0)\nsd s6, 80(t0)\nsd s7, 88(t0)\n"
    "sd s8, 96(t0)\nsd s9, 104(t0)\nsd s10, 112(t0)\nsd s11, 120(t0)\n"
    "csrr t1, mepc\naddi t1, t1, 4\nsd t1, 128(t0)\n"
    "csrr t1, satp\nsd t1, 136(t0)\n"
    "la t0, return_active\nli t1, 1\nsd t1, 0(t0)\n"
    "la t0, current_domain\nsd t1, 0(t0)\n"
    "la t0, call_count\nld t2, 0(t0)\naddi t2, t2, 1\nsd t2, 0(t0)\n"
    "la t0, server_satp_value\nld t1, 0(t0)\ncsrw satp, t1\n"
#if RPC_FLUSH_ON_SWITCH
    "sfence.vma\n"
#endif
    "li t0, 0x20000\ncsrw mepc, t0\n"
    "li sp, 0x60ff0\n"
    /* Clear non-argument state so the server cannot observe caller secrets. */
    "li ra, 0\nli gp, 0\nli tp, 0\n"
    "li s0, 0\nli s1, 0\nli s2, 0\nli s3, 0\nli s4, 0\nli s5, 0\n"
    "li s6, 0\nli s7, 0\nli s8, 0\nli s9, 0\nli s10, 0\nli s11, 0\n"
    "li a4, 0\nli a5, 0\nli a6, 0\nli a7, 0\n"
    "li t1, 0\nli t2, 0\nli t3, 0\nli t4, 0\nli t5, 0\nli t6, 0\nli t0, 0\n"
    "mret\n"

    /* Invalid calls return locally and never expose a target entry point. */
    "3:\n"
    "li a0, -1\n"
    "csrr t0, mepc\naddi t0, t0, 4\ncsrw mepc, t0\n"
    "mret\n"

    /* preturn(a0): accept only the active server and protected continuation. */
    "4:\n"
    "la t0, current_domain\nld t1, 0(t0)\nli t2, 1\nbne t1, t2, 9f\n"
    "la t0, return_active\nld t1, 0(t0)\nbeqz t1, 9f\n"
    "la t0, caller_state\n"
    "ld t1, 136(t0)\ncsrw satp, t1\n"
#if RPC_FLUSH_ON_SWITCH
    "sfence.vma\n"
#endif
    "ld t1, 128(t0)\ncsrw mepc, t1\n"
    "ld ra, 0(t0)\nld sp, 8(t0)\nld gp, 16(t0)\nld tp, 24(t0)\n"
    "ld s0, 32(t0)\nld s1, 40(t0)\nld s2, 48(t0)\nld s3, 56(t0)\n"
    "ld s4, 64(t0)\nld s5, 72(t0)\nld s6, 80(t0)\nld s7, 88(t0)\n"
    "ld s8, 96(t0)\nld s9, 104(t0)\nld s10, 112(t0)\nld s11, 120(t0)\n"
    "la t0, return_active\nsd zero, 0(t0)\n"
    "la t0, current_domain\nsd zero, 0(t0)\n"
    /* a0 is the sole result; clear all other server-controlled caller-saved state. */
    "li a1, 0\nli a2, 0\nli a3, 0\nli a4, 0\nli a5, 0\nli a6, 0\nli a7, 0\n"
    "li t1, 0\nli t2, 0\nli t3, 0\nli t4, 0\nli t5, 0\nli t6, 0\nli t0, 0\n"
    "mret\n"

    /* The caller asks M-mode to report after all U-mode checks have completed. */
    "8:\n"
    "la t0, current_domain\nld t1, 0(t0)\nbnez t1, 9f\n"
    "csrr t0, mstatus\nli t1, 0x1800\nor t0, t0, t1\ncsrw mstatus, t0\n"
    "la t0, monitor_sp\nld sp, 0(t0)\n"
    "la t0, machine_finish\ncsrw mepc, t0\nmret\n"

    "9:\n"
    "csrr t0, mcause\nla t1, unexpected_mcause\nsd t0, 0(t1)\n"
    "csrr t0, mstatus\nli t1, 0x1800\nor t0, t0, t1\ncsrw mstatus, t0\n"
    "la t0, monitor_sp\nld sp, 0(t0)\n"
    "la t0, machine_finish\ncsrw mepc, t0\nmret\n"
    ".option pop\n"
  );
}

int main(void)
{
  const uint64_t rx = PTE_V | PTE_R | PTE_X | PTE_U | PTE_A;
  const uint64_t rw = PTE_V | PTE_R | PTE_W | PTE_U | PTE_A | PTE_D;
  uint64_t status;

#ifndef BP_FPGA_PROGRAM
  __asm__ volatile(
    "csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:"
    : : : "t0", "memory"
  );
#endif

  caller_root[0] = pointer_pte(caller_middle);
  caller_middle[0] = pointer_pte(caller_leaf);
  server_root[0] = pointer_pte(server_middle);
  server_middle[0] = pointer_pte(server_leaf);
  map_low_page(caller_leaf, CALLER_ENTRY_VA, caller_entry, rx);
  map_low_page(caller_leaf, PRIVATE_VA, caller_private, rw);
  map_low_page(caller_leaf, SHARED_VA, shared_page, rw);
  map_low_page(caller_leaf, STACK_VA, caller_stack, rw);
  map_low_page(server_leaf, SERVER_ENTRY_VA, server_entry, rx);
  map_low_page(server_leaf, PRIVATE_VA, server_private, rw);
  map_low_page(server_leaf, SHARED_VA, shared_page, rw);
  map_low_page(server_leaf, STACK_VA, server_stack, rw);

  caller_satp_value = SV39_MODE | (physical_address(caller_root) >> 12);
  server_satp_value = SV39_MODE | (UINT64_C(1) << SATP_ASID_SHIFT)
                      | (physical_address(server_root) >> 12);
  current_domain = 0;
  return_active = 0;
  call_count = 0;
  unexpected_mcause = 0;
  for (int i = 0; i < 6; ++i)
    shared_page[i] = 0;
  __asm__ volatile("mv %0, sp" : "=r"(monitor_sp));

  __asm__ volatile("csrw medeleg, zero\ncsrw mideleg, zero" ::: "memory");
  __asm__ volatile("csrw mtvec, %0" : : "r"((uint64_t)machine_trap_entry) : "memory");
  __asm__ volatile("csrw satp, %0\nsfence.vma" : : "r"(caller_satp_value) : "memory");
  __asm__ volatile("csrw mepc, %0" : : "r"(CALLER_ENTRY_VA) : "memory");
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  status &= ~MSTATUS_MPP_MASK;
  __asm__ volatile("csrw mstatus, %0" : : "r"(status) : "memory");
  __asm__ volatile("li sp, 0x60ff0\nmret" : : : "memory");
  __builtin_unreachable();
}
