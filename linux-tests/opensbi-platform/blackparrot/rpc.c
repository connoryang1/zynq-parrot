/*
 * SPDX-License-Identifier: BSD-2-Clause
 *
 * BlackParrot protected-RPC control plane. This is the only firmware code
 * allowed to publish or revoke the hardware descriptor used by supervisor
 * kernels; applications never see these CSRs.
 */

#include <sbi/riscv_asm.h>
#include <sbi/sbi_ecall.h>
#include <sbi/sbi_error.h>
#include <sbi/sbi_trap.h>
#include <sbi/sbi_unpriv.h>

#include "blackparrot_rpc_abi.h"
#include "rpc.h"

static int bp_rpc_copy_descriptor(bp_rpc_descriptor_v1_t *destination,
                                  const void *source)
{
    struct sbi_trap_info trap = {0};
    uint64_t *output = (uint64_t *)destination;
    const uint64_t *input = (const uint64_t *)source;

    if (((uintptr_t)source & (sizeof(uint64_t) - 1)) != 0)
        return SBI_EINVALID_ADDR;

    for (size_t index = 0;
         index < sizeof(*destination) / sizeof(uint64_t); index++) {
        output[index] = sbi_load_u64(&input[index], &trap);
        if (trap.cause)
            return SBI_EINVALID_ADDR;
    }
    return 0;
}

static bp_rpc_control_status_t bp_rpc_status(void)
{
    return (bp_rpc_control_status_t)csr_read(BP_RPC_CSR_M_CONTROL);
}

static bp_rpc_control_status_t bp_rpc_control(uint64_t control)
{
    csr_write(BP_RPC_CSR_M_CONTROL, control);
    return bp_rpc_status();
}

static bp_rpc_control_status_t
bp_rpc_stage(uint32_t slot, bp_rpc_descriptor_field_t field, uint64_t value)
{
    csr_write(BP_RPC_CSR_M_DATA, value);
    return bp_rpc_control(
        bp_rpc_control_word(BP_RPC_CONTROL_STAGE, field, slot));
}

static int
bp_rpc_install(const bp_rpc_descriptor_v1_t *supervisor_descriptor,
               uint64_t *token, bp_rpc_control_status_t *status)
{
    bp_rpc_descriptor_v1_t descriptor;
    int error = bp_rpc_copy_descriptor(&descriptor, supervisor_descriptor);
    bp_rpc_control_status_t control_status;

    if (error) {
        *token = 0;
        *status = BP_RPC_CONTROL_INVALID;
        return error;
    }
    if (!bp_rpc_descriptor_v1_valid(&descriptor)) {
        *token = 0;
        *status = BP_RPC_CONTROL_INVALID;
        return SBI_EINVAL;
    }

    control_status = bp_rpc_stage(descriptor.slot, BP_RPC_FIELD_TOKEN,
                                  descriptor.token);
    if (control_status != BP_RPC_CONTROL_OK)
        goto control_failure;
    control_status = bp_rpc_stage(descriptor.slot, BP_RPC_FIELD_CALLER_SATP,
                                  descriptor.caller_satp);
    if (control_status != BP_RPC_CONTROL_OK)
        goto control_failure;
    control_status = bp_rpc_stage(descriptor.slot, BP_RPC_FIELD_SERVER_SATP,
                                  descriptor.server_satp);
    if (control_status != BP_RPC_CONTROL_OK)
        goto control_failure;
    control_status = bp_rpc_stage(descriptor.slot, BP_RPC_FIELD_SERVER_ENTRY,
                                  descriptor.server_entry);
    if (control_status != BP_RPC_CONTROL_OK)
        goto control_failure;
    control_status = bp_rpc_stage(descriptor.slot, BP_RPC_FIELD_SERVER_SP,
                                  descriptor.server_sp);
    if (control_status != BP_RPC_CONTROL_OK)
        goto control_failure;
    control_status = bp_rpc_stage(descriptor.slot, BP_RPC_FIELD_SERVER_GP,
                                  descriptor.server_gp);
    if (control_status != BP_RPC_CONTROL_OK)
        goto control_failure;
    control_status = bp_rpc_stage(descriptor.slot, BP_RPC_FIELD_SERVER_TP,
                                  descriptor.server_tp);
    if (control_status != BP_RPC_CONTROL_OK)
        goto control_failure;
    control_status = bp_rpc_stage(descriptor.slot, BP_RPC_FIELD_CALLER_BADGE,
                                  descriptor.caller_badge);
    if (control_status != BP_RPC_CONTROL_OK)
        goto control_failure;
    control_status = bp_rpc_stage(
        descriptor.slot, BP_RPC_FIELD_CONFIG,
        bp_rpc_config_word(descriptor.request_words, descriptor.reply_words,
                           descriptor.caller_context,
                           descriptor.server_context));
    if (control_status != BP_RPC_CONTROL_OK)
        goto control_failure;

    for (unsigned int component = 0;
         component < BP_RPC_PREPARE_COMPONENTS; component++) {
        control_status = bp_rpc_control(bp_rpc_prepare_word(
            (bp_rpc_prepare_component_t)component, descriptor.slot));
        if (control_status != BP_RPC_CONTROL_OK)
            goto control_failure;
    }

    control_status = bp_rpc_control(
        bp_rpc_control_word(BP_RPC_CONTROL_COMMIT,
                            BP_RPC_FIELD_TOKEN, descriptor.slot));

control_failure:
    *status = control_status;
    *token = *status == BP_RPC_CONTROL_OK ? descriptor.token : 0;
    return *status == BP_RPC_CONTROL_INVALID ? SBI_EINVAL : 0;
}

static bp_rpc_control_status_t bp_rpc_revoke(uint32_t slot, uint64_t token)
{
    csr_write(BP_RPC_CSR_M_DATA, token);
    return bp_rpc_control(bp_rpc_control_word(BP_RPC_CONTROL_REVOKE,
                                               BP_RPC_FIELD_TOKEN, slot));
}

static bp_rpc_control_status_t bp_rpc_query(uint32_t slot, uint64_t token)
{
    csr_write(BP_RPC_CSR_M_DATA, token);
    return bp_rpc_control(bp_rpc_control_word(BP_RPC_CONTROL_READ_STATUS,
                                               BP_RPC_FIELD_TOKEN, slot));
}

bool bp_rpc_vendor_ext_check(void)
{
    return true;
}

int bp_rpc_vendor_ext_provider(long funcid, struct sbi_trap_regs *regs,
                               struct sbi_ecall_return *out)
{
    uint64_t token = 0;
    bp_rpc_control_status_t status;

    switch (funcid) {
    case BP_RPC_SBI_INSTALL:
        {
        int error = bp_rpc_install(
            (const bp_rpc_descriptor_v1_t *)regs->a0, &token, &status);
        out->value = status == BP_RPC_CONTROL_OK ? token : status;
        return error;
        }
    case BP_RPC_SBI_REVOKE:
        status = bp_rpc_revoke((uint32_t)regs->a0, regs->a1);
        out->value = status;
        return 0;
    case BP_RPC_SBI_QUERY:
        status = bp_rpc_query((uint32_t)regs->a0, regs->a1);
        out->value = status;
        return 0;
    default:
        return SBI_ENOTSUPP;
    }
}
