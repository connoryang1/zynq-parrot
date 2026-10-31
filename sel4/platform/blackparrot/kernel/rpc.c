/* SPDX-License-Identifier: GPL-2.0-only */

#include <api/syscall.h>
#include <arch/machine.h>
#include <kernel/vspace.h>
#include <model/statedata.h>
#include <object/endpoint.h>
#include <object/tcb.h>
#include <plat/machine/blackparrot_rpc_abi.h>
#include <plat/machine/rpc.h>

/* BlackParrot reports mvendorid zero, selecting the first SBI vendor ID. */
#define BP_RPC_SBI_EXTENSION_ID BP_RPC_SBI_VENDOR_BASE

typedef struct bp_rpc_sbi_ret {
    long error;
    long value;
} bp_rpc_sbi_ret_t;

typedef struct bp_rpc_binding {
    endpoint_t *endpoint;
    tcb_t *caller;
    tcb_t *server;
    asid_t caller_asid;
    asid_t server_asid;
    word_t token;
} bp_rpc_binding_t;

static bp_rpc_binding_t bp_rpc_binding;
static word_t bp_rpc_generation;

static bp_rpc_sbi_ret_t bp_rpc_sbi_call(word_t operation, word_t arg0,
                                        word_t arg1)
{
    register word_t a0 asm("a0") = arg0;
    register word_t a1 asm("a1") = arg1;
    register word_t a6 asm("a6") = operation;
    register word_t a7 asm("a7") = BP_RPC_SBI_EXTENSION_ID;

    asm volatile("ecall"
                 : "+r"(a0), "+r"(a1)
                 : "r"(a6), "r"(a7)
                 : "memory");
    return (bp_rpc_sbi_ret_t) {
        .error = (long)a0,
        .value = (long)a1,
    };
}

static bool_t bp_rpc_tcb_satp(tcb_t *tcb, word_t *satp_value,
                              asid_t *asid_value, pte_t **root_value)
{
    cap_t root_cap = TCB_PTR_CTE_PTR(tcb, tcbVTable)->cap;
    if (cap_get_capType(root_cap) != cap_page_table_cap
        || !cap_page_table_cap_get_capPTIsMapped(root_cap)) {
        return false;
    }

    asid_t asid = cap_page_table_cap_get_capPTMappedASID(root_cap);
    if (asid == asidInvalid) {
        return false;
    }
    pte_t *root = PTE_PTR(cap_page_table_cap_get_capPTBasePtr(root_cap));
    satp_t satp = satp_new(SATP_MODE, asid,
                           addrFromPPtr(root) >> seL4_PageBits);
    *satp_value = satp.words[0];
    *asid_value = asid;
    if (root_value != NULL) {
        *root_value = root;
    }
    return true;
}

static bool_t bp_rpc_user_mapping(pte_t *root, word_t address,
                                  bool_t executable, bool_t writable)
{
    lookupPTSlot_ret_t lookup = lookupPTSlot(root, address);
    pte_t *pte = lookup.ptSlot;
    bool_t leaf = pte_ptr_get_read(pte) || pte_ptr_get_write(pte)
                  || pte_ptr_get_execute(pte);
    return pte_ptr_get_valid(pte) && leaf && pte_ptr_get_user(pte)
           && (!executable || pte_ptr_get_execute(pte))
           && (!writable || pte_ptr_get_write(pte));
}

static void bp_rpc_reply_word(word_t value)
{
    tcb_t *thread = NODE_STATE(ksCurThread);
    word_t *ipc_buffer = lookupIPCBuffer(true, thread);
    setRegister(thread, badgeRegister, 0);
    unsigned int length = setMR(thread, ipc_buffer, 0, value);
    setRegister(thread, msgInfoRegister, wordFromMessageInfo(
                    seL4_MessageInfo_new(0, 0, 0, length)));
    setThreadState(thread, ThreadState_Running);
}

static exception_t bp_rpc_error(word_t type)
{
    current_syscall_error.type = type;
    return EXCEPTION_SYSCALL_ERROR;
}

static void bp_rpc_revoke(void)
{
    if (bp_rpc_binding.token == 0) {
        return;
    }
    bp_rpc_sbi_ret_t result = bp_rpc_sbi_call(
        BP_RPC_SBI_REVOKE, 0, bp_rpc_binding.token);
    if (result.error != 0 || result.value != BP_RPC_CONTROL_OK) {
        fail("BlackParrot protected RPC revocation invariant failed");
    }
    bp_rpc_binding = (bp_rpc_binding_t) {0};
}

