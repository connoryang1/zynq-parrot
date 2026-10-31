/*
 * Exercise a tiny library service in a page table distinct from its caller.
 * A reusable client wrapper performs pcall, while a separately linked service
 * page updates server-private state and returns through protected preturn.
 */

#include <stdint.h>

#include "bp_protected_rpc.h"
#include "bp_utils.h"
#include "../sel4/include/blackparrot_rpc_abi.h"

#if BP_NUM_THREADS != 2 || (BP_NUM_CONTEXTS != 4 && BP_NUM_CONTEXTS != 10)
#error "The protected RPC library test requires two resident hardware slots"
#endif

#define MSTATUS_MPP_MASK (UINT64_C(3) << 11)
#define SV39_MODE        (UINT64_C(8) << 60)
#define SATP_ASID_SHIFT  44

#define CALLER_ENTRY_VA  UINT64_C(0x10000)
#define SERVER_ENTRY_VA  UINT64_C(0x20000)
#define PRIVATE_VA       UINT64_C(0x40000)
#define CALLER_SHARED_VA UINT64_C(0x50000)
#define STACK_VA         UINT64_C(0x60000)
#define SERVER_SHARED_VA UINT64_C(0x70000)
#define STACK_TOP_VA     (STACK_VA + UINT64_C(0xff0))

#define RPC_CAPABILITY          UINT64_C(1)
#define CALLER_PRIVATE_SENTINEL UINT64_C(0x1234)
#define SERVER_COUNTER_INITIAL UINT64_C(0x1000)
#define SERVER_COUNTER_FINAL   UINT64_C(0x1002)
#define SHARED_DATA_FIRST      UINT64_C(0x100)
#define SHARED_DATA_SECOND     UINT64_C(0x108)
#define RPC_RESULT_FIRST       UINT64_C(0x1012)
#define RPC_RESULT_SECOND      UINT64_C(0x101f)

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

extern void bp_rpc_demo_service_page(void);
extern void bp_rpc_demo_service_entry(void);

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
  status |= rpc_stage(BP_RPC_FIELD_TOKEN, RPC_CAPABILITY);
  status |= rpc_stage(BP_RPC_FIELD_CALLER_SATP, caller_satp);
  status |= rpc_stage(BP_RPC_FIELD_SERVER_SATP, server_satp);
  status |= rpc_stage(BP_RPC_FIELD_SERVER_ENTRY, server_entry);
  status |= rpc_stage(BP_RPC_FIELD_SERVER_SP, STACK_TOP_VA);
  status |= rpc_stage(BP_RPC_FIELD_SERVER_GP, 0);
  status |= rpc_stage(BP_RPC_FIELD_SERVER_TP, 0);
  status |= rpc_stage(BP_RPC_FIELD_CALLER_BADGE, UINT64_C(0x42));
  status |= rpc_stage(BP_RPC_FIELD_CONFIG, bp_rpc_config_word(4, 1, 0, 1));
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

static void __attribute__((noinline, noreturn, used, aligned(4096)))
caller_entry(void)
{
  volatile uint64_t *private_page = (volatile uint64_t *)PRIVATE_VA;
  void *shared_base = (void *)CALLER_SHARED_VA;
  volatile uint64_t *shared = (volatile uint64_t *)shared_base;
  volatile uint64_t *first_word = bp_rpc_shared_ptr(
    shared_base, 4096, SHARED_DATA_FIRST, sizeof(*first_word));
  volatile uint64_t *second_word = bp_rpc_shared_ptr(
    shared_base, 4096, SHARED_DATA_SECOND, sizeof(*second_word));
  void *invalid_word = bp_rpc_shared_ptr(shared_base, 4096, 4092, 8);

  private_page[0] = CALLER_PRIVATE_SENTINEL;
  *first_word = 10;
  *second_word = 20;
  const uint64_t first = bp_protected_rpc_call4(
    RPC_CAPABILITY, SHARED_DATA_FIRST, sizeof(*first_word), 7, 0);
  const uint64_t second = bp_protected_rpc_call4(
    RPC_CAPABILITY, SHARED_DATA_SECOND, sizeof(*second_word), 9, 0);
  const uint64_t rejected = bp_protected_rpc_call4(
    RPC_CAPABILITY, 4092, 8, 0, 0);

  shared[0] = first;
  shared[1] = second;
  shared[3] = first == RPC_RESULT_FIRST
              && second == RPC_RESULT_SECOND
              && rejected == UINT64_MAX
              && *first_word == RPC_RESULT_FIRST
              && *second_word == RPC_RESULT_SECOND
              && invalid_word == NULL
              && private_page[0] == CALLER_PRIVATE_SENTINEL;
  shared[4] = rejected;
  __asm__ volatile("ecall\n1: j 1b" : : : "memory");
  __builtin_unreachable();
}

