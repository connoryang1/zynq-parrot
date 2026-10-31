#include <stdint.h>
#include <string.h>

#include "blackparrot_rpc_abi.h"
#include "protected_rpc_backend.h"
#include "protected_rpc_blackparrot.h"

static protected_rpc_endpoint_t bound_endpoint;
static uint64_t bound_token;

#ifdef PROTECTED_RPC_BLACKPARROT_TEST_HOOK
extern uint64_t protected_rpc_blackparrot_arch_call(
    uint64_t token, uint64_t words[BP_RPC_MAX_WORDS], uint64_t request_meta,
    uint64_t *reply_meta);
#elif defined(__riscv) && __riscv_xlen == 64
static uint64_t protected_rpc_blackparrot_arch_call(
    uint64_t token, uint64_t words[BP_RPC_MAX_WORDS], uint64_t request_meta,
    uint64_t *reply_meta)
{
    register uint64_t a0 __asm__("a0") = words[0];
    register uint64_t a1 __asm__("a1") = words[1];
    register uint64_t a2 __asm__("a2") = words[2];
    register uint64_t a3 __asm__("a3") = words[3];
    register uint64_t a4 __asm__("a4") = token;
    register uint64_t a5 __asm__("a5") = request_meta;

    __asm__ volatile(
        "csrrw a4, 0x808, a4"
        : "+r"(a0), "+r"(a1), "+r"(a2), "+r"(a3), "+r"(a4), "+r"(a5)
        :
        : "memory");

    words[0] = a0;
    words[1] = a1;
    words[2] = a2;
    words[3] = a3;
    *reply_meta = a5;
    return a4;
}
#else
#error "BlackParrot protected-RPC backend requires RV64 or its test hook"
#endif

protected_rpc_status_t protected_rpc_blackparrot_attach(
    protected_rpc_endpoint_t endpoint, uint64_t token)
{
    if (endpoint.opaque == 0 || token == 0) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }
    if (bound_token != 0
        && (bound_endpoint.opaque != endpoint.opaque || bound_token != token)) {
        return PROTECTED_RPC_DENIED;
    }
    bound_endpoint = endpoint;
    bound_token = token;
    return PROTECTED_RPC_OK;
}

protected_rpc_status_t protected_rpc_blackparrot_detach(
    protected_rpc_endpoint_t endpoint)
{
    if (bound_token == 0 || bound_endpoint.opaque != endpoint.opaque) {
        return PROTECTED_RPC_REVOKED;
    }
    memset(&bound_endpoint, 0, sizeof(bound_endpoint));
    bound_token = 0;
    return PROTECTED_RPC_OK;
}

static protected_rpc_status_t blackparrot_try_call(
    protected_rpc_endpoint_t endpoint,
    const protected_rpc_message_t *request,
    protected_rpc_attempt_result_t *result)
{
    result->path = PROTECTED_RPC_PATH_HARDWARE;
    if (!protected_rpc_message_valid(request) || endpoint.opaque == 0) {
        result->disposition = PROTECTED_RPC_ATTEMPT_REJECTED;
        result->status = PROTECTED_RPC_INVALID_ARGUMENT;
        return result->status;
    }
    if (bound_token == 0 || bound_endpoint.opaque != endpoint.opaque) {
        result->disposition = PROTECTED_RPC_ATTEMPT_FALLBACK_SAFE;
        result->status = PROTECTED_RPC_UNSUPPORTED;
        return result->status;
    }

    uint64_t words[BP_RPC_MAX_WORDS] = {0};
    for (size_t word = 0; word < request->length; word++) {
        words[word] = request->words[word];
    }
    uint64_t reply_meta = 0;
    const uint64_t outcome = protected_rpc_blackparrot_arch_call(
        bound_token, words, bp_rpc_request_meta(request->length), &reply_meta);

    switch (outcome) {
    case BP_RPC_OUTCOME_COMPLETED:
        if (!bp_rpc_reply_meta_valid(reply_meta)
            || bp_rpc_reply_status(reply_meta) > PROTECTED_RPC_BACKEND_ERROR) {
            result->disposition = PROTECTED_RPC_ATTEMPT_COMMITTED_FAILED;
            result->status = PROTECTED_RPC_BACKEND_ERROR;
            return result->status;
        }
        result->reply.length = bp_rpc_reply_length(reply_meta);
        for (size_t word = 0; word < result->reply.length; word++) {
            result->reply.words[word] = words[word];
        }
        result->disposition = PROTECTED_RPC_ATTEMPT_COMPLETED;
        result->status = (protected_rpc_status_t)bp_rpc_reply_status(reply_meta);
        return result->status;

    case BP_RPC_OUTCOME_NOT_STARTED:
        result->disposition = PROTECTED_RPC_ATTEMPT_FALLBACK_SAFE;
        result->status = PROTECTED_RPC_UNSUPPORTED;
        return result->status;

    case BP_RPC_OUTCOME_REVOKED:
        result->disposition = PROTECTED_RPC_ATTEMPT_FALLBACK_SAFE;
        result->status = PROTECTED_RPC_REVOKED;
        return result->status;

    case BP_RPC_OUTCOME_COMMITTED_FAILED:
    default:
        result->disposition = PROTECTED_RPC_ATTEMPT_COMMITTED_FAILED;
        result->status = PROTECTED_RPC_BACKEND_ERROR;
        return result->status;
    }
}

const protected_rpc_backend_t protected_rpc_hardware_backend = {
    .try_call = blackparrot_try_call,
};
