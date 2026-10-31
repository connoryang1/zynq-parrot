#include <sel4/sel4.h>
#include <stdint.h>

#include "blackparrot_rpc_abi.h"
#include "protected_rpc_blackparrot.h"

static protected_rpc_status_t sel4_error_status(seL4_Word error)
{
    switch (error) {
    case seL4_InvalidArgument:
    case seL4_RangeError:
    case seL4_AlignmentError:
    case seL4_TruncatedMessage:
        return PROTECTED_RPC_INVALID_ARGUMENT;
    case seL4_InvalidCapability:
    case seL4_IllegalOperation:
    case seL4_DeleteFirst:
    case seL4_RevokeFirst:
        return PROTECTED_RPC_DENIED;
    default:
        return PROTECTED_RPC_BACKEND_ERROR;
    }
}

static seL4_MessageInfo_t invoke_binding(
    protected_rpc_endpoint_t endpoint, seL4_Word label,
    const protected_rpc_blackparrot_binding_t *binding)
{
    seL4_Word length = 0;
    seL4_Word extra_caps = 0;
    if (binding != NULL) {
        seL4_SetMR(0, binding->server_entry);
        seL4_SetMR(1, binding->server_sp);
        seL4_SetMR(2, binding->server_gp);
        seL4_SetMR(3, binding->server_tp);
        seL4_SetMR(4, bp_rpc_sel4_counts(binding->request_words,
                                         binding->reply_words));
        seL4_SetCap(0, (seL4_CPtr)binding->server_tcb);
        length = BP_RPC_SEL4_BIND_ARGUMENTS;
        extra_caps = 1;
    }
    return seL4_Call((seL4_CPtr)endpoint.opaque,
                     seL4_MessageInfo_new(label, 0, extra_caps, length));
}

protected_rpc_status_t protected_rpc_blackparrot_bind(
    protected_rpc_endpoint_t endpoint,
    const protected_rpc_blackparrot_binding_t *binding)
{
    if (endpoint.opaque == 0 || binding == NULL || binding->server_tcb == 0
        || binding->server_entry == 0 || binding->server_sp == 0
        || binding->request_words > BP_RPC_MAX_WORDS
        || binding->reply_words > BP_RPC_MAX_WORDS) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }

    seL4_MessageInfo_t info = invoke_binding(
        endpoint, BP_RPC_SEL4_BIND_LABEL, binding);
    const seL4_Word error = seL4_MessageInfo_get_label(info);
    if (error != seL4_NoError) {
        return sel4_error_status(error);
    }

    const uint64_t token = seL4_GetMR(0);
    protected_rpc_status_t status = protected_rpc_blackparrot_attach(
        endpoint, token);
    if (status != PROTECTED_RPC_OK) {
        /* Do not leave a live kernel descriptor detached from the adapter. */
        (void)invoke_binding(endpoint, BP_RPC_SEL4_UNBIND_LABEL, NULL);
    }
    return status;
}

protected_rpc_status_t protected_rpc_blackparrot_unbind(
    protected_rpc_endpoint_t endpoint)
{
    if (endpoint.opaque == 0) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }
    seL4_MessageInfo_t info = invoke_binding(
        endpoint, BP_RPC_SEL4_UNBIND_LABEL, NULL);
    const seL4_Word error = seL4_MessageInfo_get_label(info);
    if (error != seL4_NoError) {
        return sel4_error_status(error);
    }
    return protected_rpc_blackparrot_detach(endpoint);
}
