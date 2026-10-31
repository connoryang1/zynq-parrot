#include <assert.h>
#include <stdint.h>

#include "blackparrot_rpc_abi.h"
#include "protected_rpc_backend.h"
#include "protected_rpc_blackparrot.h"

static uint64_t arch_outcome;
static uint64_t arch_reply_meta;
static uint64_t expected_token;
static unsigned arch_calls;
static unsigned software_calls;

uint64_t protected_rpc_blackparrot_arch_call(
    uint64_t token, uint64_t words[BP_RPC_MAX_WORDS], uint64_t request_meta,
    uint64_t *reply_meta)
{
    assert(token == expected_token);
    assert(bp_rpc_request_meta_valid(request_meta));
    arch_calls++;
    for (size_t word = 0; word < BP_RPC_MAX_WORDS; word++) {
        words[word] += UINT64_C(0x100) + word;
    }
    *reply_meta = arch_reply_meta;
    return arch_outcome;
}

static protected_rpc_status_t software_call(
    protected_rpc_endpoint_t endpoint,
    const protected_rpc_message_t *request,
    protected_rpc_attempt_result_t *result)
{
    (void)endpoint;
    (void)request;
    software_calls++;
    result->disposition = PROTECTED_RPC_ATTEMPT_COMPLETED;
    result->status = PROTECTED_RPC_OK;
    result->path = PROTECTED_RPC_PATH_SOFTWARE;
    result->reply.length = 1;
    result->reply.words[0] = UINT64_C(0x534f4654);
    return result->status;
}

const protected_rpc_backend_t protected_rpc_software_backend = {
    .try_call = software_call,
};

static void reset_arch(uint64_t outcome, uint64_t meta)
{
    arch_outcome = outcome;
    arch_reply_meta = meta;
    arch_calls = 0;
    software_calls = 0;
}

int main(void)
{
    const protected_rpc_endpoint_t endpoint = {.opaque = 7};
    const protected_rpc_endpoint_t other = {.opaque = 8};
    const protected_rpc_message_t request = {
        .length = 2,
        .words = {10, 20},
    };
    protected_rpc_call_result_t result;
    protected_rpc_call_options_t options = {
        .route = PROTECTED_RPC_ROUTE_HARDWARE,
    };
    expected_token = UINT64_C(0x123456789abcdef0);

    assert(protected_rpc_blackparrot_attach(endpoint, expected_token)
           == PROTECTED_RPC_OK);
    assert(protected_rpc_blackparrot_attach(other, expected_token)
           == PROTECTED_RPC_DENIED);

    reset_arch(BP_RPC_OUTCOME_COMPLETED,
               bp_rpc_reply_meta(2, PROTECTED_RPC_OK));
    assert(protected_rpc_call(endpoint, &request, &options, &result)
           == PROTECTED_RPC_OK);
    assert(arch_calls == 1 && software_calls == 0);
    assert(result.path == PROTECTED_RPC_PATH_HARDWARE);
    assert(result.reply.length == 2);
    assert(result.reply.words[0] == UINT64_C(0x10a));
    assert(result.reply.words[1] == UINT64_C(0x115));

    reset_arch(BP_RPC_OUTCOME_REVOKED, 0);
    assert(protected_rpc_call(endpoint, &request, &options, &result)
           == PROTECTED_RPC_REVOKED);
    assert(arch_calls == 1 && software_calls == 0);

    options.route = PROTECTED_RPC_ROUTE_AUTO;
    reset_arch(BP_RPC_OUTCOME_NOT_STARTED, 0);
    assert(protected_rpc_call(endpoint, &request, &options, &result)
           == PROTECTED_RPC_OK);
    assert(arch_calls == 1 && software_calls == 1);
    assert(result.path == PROTECTED_RPC_PATH_SOFTWARE);

    reset_arch(BP_RPC_OUTCOME_COMMITTED_FAILED, 0);
    assert(protected_rpc_call(endpoint, &request, &options, &result)
           == PROTECTED_RPC_BACKEND_ERROR);
    assert(arch_calls == 1 && software_calls == 0);

    reset_arch(BP_RPC_OUTCOME_COMPLETED, UINT64_C(1) << 16);
    assert(protected_rpc_call(endpoint, &request, &options, &result)
           == PROTECTED_RPC_BACKEND_ERROR);
    assert(arch_calls == 1 && software_calls == 0);

    reset_arch(BP_RPC_OUTCOME_COMPLETED, 0);
    assert(protected_rpc_call(other, &request, &options, &result)
           == PROTECTED_RPC_OK);
    assert(arch_calls == 0 && software_calls == 1);

    assert(protected_rpc_blackparrot_detach(endpoint) == PROTECTED_RPC_OK);
    assert(protected_rpc_blackparrot_detach(endpoint) == PROTECTED_RPC_REVOKED);
    return 0;
}