static void __attribute__((used, noinline, noreturn)) machine_finish(void)
{
  const unsigned caller_entry_index = (CALLER_ENTRY_VA >> 12) & 0x1ff;
  const unsigned server_entry_index = (SERVER_ENTRY_VA >> 12) & 0x1ff;
  const unsigned caller_shared_index = (CALLER_SHARED_VA >> 12) & 0x1ff;
  const unsigned server_shared_index = (SERVER_SHARED_VA >> 12) & 0x1ff;
  const int page_tables_are_distinct = caller_leaf[server_entry_index] == 0
                                       && server_leaf[caller_entry_index] == 0
                                       && caller_leaf[server_shared_index] == 0
                                       && server_leaf[caller_shared_index] == 0
                                       && caller_leaf[caller_shared_index]
                                          == server_leaf[server_shared_index];
  const int pass = shared_page[0] == RPC_RESULT_FIRST
                   && shared_page[1] == RPC_RESULT_SECOND
                   && shared_page[2] == SERVER_COUNTER_FINAL
                   && shared_page[3] == 1
                   && shared_page[4] == UINT64_MAX
                   && caller_private[0] == CALLER_PRIVATE_SENTINEL
                   && server_private[0] == SERVER_COUNTER_FINAL
                   && page_tables_are_distinct
                   && unexpected_mcause == 0;

  if (pass) {
    bp_print_string("Protected library results: ");
    bp_hprint_uint64(shared_page[0]);
    bp_print_string(" / ");
    bp_hprint_uint64(shared_page[1]);
    bp_print_string("\n[BSG-PASS] protected RPC library address-space isolation\n");
    bp_finish(0);
  }

  bp_print_string("[BSG-FAIL] protected RPC library\nresults/verdict: ");
  bp_hprint_uint64(shared_page[0]);
  bp_hprint_uint64(shared_page[1]);
  bp_hprint_uint64(shared_page[3]);
  bp_print_string("\nprivate pages/server counter: ");
  bp_hprint_uint64(caller_private[0]);
  bp_hprint_uint64(server_private[0]);
  bp_hprint_uint64(shared_page[2]);
  bp_print_string("\npage-table separation/trap: ");
  bp_hprint_uint64(page_tables_are_distinct);
  bp_hprint_uint64(unexpected_mcause);
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
    "csrr t0, mstatus\nli t1, 0x1800\nor t0, t0, t1\n"
    "csrw mstatus, t0\n"
    "la t0, monitor_sp\nld sp, 0(t0)\n"
    "la t0, machine_finish\ncsrw mepc, t0\nmret\n"
    "1: la t1, unexpected_mcause\nsd t0, 0(t1)\n"
    "csrr t0, mepc\nla t1, unexpected_mepc\nsd t0, 0(t1)\n"
    "csrr t0, mtval\nla t1, unexpected_mtval\nsd t0, 0(t1)\n"
    "csrr t0, mstatus\nli t1, 0x1800\nor t0, t0, t1\n"
    "csrw mstatus, t0\n"
    "la t0, monitor_sp\nld sp, 0(t0)\n"
    "la t0, machine_finish\ncsrw mepc, t0\nmret\n"
    ".option pop\n");
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
    : : : "t0", "memory");
#endif

  const uint64_t service_page = physical_address(bp_rpc_demo_service_page);
  const uint64_t service_offset = physical_address(bp_rpc_demo_service_entry)
                                  - service_page;
  if (service_offset >= 4096)
    machine_finish();

  caller_root[0] = pointer_pte(caller_middle);
  caller_middle[0] = pointer_pte(caller_leaf);
  server_root[0] = pointer_pte(server_middle);
  server_middle[0] = pointer_pte(server_leaf);
  map_low_page(caller_leaf, CALLER_ENTRY_VA, caller_entry, rx);
  map_low_page(caller_leaf, PRIVATE_VA, caller_private, rw);
  map_low_page(caller_leaf, CALLER_SHARED_VA, shared_page, rw);
  map_low_page(caller_leaf, STACK_VA, caller_stack, rw);
  map_low_page(server_leaf, SERVER_ENTRY_VA,
               bp_rpc_demo_service_page, rx);
  map_low_page(server_leaf, PRIVATE_VA, server_private, rw);
  map_low_page(server_leaf, SERVER_SHARED_VA, shared_page, rw);
  map_low_page(server_leaf, STACK_VA, server_stack, rw);

  const uint64_t caller_satp = SV39_MODE
                               | (physical_address(caller_root) >> 12);
  server_satp_value = SV39_MODE | (UINT64_C(1) << SATP_ASID_SHIFT)
                      | (physical_address(server_root) >> 12);
  for (int i = 0; i < 9; ++i)
    shared_page[i] = 0;
  caller_private[0] = 0;
  server_private[0] = SERVER_COUNTER_INITIAL;
  unexpected_mcause = 0;
  unexpected_mepc = 0;
  unexpected_mtval = 0;
  __asm__ volatile("mv %0, sp" : "=r"(monitor_sp));

  __asm__ volatile("csrw medeleg, zero\ncsrw mideleg, zero" ::: "memory");
  __asm__ volatile("csrw mtvec, %0" : : "r"((uint64_t)machine_trap_entry)
                   : "memory");
  seed_server_register(8, UINT64_C(0x11111));
  seed_server_register(18, UINT64_C(0x22222));

  const uint64_t service_va = SERVER_ENTRY_VA + service_offset;
  if (rpc_install_descriptor(caller_satp, server_satp_value, service_va)
      != BP_RPC_CONTROL_OK)
    machine_finish();

  __asm__ volatile("csrw satp, %0\nsfence.vma"
                   : : "r"(caller_satp) : "memory");
  __asm__ volatile("csrw mepc, %0" : : "r"(CALLER_ENTRY_VA) : "memory");
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  status &= ~MSTATUS_MPP_MASK;
  __asm__ volatile("csrw mstatus, %0" : : "r"(status) : "memory");
  __asm__ volatile("li sp, 0x60ff0\nmret" : : : "memory");
  __builtin_unreachable();
}
