/*
 * Validate and measure the atomic hardware-protected RPC transition. Two resident U-mode contexts use distinct Sv39
 * address spaces; pcall carries four arguments plus request metadata and
 * preturn carries four replies plus outcome metadata;
 * an atomically published M-mode descriptor binds token 1 to the fixed
 * context-0/context-1 transition.
 */

#include <stdint.h>

#include "bp_utils.h"
#include "../sel4/include/blackparrot_rpc_abi.h"

#if BP_NUM_THREADS != 2 || (BP_NUM_CONTEXTS != 4 && BP_NUM_CONTEXTS != 10)
#error "The protected RPC test requires two resident slots and four or ten logical contexts"
#endif

#define MSTATUS_MPP_MASK (UINT64_C(3) << 11)
#define MSTATUS_MPP_M    (UINT64_C(3) << 11)
#define SV39_MODE        (UINT64_C(8) << 60)
#define SATP_ASID_SHIFT  44

#define CALLER_ENTRY_VA  UINT64_C(0x10000)
#define SERVER_ENTRY_VA  UINT64_C(0x20000)
#define PRIVATE_VA       UINT64_C(0x40000)
#define SHARED_VA        UINT64_C(0x50000)
#define STACK_VA         UINT64_C(0x60000)
#define STACK_TOP_VA     (STACK_VA + UINT64_C(0xff0))

#define CALLER_PRIVATE_VALUE UINT64_C(0x1111222233334444)
#define SERVER_PRIVATE_VALUE UINT64_C(0x5555666677778888)
#define SHARED_INPUT         UINT64_C(0x33)
#define RPC_RESULT_FIRST     UINT64_C(0x2788)
#define RPC_RESULT_SECOND    UINT64_C(0x2278)

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

static uint64_t server_satp_value __attribute__((used));
static uint64_t monitor_sp __attribute__((used));
static volatile uint64_t unexpected_mcause;
static volatile uint64_t unexpected_mepc;
static volatile uint64_t unexpected_mtval;
extern void server_service(void);

static inline void rpc_data_write(uint64_t value)
{
  __asm__ volatile("csrw 0x7c3, %0" : : "r"(value) : "memory");
}

static void seed_server_register(unsigned reg, uint64_t value)
{
  const unsigned context_width = BP_NUM_CONTEXTS <= 4 ? 2 : 4;
  const uint64_t encoded = (value & ((UINT64_C(1) << 39) - 1))
                           | (UINT64_C(1) << 39)
                           | ((uint64_t)reg << (39 + context_width));
  __asm__ volatile("csrw 0x802, %0" : : "r"(encoded) : "memory");
}

static uint64_t rpc_stage(bp_rpc_descriptor_field_t field, uint64_t value)
{
  uint64_t status;
  rpc_data_write(value);
  const uint64_t control =
    bp_rpc_control_word(BP_RPC_CONTROL_STAGE, field, 0);
  __asm__ volatile("csrw 0x7c4, %1\ncsrr %0, 0x7c4"
                   : "=r"(status) : "r"(control) : "memory");
  return status;
}

static uint64_t rpc_control(uint64_t control)
{
  uint64_t status;
  __asm__ volatile("csrw 0x7c4, %1\ncsrr %0, 0x7c4"
                   : "=r"(status) : "r"(control) : "memory");
  return status;
}

