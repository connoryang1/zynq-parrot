#include <assert.h>
#include <stdint.h>
#include <string.h>

#include <sel4/sel4.h>

#include "blackparrot_rpc_abi.h"
#include "protected_rpc_blackparrot.h"

seL4_Word mock_sel4_mrs[16];

seL4_MessageInfo_t seL4_Call(seL4_CPtr endpoint, seL4_MessageInfo_t info)
{
    (void)endpoint;
    return info;
}

seL4_MessageInfo_t seL4_Recv(seL4_CPtr endpoint, seL4_Word *badge)
{
    (void)endpoint;
    (void)badge;
    return seL4_MessageInfo_new(0, 0, 0, 0);
}

seL4_MessageInfo_t seL4_ReplyRecv(
    seL4_CPtr endpoint, seL4_MessageInfo_t info, seL4_Word *badge)
{
    (void)endpoint;
    (void)badge;
    return info;
}

void seL4_Reply(seL4_MessageInfo_t info)
{
    (void)info;
}

static uint64_t seen_badge;
static protected_rpc_message_t seen_request;
static unsigned handler_calls;

static protected_rpc_status_t test_handler(
    const protected_rpc_call_context_t *context,
    const protected_rpc_message_t *request,
    protected_rpc_message_t *reply, void *cookie)
{
    (void)cookie;
    handler_calls++;
    seen_badge = context->caller_badge;
    seen_request = *request;
    reply->length = 2;
    reply->words[0] = request->words[0] + 1;
    reply->words[1] = request->words[1] + 2;
    return PROTECTED_RPC_OK;
}

int main(void)
{
    const protected_rpc_server_config_t config = {
        .handler = test_handler,
    };
    protected_rpc_blackparrot_server_runtime_t runtime;
    memset(&runtime, 0xa5, sizeof(runtime));
    assert(protected_rpc_blackparrot_server_prepare(&config, &runtime)
           == PROTECTED_RPC_OK);
    assert(runtime.server_entry != 0);
    assert(runtime.server_gp == UINT64_C(0x4750));
    assert(runtime.server_tp == (uint64_t)(uintptr_t)&config);

    uint64_t words[PROTECTED_RPC_MAX_WORDS];
    uint64_t reply_meta;
    for (uint8_t length = 0; length <= PROTECTED_RPC_MAX_WORDS; length++) {
        for (size_t word = 0; word < PROTECTED_RPC_MAX_WORDS; word++) {
            words[word] = 10 * (word + 1);
        }
        reply_meta = UINT64_MAX;
        assert(protected_rpc_blackparrot_server_test_dispatch(
                   &config, UINT64_C(0x5e1a), bp_rpc_request_meta(length),
                   words, &reply_meta)
               == PROTECTED_RPC_OK);
        assert(handler_calls == (unsigned)length + 1);
        assert(seen_badge == UINT64_C(0x5e1a));
        assert(seen_request.length == length);
        assert(words[0] == (length >= 1 ? 11 : 1));
        assert(words[1] == (length >= 2 ? 22 : 2));
        assert(words[2] == 0 && words[3] == 0);
        assert(bp_rpc_reply_meta_valid(reply_meta));
        assert(bp_rpc_reply_length(reply_meta) == 2);
        assert(bp_rpc_reply_status(reply_meta) == PROTECTED_RPC_OK);
    }

    words[0] = words[1] = words[2] = words[3] = UINT64_MAX;
    reply_meta = UINT64_MAX;
    assert(protected_rpc_blackparrot_server_test_dispatch(
               &config, 7, UINT64_C(1) << 8, words, &reply_meta)
           == PROTECTED_RPC_INVALID_ARGUMENT);
    assert(handler_calls == PROTECTED_RPC_MAX_WORDS + 1);
    for (size_t word = 0; word < PROTECTED_RPC_MAX_WORDS; word++) {
        assert(words[word] == 0);
    }
    assert(bp_rpc_reply_length(reply_meta) == 0);
    assert(bp_rpc_reply_status(reply_meta) == PROTECTED_RPC_INVALID_ARGUMENT);

    memset(&runtime, 0xa5, sizeof(runtime));
    assert(protected_rpc_blackparrot_server_prepare(NULL, &runtime)
           == PROTECTED_RPC_INVALID_ARGUMENT);
    assert(runtime.server_entry == 0 && runtime.server_gp == 0
           && runtime.server_tp == 0);
    return 0;
}
