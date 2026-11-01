#include <stdint.h>
#include <string.h>

#include "blackparrot_rpc_abi.h"
#include "protected_rpc_blackparrot.h"
#include "protected_rpc_runtime.h"

static protected_rpc_status_t dispatch_protected_call(
    const protected_rpc_server_config_t *config, uint64_t caller_badge,
    uint64_t request_meta, uint64_t words[PROTECTED_RPC_MAX_WORDS],
    uint64_t *reply_meta)
{
    if (words == NULL || reply_meta == NULL) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }

    protected_rpc_message_t request = {0};
    protected_rpc_message_t reply = {0};
    protected_rpc_status_t status = PROTECTED_RPC_INVALID_ARGUMENT;
    if (bp_rpc_request_meta_valid(request_meta)) {
        request.length = bp_rpc_request_length(request_meta);
        request.words[0] = request.length >= 1 ? words[0] : 0;
        request.words[1] = request.length >= 2 ? words[1] : 0;
        request.words[2] = request.length >= 3 ? words[2] : 0;
        request.words[3] = request.length >= 4 ? words[3] : 0;
        status = protected_rpc_dispatch(
            config, caller_badge, &request, &reply);
    }

    words[0] = reply.length >= 1 ? reply.words[0] : 0;
    words[1] = reply.length >= 2 ? reply.words[1] : 0;
    words[2] = reply.length >= 3 ? reply.words[2] : 0;
    words[3] = reply.length >= 4 ? reply.words[3] : 0;
    *reply_meta = bp_rpc_reply_meta(reply.length, (uint8_t)status);
    return status;
}

#ifdef PROTECTED_RPC_BLACKPARROT_SERVER_TEST_HOOK
static void protected_rpc_blackparrot_server_entry(void)
{
}

protected_rpc_status_t protected_rpc_blackparrot_server_test_dispatch(
    const protected_rpc_server_config_t *config, uint64_t caller_badge,
    uint64_t request_meta, uint64_t words[PROTECTED_RPC_MAX_WORDS],
    uint64_t *reply_meta)
{
    return dispatch_protected_call(
        config, caller_badge, request_meta, words, reply_meta);
}
#elif defined(__riscv) && __riscv_xlen == 64
static void __attribute__((noreturn, noinline)) protected_return(
    const uint64_t words[PROTECTED_RPC_MAX_WORDS], uint64_t reply_meta)
{
    register uint64_t a0 __asm__("a0") = words[0];
    register uint64_t a1 __asm__("a1") = words[1];
    register uint64_t a2 __asm__("a2") = words[2];
    register uint64_t a3 __asm__("a3") = words[3];
    register uint64_t a5 __asm__("a5") = reply_meta;
    __asm__ volatile(
        "csrw 0x809, a0"
        : "+r"(a0), "+r"(a1), "+r"(a2), "+r"(a3), "+r"(a5)
        :
        : "memory");

    for (;;) {
        __asm__ volatile("wfi");
    }
}

static void __attribute__((noreturn, noinline, used, aligned(64)))
protected_rpc_blackparrot_server_entry(
    uint64_t word0, uint64_t word1, uint64_t word2, uint64_t word3)
{
    protected_rpc_server_config_t *config;
    uint64_t caller_badge;
    uint64_t request_meta;
    __asm__ volatile("mv %0, tp" : "=r"(config));
    __asm__ volatile("mv %0, s1" : "=r"(caller_badge));
    __asm__ volatile("mv %0, a5" : "=r"(request_meta));

    uint64_t words[PROTECTED_RPC_MAX_WORDS] = {
        word0, word1, word2, word3,
    };
    uint64_t reply_meta;
    (void)dispatch_protected_call(
        config, caller_badge, request_meta, words, &reply_meta);
    protected_return(words, reply_meta);
}
#else
#error "BlackParrot protected-RPC server runtime requires RV64 or its test hook"
#endif

protected_rpc_status_t protected_rpc_blackparrot_server_prepare(
    const protected_rpc_server_config_t *config,
    protected_rpc_blackparrot_server_runtime_t *runtime)
{
    if (runtime == NULL) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }
    memset(runtime, 0, sizeof(*runtime));
    if (config == NULL || config->handler == NULL) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }

    uintptr_t global_pointer;
#ifdef PROTECTED_RPC_BLACKPARROT_SERVER_TEST_HOOK
    global_pointer = UINT64_C(0x4750);
#else
    __asm__ volatile("mv %0, gp" : "=r"(global_pointer));
#endif
    runtime->server_entry =
        (uint64_t)(uintptr_t)protected_rpc_blackparrot_server_entry;
    runtime->server_gp = global_pointer;
    runtime->server_tp = (uint64_t)(uintptr_t)config;
    return PROTECTED_RPC_OK;
}
