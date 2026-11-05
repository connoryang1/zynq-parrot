/* SPDX-License-Identifier: GPL-2.0-only */

#pragma once

#include <types.h>
#include <object/structures.h>

bool_t bp_rpc_is_endpoint_invocation(word_t label);
exception_t bp_rpc_decode_endpoint_invocation(word_t label, word_t length,
                                               cap_t endpoint_cap, bool_t call,
                                               word_t *buffer);
void bp_rpc_finalise_endpoint(endpoint_t *endpoint);
void bp_rpc_finalise_tcb(tcb_t *tcb);
void bp_rpc_tcb_vspace_change(tcb_t *tcb);
void bp_rpc_revoke_asid(asid_t asid);
void bp_rpc_revoke_asid_pool(asid_t asid_base);
