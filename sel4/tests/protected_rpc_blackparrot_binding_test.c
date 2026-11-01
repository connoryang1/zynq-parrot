#include <assert.h>
#include <stdint.h>
#include <string.h>

#include <sel4/sel4.h>

#include "blackparrot_rpc_abi.h"
#include "protected_rpc_backend.h"
#include "protected_rpc_blackparrot.h"

seL4_Word mock_sel4_mrs[16];
seL4_CPtr mock_sel4_caps[4];

static seL4_CPtr called_endpoint;
static seL4_MessageInfo_t called_info;
static seL4_Word call_error;
static uint64_t kernel_token;
static uint64_t attached_token;
static protected_rpc_endpoint_t attached_endpoint;
static protected_rpc_status_t attach_status;
static protected_rpc_status_t detach_status;
static unsigned kernel_calls;
static unsigned attach_calls;
static unsigned detach_calls;

seL4_MessageInfo_t seL4_Call(seL4_CPtr endpoint, seL4_MessageInfo_t info)
{
    kernel_calls++;
    called_endpoint = endpoint;
    called_info = info;
    if (seL4_MessageInfo_get_label(info) == BP_RPC_SEL4_BIND_LABEL
        && call_error == seL4_NoError) {
        mock_sel4_mrs[0] = kernel_token;
    }
    return seL4_MessageInfo_new(call_error, 0, 0, 0);
}

protected_rpc_status_t protected_rpc_blackparrot_attach(
    protected_rpc_endpoint_t endpoint, uint64_t token)
{
    attach_calls++;
    if (attach_status != PROTECTED_RPC_OK) {
        return attach_status;
    }
    attached_endpoint = endpoint;
    attached_token = token;
    return PROTECTED_RPC_OK;
}

protected_rpc_status_t protected_rpc_blackparrot_detach(
    protected_rpc_endpoint_t endpoint)
{
    detach_calls++;
    if (detach_status != PROTECTED_RPC_OK) {
        return detach_status;
    }
    assert(endpoint.opaque == attached_endpoint.opaque);
    attached_token = 0;
    return PROTECTED_RPC_OK;
}

static void reset(void)
{
    memset(mock_sel4_mrs, 0, sizeof(mock_sel4_mrs));
    memset(mock_sel4_caps, 0, sizeof(mock_sel4_caps));
    called_endpoint = 0;
    called_info.words[0] = 0;
    call_error = seL4_NoError;
    kernel_token = UINT64_C(0x123456789abcdef0);
    attach_status = PROTECTED_RPC_OK;
    detach_status = PROTECTED_RPC_OK;
    kernel_calls = 0;
    attach_calls = 0;
    detach_calls = 0;
    attached_token = 0;
    attached_endpoint.opaque = 0;
}

