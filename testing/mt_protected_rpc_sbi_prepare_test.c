/* Regress protected-RPC preparation through an S-mode SBI-style trap.
 *
 * seL4 asks OpenSBI to install the inactive server context.  The direct
 * descriptor-controller test does not exercise the trap entry/return pipe
 * around CSR 0x7c4, so keep this small reproducer for that integration path.
 */

#include <stdint.h>

#include "bp_utils.h"
#include "../sel4/internal/blackparrot_rpc_abi.h"

#define MSTATUS_MPP_MASK (UINT64_C(3) << 11)
#define MSTATUS_MPP_S    (UINT64_C(1) << 11)
#define MSTATUS_MPP_M    (UINT64_C(3) << 11)

static volatile uint64_t monitor_sp;
static volatile uint64_t result[3];
static volatile uint64_t unexpected_cause;

static inline void rpc_data_write(uint64_t value)
{
  __asm__ volatile("csrw 0x7c3, %0" : : "r"(value) : "memory");
}

static inline uint64_t rpc_control(uint64_t control)
{
  uint64_t status;
  __asm__ volatile("csrw 0x7c4, %1\ncsrr %0, 0x7c4"
                   : "=r"(status) : "r"(control) : "memory");
  return status;
}

static uint64_t rpc_stage(bp_rpc_descriptor_field_t field, uint64_t value)
{
  rpc_data_write(value);
  return rpc_control(bp_rpc_control_word(BP_RPC_CONTROL_STAGE, field, 0));
}

static uint64_t stage_descriptor(void)
{
  uint64_t status = 0;
  status |= rpc_stage(BP_RPC_FIELD_TOKEN, UINT64_C(0x7351c0de12345678));
  status |= rpc_stage(BP_RPC_FIELD_CALLER_SATP, UINT64_C(0x8000000000000100));
  status |= rpc_stage(BP_RPC_FIELD_SERVER_SATP, UINT64_C(0x8000100000000200));
  status |= rpc_stage(BP_RPC_FIELD_SERVER_ENTRY, UINT64_C(0x10000));
  status |= rpc_stage(BP_RPC_FIELD_SERVER_SP, UINT64_C(0x20ff0));
  status |= rpc_stage(BP_RPC_FIELD_SERVER_GP, 0);
  status |= rpc_stage(BP_RPC_FIELD_SERVER_TP, 0);
  status |= rpc_stage(BP_RPC_FIELD_CALLER_BADGE, UINT64_C(0x55));
  status |= rpc_stage(BP_RPC_FIELD_CONFIG, bp_rpc_config_word(4, 4, 0, 1));
  return status;
}

static void __attribute__((used, noinline)) machine_finish(void)
{
  if (unexpected_cause == 0
      && result[0] == BP_RPC_CONTROL_OK
      && result[1] == BP_RPC_CONTROL_OK
      && result[2] == BP_RPC_CONTROL_OK) {
    bp_print_string("[BSG-PASS] SBI-style protected RPC preparation\n");
    bp_finish(0);
  }

  bp_print_string("[BSG-FAIL] SBI-style protected RPC preparation\n");
  bp_hprint_uint64(unexpected_cause);
  bp_hprint_uint64(result[0]);
  bp_hprint_uint64(result[1]);
  bp_hprint_uint64(result[2]);
  bp_finish(1);
  for (;;)
    ;
}

/* a7=0 performs the privileged control operation in a0.  a7=1 returns to
 * machine_finish.  Keep the producer chain immediately before CSR 0x7c4,
 * matching the shape of OpenSBI's vendor-extension handler. */
static void __attribute__((naked, aligned(4))) machine_trap_entry(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "csrr t0, mcause\nli t1, 9\nbne t0, t1, 2f\n"
    "csrr t0, mepc\naddi t0, t0, 4\ncsrw mepc, t0\n"
    "bnez a7, 1f\n"
    "li t0, 1\nslli t0, t0, 58\nor a0, a0, t0\n"
    "csrw 0x7c4, a0\ncsrr a0, 0x7c4\nmret\n"
    "1: csrr t0, mstatus\nli t1, 0x1800\nor t0, t0, t1\n"
    "csrw mstatus, t0\nla t0, monitor_sp\nld sp, 0(t0)\n"
    "la t0, machine_finish\ncsrw mepc, t0\nmret\n"
    "2: la t1, unexpected_cause\nsd t0, 0(t1)\n"
    "csrr t0, mstatus\nli t1, 0x1800\nor t0, t0, t1\n"
    "csrw mstatus, t0\nla t0, monitor_sp\nld sp, 0(t0)\n"
    "la t0, machine_finish\ncsrw mepc, t0\nmret\n"
    ".option pop\n");
}

static void __attribute__((noreturn)) supervisor_entry(void)
{
  for (uint64_t component = 0; component < 3; component++) {
    register uint64_t a0 __asm__("a0") = component << 48;
    register uint64_t a7 __asm__("a7") = 0;
    __asm__ volatile("ecall" : "+r"(a0) : "r"(a7) : "memory");
    result[component] = a0;
  }

  register uint64_t a7 __asm__("a7") = 1;
  __asm__ volatile("ecall" : : "r"(a7) : "memory");
  __builtin_unreachable();
}

int main(void)
{
  uint64_t status;

#ifndef BP_FPGA_PROGRAM
  __asm__ volatile(
    "csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:"
    : : : "t0", "memory");
#endif

  if (stage_descriptor() != BP_RPC_CONTROL_OK) {
    bp_print_string("[BSG-FAIL] SBI prepare descriptor staging\n");
    bp_finish(1);
  }

  unexpected_cause = 0;
  result[0] = result[1] = result[2] = UINT64_MAX;
  __asm__ volatile("mv %0, sp" : "=r"(monitor_sp));
  __asm__ volatile("csrw medeleg, zero\ncsrw mideleg, zero" ::: "memory");
  __asm__ volatile("csrw mtvec, %0" : : "r"((uint64_t)machine_trap_entry)
                   : "memory");
  __asm__ volatile("csrw mepc, %0" : : "r"((uint64_t)supervisor_entry)
                   : "memory");
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  status = (status & ~MSTATUS_MPP_MASK) | MSTATUS_MPP_S;
  __asm__ volatile("csrw mstatus, %0\nmret" : : "r"(status) : "memory");
  __builtin_unreachable();
}