static uint64_t rpc_install_descriptor(uint64_t caller_satp,
                                       uint64_t server_satp,
                                       uint64_t server_entry)
{
  uint64_t status = 0;
  status |= rpc_stage(BP_RPC_FIELD_TOKEN, 1);
  status |= rpc_stage(BP_RPC_FIELD_CALLER_SATP, caller_satp);
  status |= rpc_stage(BP_RPC_FIELD_SERVER_SATP, server_satp);
  status |= rpc_stage(BP_RPC_FIELD_SERVER_ENTRY, server_entry);
  status |= rpc_stage(BP_RPC_FIELD_SERVER_SP, STACK_TOP_VA);
  status |= rpc_stage(BP_RPC_FIELD_SERVER_GP, 0);
  status |= rpc_stage(BP_RPC_FIELD_SERVER_TP, 0);
  status |= rpc_stage(BP_RPC_FIELD_CALLER_BADGE, UINT64_C(0x99));
  status |= rpc_stage(BP_RPC_FIELD_CONFIG, bp_rpc_config_word(4, 4, 0, 1));
  if (status != BP_RPC_CONTROL_OK)
    return status;
  for (unsigned component = 0; component < BP_RPC_PREPARE_COMPONENTS;
       component++) {
    status = rpc_control(bp_rpc_prepare_word(
      (bp_rpc_prepare_component_t)component, 0));
    if (status != BP_RPC_CONTROL_OK)
      return status;
  }
  return rpc_control(bp_rpc_control_word(BP_RPC_CONTROL_COMMIT,
                                          BP_RPC_FIELD_TOKEN, 0));
}

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
    /* Initialize the caller-private and explicitly shared state. */
    "li t0, 0x40000\n"
    "li t1, 0x1111222233334444\n"
    "sd t1, 0(t0)\n"
    "li t0, 0x50000\n"
    "li t1, 0x33\n"
    "sd t1, 0(t0)\n"

    /* Descriptor publication locks the legacy NPC/switch interface. Point at
     * an unauthorized PC and require both calls to enter the fixed entry. */
    "li t0, 0x4000008000020100\ncsrw 0x801, t0\n"
    /* Descriptor installation locks the legacy U-mode handoff path. */
    "csrwi 0x800, 1\ncsrr t0, 0x800\nbnez t0, 7f\n"
    /* M-mode seeded nonzero cache-service and miss-trace state before the
     * descriptor was installed. Locked U mode must observe only zero. */
    "csrr t0, 0x803\nbnez t0, 7f\n"
    "csrr t0, 0x804\nbnez t0, 7f\n"
    "csrr t0, 0x805\nbnez t0, 7f\n"
    "csrr t0, 0x807\nbnez t0, 7f\n"
    /* Invalid call and return operands must retire locally. */
    "li a0, 0x55\nli a5, 3\nli a4, 2\ncsrrw a4, 0x808, a4\n"
    "li t0, 1\nbne a4, t0, 7f\n"
    "li t0, 0x55\nbne a0, t0, 7f\n"
    "li t0, 3\nbne a5, t0, 7f\n"
    "csrw 0x809, a0\n"
    "csrr t0, 0x800\nbnez t0, 7f\n"

    /* Call the same timed direct helper twice so the repeat is truly warm. */
    "li a0, 7\nli a1, 9\nli a2, 0x123\nli a3, 0x456\n"
    "jal s7, direct_measure\n"
    "li t0, 0x50000\nsd a4, 32(t0)\n"
    "li t1, 0x2788\nbne a0, t1, 1f\n"
    "li a0, 11\nli a1, 13\nli a2, 0x222\nli a3, 0x333\n"
    "jal s7, direct_measure\n"
    "li t0, 0x50000\nsd a4, 40(t0)\n"
    "li t1, 0x2278\nbne a0, t1, 2f\n"

    /* The protected helper times one atomic pcall/preturn round trip. */
    "li a0, 7\nli a1, 9\nli a2, 0x123\nli a3, 0x456\n"
    "li a4, 1\n"
    "jal s7, protected_measure\n"
    "li t0, 0x50000\nsd a4, 48(t0)\n"
    "li t1, 0x2788\nbne a0, t1, 3f\n"
    "li t1, 18\nbne a1, t1, 3f\n"
    "li t1, 0x48c\nbne a2, t1, 3f\n"
    "li t1, 0x22b0\nbne a3, t1, 3f\n"
    "li t1, 4\nbne a5, t1, 3f\n"

    /* Repeat through the same helper and already initialized domains. */
    "li a0, 11\nli a1, 13\nli a2, 0x222\nli a3, 0x333\n"
    "li a4, 1\n"
    "jal s7, protected_measure\n"
    "li t0, 0x50000\nsd a4, 56(t0)\n"
    "li t1, 0x2278\nbne a0, t1, 4f\n"
    "ld t1, 16(t0)\n"
    "li t2, 0x5555666677778888\n"
    "bne t1, t2, 5f\n"
    "li t1, 0x40000\nld t2, 0(t1)\n"
    "li t3, 0x1111222233334444\n"
    "bne t2, t3, 6f\n"
    "li t1, 1\nsd t1, 24(t0)\nj 8f\n"
    "1: li t1, 0x101\nsd t1, 24(t0)\nj 8f\n"
    "2: li t1, 0x102\nsd t1, 24(t0)\nj 8f\n"
    "3: li t1, 0x103\nsd t1, 24(t0)\nj 8f\n"
    "4: li t1, 0x104\nsd t1, 24(t0)\nj 8f\n"
    "5: li t1, 0x105\nsd t1, 24(t0)\nj 8f\n"
    "6: li t1, 0x106\nsd t1, 24(t0)\nj 8f\n"
    "7: li t0, 0x50000\nli t1, 0x107\nsd t1, 24(t0)\n"
    /* Report through the architectural U-to-M trap path.  The protected
     * descriptor intentionally leaves no legacy U-mode switch available. */
    "8: ecall\n9: j 9b\n"

    /* Timed helpers use s7 as their caller link; the direct helper uses s6
     * for its internal service link so no stack traffic distorts the match. */
    "direct_measure:\n"
    "csrr s0, 0xcc0\njal s6, local_service\ncsrr s1, 0xcc0\n"
    "sub a4, s1, s0\njalr zero, 0(s7)\n"

    "protected_measure:\n"
    "csrr s0, 0xcc0\n"
    "li a5, 4\ncsrrw a4, 0x808, a4\nbnez a4, 1f\n"
    "csrr s1, 0xcc0\nsub a4, s1, s0\njalr zero, 0(s7)\n"
    "1: li a0, -1\njalr zero, 0(s7)\n"

    /* Same memory operations and arithmetic as the server body. */
    "local_service:\n"
    "li t0, 0x40000\nli t1, 0x1111222233334444\nsd t1, 0(t0)\n"
    "li t0, 0x50000\nld t1, 0(t0)\n"
    "slli a1, a1, 1\nslli a2, a2, 2\nslli a3, a3, 3\n"
    "add a0, a0, a1\nadd a0, a0, a2\nadd a0, a0, a3\nadd a0, a0, t1\n"
    "li t1, 0x1111222233334444\nsd t1, 8(t0)\n"
    "jalr zero, 0(s6)\n"
    ".option pop\n"
  );
}

