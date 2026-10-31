/* Validate the machine-only version-1 protected-RPC descriptor controller. */

#include <stdint.h>

#include "bp_utils.h"
#include "../sel4/include/blackparrot_rpc_abi.h"

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

static uint64_t rpc_token_command(bp_rpc_control_command_t command,
                                  uint32_t slot, uint64_t token)
{
  rpc_data_write(token);
  return rpc_control(bp_rpc_control_word(command, BP_RPC_FIELD_TOKEN, slot));
}

static uint64_t rpc_stage_descriptor(uint64_t token, uint64_t caller_satp,
                                     uint64_t server_satp)
{
  uint64_t status = 0;
  status |= rpc_stage(BP_RPC_FIELD_TOKEN, token);
  status |= rpc_stage(BP_RPC_FIELD_CALLER_SATP, caller_satp);
  status |= rpc_stage(BP_RPC_FIELD_SERVER_SATP, server_satp);
  status |= rpc_stage(BP_RPC_FIELD_SERVER_ENTRY, UINT64_C(0x10000));
  status |= rpc_stage(BP_RPC_FIELD_SERVER_SP, UINT64_C(0x20ff0));
  status |= rpc_stage(BP_RPC_FIELD_SERVER_GP, 0);
  status |= rpc_stage(BP_RPC_FIELD_SERVER_TP, 0);
  status |= rpc_stage(BP_RPC_FIELD_CALLER_BADGE, UINT64_C(0x55));
  status |= rpc_stage(BP_RPC_FIELD_CONFIG, bp_rpc_config_word(4, 4, 0, 1));
  return status;
}

static void fail(const char *step, uint64_t actual, uint64_t expected)
{
  bp_print_string("[BSG-FAIL] protected RPC descriptor control: ");
  bp_print_string(step);
  bp_print_string("\nactual: ");
  bp_hprint_uint64(actual);
  bp_print_string(" expected: ");
  bp_hprint_uint64(expected);
  bp_print_string("\n");
  bp_finish(1);
}

#define EXPECT(step, expression, expected) do {             \
  uint64_t actual_ = (expression);                          \
  if (actual_ != (uint64_t)(expected))                      \
    fail((step), actual_, (uint64_t)(expected));            \
} while (0)

int main(void)
{
#ifndef BP_FPGA_PROGRAM
  /* The simulator CRT enters debug mode; descriptor CSRs are M-mode-only. */
  __asm__ volatile(
    "csrr t0, dcsr\n"
    "ori t0, t0, 3\n"
    "csrw dcsr, t0\n"
    "la t0, 1f\n"
    "csrw dpc, t0\n"
    "dret\n"
    "1:"
    : : : "t0", "memory");
#endif

  const uint64_t token = UINT64_C(0x7351c0de12345678);
  const uint64_t caller_satp = UINT64_C(0x8000000000000100);
  const uint64_t server_satp = UINT64_C(0x8000100000000200);

  EXPECT("incomplete commit",
         rpc_control(bp_rpc_control_word(BP_RPC_CONTROL_COMMIT,
                                         BP_RPC_FIELD_TOKEN, 0)),
         BP_RPC_CONTROL_INVALID);
  EXPECT("unsupported slot",
         rpc_token_command(BP_RPC_CONTROL_READ_STATUS, 1, token),
         BP_RPC_CONTROL_UNSUPPORTED);
  EXPECT("reserved control bits",
         rpc_control(bp_rpc_control_word(BP_RPC_CONTROL_STAGE,
                                         BP_RPC_FIELD_TOKEN, 0)
                     | (UINT64_C(1) << 32)),
         BP_RPC_CONTROL_INVALID);

  EXPECT("stage structurally invalid descriptor",
         rpc_stage_descriptor(token, caller_satp, caller_satp),
         BP_RPC_CONTROL_OK);
  EXPECT("reject equal address spaces",
         rpc_control(bp_rpc_control_word(BP_RPC_CONTROL_COMMIT,
                                         BP_RPC_FIELD_TOKEN, 0)),
         BP_RPC_CONTROL_INVALID);
  EXPECT("stage valid descriptor",
         rpc_stage_descriptor(token, caller_satp, server_satp),
         BP_RPC_CONTROL_OK);
  EXPECT("atomic commit",
         rpc_control(bp_rpc_control_word(BP_RPC_CONTROL_COMMIT,
                                         BP_RPC_FIELD_TOKEN, 0)),
         BP_RPC_CONTROL_OK);

  EXPECT("query live token",
         rpc_token_command(BP_RPC_CONTROL_READ_STATUS, 0, token),
         BP_RPC_CONTROL_OK);
  EXPECT("query wrong token",
         rpc_token_command(BP_RPC_CONTROL_READ_STATUS, 0, token + 1),
         BP_RPC_CONTROL_STALE);
  EXPECT("revoke wrong token",
         rpc_token_command(BP_RPC_CONTROL_REVOKE, 0, token + 1),
         BP_RPC_CONTROL_STALE);
  EXPECT("revoke live token",
         rpc_token_command(BP_RPC_CONTROL_REVOKE, 0, token),
         BP_RPC_CONTROL_OK);
  EXPECT("query revoked token",
         rpc_token_command(BP_RPC_CONTROL_READ_STATUS, 0, token),
         BP_RPC_CONTROL_STALE);

  bp_print_string("[BSG-PASS] atomic protected RPC descriptor control\n");
  bp_finish(0);
  return 0;
}