static exception_t bp_rpc_bind(word_t length, cap_t endpoint_cap,
                               word_t *buffer)
{
    if (length < BP_RPC_SEL4_BIND_ARGUMENTS
        || current_extra_caps.excaprefs[0] == NULL) {
        return bp_rpc_error(seL4_TruncatedMessage);
    }
    cap_t server_cap = current_extra_caps.excaprefs[0]->cap;
    if (cap_get_capType(server_cap) != cap_thread_cap) {
        current_syscall_error.invalidCapNumber = 1;
        return bp_rpc_error(seL4_InvalidCapability);
    }
    if (bp_rpc_binding.token != 0) {
        return bp_rpc_error(seL4_DeleteFirst);
    }

    endpoint_t *endpoint = EP_PTR(cap_endpoint_cap_get_capEPPtr(endpoint_cap));
    tcb_t *caller = NODE_STATE(ksCurThread);
    tcb_t *server = TCB_PTR(cap_thread_cap_get_capTCBPtr(server_cap));
    tcb_queue_t queue = ep_ptr_get_queue(endpoint);
    if (endpoint_ptr_get_state(endpoint) != EPState_Recv
        || queue.head != server || queue.end != server
        || thread_state_get_tsType(server->tcbState)
           != ThreadState_BlockedOnReceive
        || EP_PTR(thread_state_get_blockingObject(server->tcbState))
           != endpoint) {
        return bp_rpc_error(seL4_IllegalOperation);
    }

    word_t caller_satp, server_satp;
    asid_t caller_asid, server_asid;
    pte_t *server_root;
    if (!bp_rpc_tcb_satp(caller, &caller_satp, &caller_asid, NULL)
        || !bp_rpc_tcb_satp(server, &server_satp, &server_asid, &server_root)
        || caller_satp == server_satp) {
        return bp_rpc_error(seL4_IllegalOperation);
    }

    word_t counts = getSyscallArg(4, buffer);
    uint8_t request_words = counts;
    uint8_t reply_words = counts >> 8;
    if ((counts >> 16) != 0 || request_words > BP_RPC_MAX_WORDS
        || reply_words > BP_RPC_MAX_WORDS) {
        current_syscall_error.invalidArgumentNumber = 4;
        return bp_rpc_error(seL4_InvalidArgument);
    }

    if (++bp_rpc_generation == 0) {
        bp_rpc_generation++;
    }
    bp_rpc_descriptor_v1_t descriptor = {
        .version = BP_RPC_ABI_VERSION,
        .size = BP_RPC_DESCRIPTOR_V1_SIZE,
        .slot = 0,
        .request_words = request_words,
        .reply_words = reply_words,
        .token = bp_rpc_generation,
        .caller_satp = caller_satp,
        .server_satp = server_satp,
        .server_entry = getSyscallArg(0, buffer),
        .server_sp = getSyscallArg(1, buffer),
        .server_gp = getSyscallArg(2, buffer),
        .server_tp = getSyscallArg(3, buffer),
        .caller_badge = cap_endpoint_cap_get_capEPBadge(endpoint_cap),
        .caller_context = 0,
        .server_context = 1,
    };
    if (!bp_rpc_descriptor_v1_valid(&descriptor)) {
        return bp_rpc_error(seL4_InvalidArgument);
    }
    if (!bp_rpc_user_mapping(server_root, descriptor.server_entry,
                             true, false)
        || !bp_rpc_user_mapping(server_root, descriptor.server_sp - 1,
                                false, true)) {
        return bp_rpc_error(seL4_FailedLookup);
    }

    bp_rpc_sbi_ret_t result = bp_rpc_sbi_call(
        BP_RPC_SBI_INSTALL, (word_t)&descriptor, 0);
    if (result.error != 0 || (word_t)result.value != descriptor.token) {
        return bp_rpc_error(seL4_IllegalOperation);
    }

    bp_rpc_binding = (bp_rpc_binding_t) {
        .endpoint = endpoint,
        .caller = caller,
        .server = server,
        .caller_asid = caller_asid,
        .server_asid = server_asid,
        .token = descriptor.token,
    };
    bp_rpc_reply_word(descriptor.token);
    return EXCEPTION_NONE;
}

bool_t bp_rpc_is_endpoint_invocation(word_t label)
{
    return label == BP_RPC_SEL4_BIND_LABEL
           || label == BP_RPC_SEL4_UNBIND_LABEL;
}

exception_t bp_rpc_decode_endpoint_invocation(word_t label, word_t length,
                                               cap_t endpoint_cap, bool_t call,
                                               word_t *buffer)
{
    if (!call) {
        return bp_rpc_error(seL4_IllegalOperation);
    }
    if (label == BP_RPC_SEL4_BIND_LABEL) {
        return bp_rpc_bind(length, endpoint_cap, buffer);
    }
    endpoint_t *endpoint = EP_PTR(cap_endpoint_cap_get_capEPPtr(endpoint_cap));
    if (bp_rpc_binding.token == 0 || bp_rpc_binding.endpoint != endpoint
        || bp_rpc_binding.caller != NODE_STATE(ksCurThread)) {
        return bp_rpc_error(seL4_IllegalOperation);
    }
    bp_rpc_revoke();
    bp_rpc_reply_word(BP_RPC_CONTROL_OK);
    return EXCEPTION_NONE;
}

void bp_rpc_finalise_endpoint(endpoint_t *endpoint)
{
    if (bp_rpc_binding.endpoint == endpoint) {
        bp_rpc_revoke();
    }
}

void bp_rpc_finalise_tcb(tcb_t *tcb)
{
    if (bp_rpc_binding.caller == tcb || bp_rpc_binding.server == tcb) {
        bp_rpc_revoke();
    }
}

void bp_rpc_tcb_vspace_change(tcb_t *tcb)
{
    bp_rpc_finalise_tcb(tcb);
}

void bp_rpc_revoke_asid(asid_t asid)
{
    if ((bp_rpc_binding.token != 0)
        && (bp_rpc_binding.caller_asid == asid
            || bp_rpc_binding.server_asid == asid)) {
        bp_rpc_revoke();
    }
}

void bp_rpc_revoke_asid_pool(asid_t asid_base)
{
    if ((bp_rpc_binding.token != 0)
        && (ASID_HIGH(bp_rpc_binding.caller_asid) == ASID_HIGH(asid_base)
            || ASID_HIGH(bp_rpc_binding.server_asid) == ASID_HIGH(asid_base))) {
        bp_rpc_revoke();
    }
}
