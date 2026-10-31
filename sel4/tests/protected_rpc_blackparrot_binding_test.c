#include <assert.h>
#include <stdint.h>
#include <string.h>

#include <sel4/sel4.h>

#include "blackparrot_rpc_abi.h"
#include "protected_rpc_blackparrot.h"

seL4_Word mock_sel4_mrs[8];
seL4_CPtr mock_sel4_caps[4];

static seL4_CPtr called_endpoint;
static seL4_MessageInfo_t called_info;
static seL4_Word call_error;
static uint64_t kernel_token;
static uint64_t attached_token;
static protected_rpc_endpoint_t attached_endpoint;

seL4_MessageInfo_t seL4_Call(seL4_CPtr endpoint, seL4_MessageInfo_t info)
{
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
    attached_endpoint = endpoint;
    attached_token = token;
    return PROTECTED_RPC_OK;
}

protected_rpc_status_t protected_rpc_blackparrot_detach(
    protected_rpc_endpoint_t endpoint)
{
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

    assert(protected_rpc_blackparrot_unbind(endpoint) == PROTECTED_RPC_OK);
    assert(seL4_MessageInfo_get_label(called_info)
           == BP_RPC_SEL4_UNBIND_LABEL);
    assert(attached_token == 0);

    reset();
    call_error = seL4_IllegalOperation;
    assert(protected_rpc_blackparrot_bind(endpoint, &binding)
           == PROTECTED_RPC_DENIED);
    assert(attached_token == 0);

    reset();
    assert(protected_rpc_blackparrot_bind(endpoint, NULL)
           == PROTECTED_RPC_INVALID_ARGUMENT);
    assert(called_endpoint == 0);
    return 0;
}
