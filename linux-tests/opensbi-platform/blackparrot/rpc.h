/* SPDX-License-Identifier: BSD-2-Clause */

#ifndef BLACKPARROT_OPENSBI_RPC_H
#define BLACKPARROT_OPENSBI_RPC_H

#include <sbi/sbi_types.h>

struct sbi_ecall_return;
struct sbi_trap_regs;

bool bp_rpc_vendor_ext_check(void);
int bp_rpc_vendor_ext_provider(long funcid, struct sbi_trap_regs *regs,
                               struct sbi_ecall_return *out);

#endif