int main(void)
{
    const protected_rpc_endpoint_t endpoint = {.opaque = 17};
    const protected_rpc_blackparrot_binding_t binding = {
        .server_tcb = 29,
        .server_entry = UINT64_C(0x10000),
        .server_sp = UINT64_C(0x20000),
        .server_gp = UINT64_C(0x30000),
        .server_tp = UINT64_C(0x40000),
        .request_words = 4,
        .reply_words = 2,
    };

    reset();
    assert(protected_rpc_blackparrot_bind(endpoint, &binding)
           == PROTECTED_RPC_OK);
    assert(called_endpoint == endpoint.opaque);
    assert(seL4_MessageInfo_get_label(called_info) == BP_RPC_SEL4_BIND_LABEL);
    assert((called_info.words[0] & UINT64_C(0xff))
           == BP_RPC_SEL4_BIND_ARGUMENTS);
    assert(((called_info.words[0] >> 8) & UINT64_C(0xff)) == 1);
    assert(mock_sel4_caps[0] == binding.server_tcb);
    assert(mock_sel4_mrs[1] == binding.server_sp);
    assert(mock_sel4_mrs[2] == binding.server_gp);
    assert(mock_sel4_mrs[3] == binding.server_tp);
    assert(mock_sel4_mrs[4] == bp_rpc_sel4_counts(4, 2));
    assert(attached_endpoint.opaque == endpoint.opaque);
    assert(attached_token == kernel_token);
    assert(kernel_calls == 1 && attach_calls == 1 && detach_calls == 0);

    assert(protected_rpc_blackparrot_unbind(endpoint) == PROTECTED_RPC_OK);
    assert(seL4_MessageInfo_get_label(called_info)
           == BP_RPC_SEL4_UNBIND_LABEL);
    assert(attached_token == 0);
    assert(kernel_calls == 2 && attach_calls == 1 && detach_calls == 1);

    reset();
    protected_rpc_blackparrot_binding_t region_binding = binding;
    region_binding.region = (protected_rpc_blackparrot_region_binding_t) {
        .region = {.opaque = UINT64_C(0xa11ce001)},
        .caller_base = UINT64_C(0x50000),
        .server_base = UINT64_C(0x60000),
        .size = UINT64_C(0x1000),
        .access = PROTECTED_RPC_ACCESS_READ | PROTECTED_RPC_ACCESS_WRITE,
    };
    assert(protected_rpc_blackparrot_bind(endpoint, &region_binding)
           == PROTECTED_RPC_OK);
    assert((called_info.words[0] & UINT64_C(0xff))
           == BP_RPC_SEL4_BIND_REGION_ARGUMENTS);
    assert(mock_sel4_mrs[5] == region_binding.region.region.opaque);
    assert(mock_sel4_mrs[6] == region_binding.region.caller_base);
    assert(mock_sel4_mrs[7] == region_binding.region.server_base);
    assert(mock_sel4_mrs[8] == region_binding.region.size);
    assert(mock_sel4_mrs[9] == region_binding.region.access);
    assert(protected_rpc_blackparrot_unbind(endpoint) == PROTECTED_RPC_OK);

    reset();
    call_error = seL4_IllegalOperation;
    assert(protected_rpc_blackparrot_bind(endpoint, &binding)
           == PROTECTED_RPC_DENIED);
    assert(attached_token == 0);
    assert(kernel_calls == 1 && attach_calls == 0 && detach_calls == 0);

    reset();
    call_error = seL4_FailedLookup;
    assert(protected_rpc_blackparrot_bind(endpoint, &region_binding)
           == PROTECTED_RPC_DENIED);
    assert(attached_token == 0);
    assert(kernel_calls == 1 && attach_calls == 0 && detach_calls == 0);

    /* A local attach failure must revoke the descriptor just installed. */
    reset();
    attach_status = PROTECTED_RPC_BACKEND_ERROR;
    assert(protected_rpc_blackparrot_bind(endpoint, &binding)
           == PROTECTED_RPC_BACKEND_ERROR);
    assert(seL4_MessageInfo_get_label(called_info)
           == BP_RPC_SEL4_UNBIND_LABEL);
    assert(kernel_calls == 2 && attach_calls == 1 && detach_calls == 0);
    assert(attached_token == 0);

    /* A rejected kernel unbind must leave the local association intact. */
    reset();
    assert(protected_rpc_blackparrot_bind(endpoint, &binding)
           == PROTECTED_RPC_OK);
    call_error = seL4_IllegalOperation;
    assert(protected_rpc_blackparrot_unbind(endpoint)
           == PROTECTED_RPC_DENIED);
    assert(kernel_calls == 2 && attach_calls == 1 && detach_calls == 0);
    assert(attached_token == kernel_token);

    reset();
    assert(protected_rpc_blackparrot_bind(endpoint, NULL)
           == PROTECTED_RPC_INVALID_ARGUMENT);
    assert(called_endpoint == 0);

    reset();
    region_binding.region.access = 0;
    assert(protected_rpc_blackparrot_bind(endpoint, &region_binding)
           == PROTECTED_RPC_INVALID_ARGUMENT);
    assert(called_endpoint == 0);
    return 0;
}