static void __attribute__((naked, noinline, used, aligned(4096))) server_entry(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    /* Every protected entry carries the fixed badge and four atomically
     * installed arguments. s0 and s2 were deliberately dirtied before
     * preparation and must have been scrubbed across both GPR lines. */
    ".global server_service\nserver_service:\n"
    "1: bnez s0, 2f\nbnez s2, 2f\n"
    "li t2, 0x99\nbne s1, t2, 2f\n"
    "li t2, 4\nbeq a5, t2, 3f\n"
    "2: "
    "li a0, -2\nli a1, 0\nli a2, 0\nli a3, 0\nli a5, 4\n"
    "csrw 0x809, a0\n2: j 2b\n"
    "3: li t0, 0x40000\n"
    "li t1, 0x5555666677778888\nsd t1, 0(t0)\n"
    "li t0, 0x50000\nld t1, 0(t0)\n"
    "slli a1, a1, 1\nslli a2, a2, 2\nslli a3, a3, 3\n"
    "add a0, a0, a1\nadd a0, a0, a2\nadd a0, a0, a3\nadd a0, a0, t1\n"
    "li t1, 0x5555666677778888\nsd t1, 16(t0)\n"
    /* Hardware copies a0-a3 plus the reply length/status metadata in a5 and
     * consumes the protected continuation. */
    "li a5, 4\n"
    "csrw 0x809, a0\n"
    /* Sequential instructions are unreachable architecturally. A self-loop
     * makes any stale post-return frontend packet fail instead of recovering. */
    ".rept 8\nnop\n.endr\n4: j 4b\n"
    ".option pop\n"
  );
}

static void __attribute__((used, noinline, noreturn)) machine_finish(void)
{
  const int pass = shared_page[3] == 1
                   && shared_page[1] == CALLER_PRIVATE_VALUE
                   && shared_page[2] == SERVER_PRIVATE_VALUE
                   && caller_private[0] == CALLER_PRIVATE_VALUE
                   && server_private[0] == SERVER_PRIVATE_VALUE
                   && unexpected_mcause == 0;
  if (pass) {
    bp_print_string("Direct call first/repeat cycles: ");
    bp_hprint_uint64(shared_page[4]);
    bp_print_string(" / ");
    bp_hprint_uint64(shared_page[5]);
    bp_print_string("\nProtected hardware RPC first/repeat cycles: ");
    bp_hprint_uint64(shared_page[6]);
    bp_print_string(" / ");
    bp_hprint_uint64(shared_page[7]);
    bp_print_string("\n[BSG-PASS] atomic protected RPC capability, fixed entry and return\n");
    bp_finish(0);
  }

  bp_print_string("[BSG-FAIL] atomic protected RPC hardware\nverdict: ");
  bp_hprint_uint64(shared_page[3]);
  bp_print_string("\nshared result: ");
  bp_hprint_uint64(shared_page[2]);
  bp_print_string("\ncaller/server private: ");
  bp_hprint_uint64(caller_private[0]);
  bp_hprint_uint64(server_private[0]);
  bp_print_string("\nunexpected mcause: ");
  bp_hprint_uint64(unexpected_mcause);
  bp_print_string(" mepc/mtval: ");
  bp_hprint_uint64(unexpected_mepc);
  bp_hprint_uint64(unexpected_mtval);
  bp_print_string("\n");
  bp_finish(1);
  for (;;)
    ;
}

static void __attribute__((naked, aligned(4))) machine_trap_entry(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "csrr t0, mcause\nli t1, 8\nbne t0, t1, 1f\n"
    "csrr t0, mstatus\nli t1, 0x1800\nor t0, t0, t1\ncsrw mstatus, t0\n"
    "la t0, monitor_sp\nld sp, 0(t0)\n"
    "la t0, machine_finish\ncsrw mepc, t0\nmret\n"
    "1: la t1, unexpected_mcause\nsd t0, 0(t1)\n"
    "csrr t0, mepc\nla t1, unexpected_mepc\nsd t0, 0(t1)\n"
    "csrr t0, mtval\nla t1, unexpected_mtval\nsd t0, 0(t1)\n"
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
  uint64_t caller_satp, status;

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

  caller_satp = SV39_MODE | (physical_address(caller_root) >> 12);
  server_satp_value = SV39_MODE | (UINT64_C(1) << SATP_ASID_SHIFT)
                      | (physical_address(server_root) >> 12);
  for (int i = 0; i < 9; ++i)
    shared_page[i] = 0;
  unexpected_mcause = 0;
  unexpected_mepc = 0;
  unexpected_mtval = 0;
  __asm__ volatile("mv %0, sp" : "=r"(monitor_sp));

  __asm__ volatile("csrw medeleg, zero\ncsrw mideleg, zero" ::: "memory");
  __asm__ volatile("csrw mtvec, %0" : : "r"((uint64_t)machine_trap_entry) : "memory");
  seed_server_register(8, UINT64_C(0x11111));
  seed_server_register(18, UINT64_C(0x22222));
  /* The descriptor controller constructs context 1 directly from the staged
   * U/Sv39 image; no legacy execution or bootstrap handoff is required. */
  {
    const uint64_t server_service_va =
      SERVER_ENTRY_VA + physical_address(server_service)
      - physical_address(server_entry);
    /* Seed observably nonzero legacy diagnostic state while M-mode access is
     * still authorized. The caller verifies the post-install read lock. */
    __asm__ volatile("li t0, 0x5a5a\ncsrw 0x803, t0\ncsrwi 0x805, 1"
                     : : : "t0", "memory");
    const uint64_t install_status =
      rpc_install_descriptor(caller_satp, server_satp_value, server_service_va);
    if (install_status != BP_RPC_CONTROL_OK) {
      bp_print_string("[BSG-FAIL] protected RPC descriptor installation\n");
      bp_hprint_uint64(install_status);
      bp_finish(1);
    }
  }
  __asm__ volatile("csrw satp, %0\nsfence.vma" : : "r"(caller_satp) : "memory");
  __asm__ volatile("csrw mepc, %0" : : "r"(CALLER_ENTRY_VA) : "memory");
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  status &= ~MSTATUS_MPP_MASK;
  __asm__ volatile("csrw mstatus, %0" : : "r"(status) : "memory");
  __asm__ volatile("li sp, 0x60ff0\nmret" : : : "memory");
  __builtin_unreachable();
}
