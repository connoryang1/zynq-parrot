/* Minimal server image for the focused BlackParrot protected-RPC test. */

#include <stdint.h>
#include <stdlib.h>
#include <sel4/sel4.h>

#include "blackparrot_rpc_abi.h"
#include "protected_rpc.h"
#include "sel4_rpc_search_service.h"

#define SERVER_SOFTWARE_CALLS SEL4_RPC_SEARCH_SOFTWARE_REQUESTS

static protected_rpc_region_binding_t server_region;
static protected_rpc_server_config_t server_config;

static void __attribute__((noreturn, noinline, used, aligned(64)))
hardware_search_entry(uint64_t word0, uint64_t word1, uint64_t word2,
                      uint64_t word3)
{
    protected_rpc_server_config_t *config;
    __asm__ volatile("mv %0, tp" : "=r"(config));
    protected_rpc_message_t request = {
        .length = 4,
        .words = {word0, word1, word2, word3},
    };
    protected_rpc_message_t reply = {0};
    const protected_rpc_call_context_t context = {
        .runtime_private = config,
    };
    protected_rpc_status_t status = config->handler(
        &context, &request, &reply, config->cookie);
    if (!protected_rpc_message_valid(&reply)) {
        reply = (protected_rpc_message_t) {0};
        status = PROTECTED_RPC_BACKEND_ERROR;
    }

    register uint64_t a0 __asm__("a0") = reply.words[0];
    register uint64_t a1 __asm__("a1") = reply.words[1];
    register uint64_t a2 __asm__("a2") = reply.words[2];
    register uint64_t a3 __asm__("a3") = reply.words[3];
    register uint64_t a5 __asm__("a5") = bp_rpc_reply_meta(
        reply.length, (uint8_t)status);
    __asm__ volatile(
        "csrw 0x809, a0"
        : "+r"(a0), "+r"(a1), "+r"(a2), "+r"(a3), "+r"(a5)
        :
        : "memory");
    for (;;) {
        __asm__ volatile("wfi");
    }
}

int main(int argc, char **argv)
{
    if (argc != 4) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }

    const seL4_CPtr endpoint = (seL4_CPtr)strtoull(argv[0], NULL, 0);
    const seL4_CPtr control = (seL4_CPtr)strtoull(argv[1], NULL, 0);
    const uintptr_t shared_base = (uintptr_t)strtoull(argv[2], NULL, 0);
    const uint64_t region_token = strtoull(argv[3], NULL, 0);
    if (endpoint == 0 || control == 0 || shared_base == 0
        || region_token == 0) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }

    server_region = (protected_rpc_region_binding_t) {
        .region = {.opaque = region_token},
        .local_base = (void *)shared_base,
        .size = UINT64_C(1) << seL4_PageBits,
        .access = PROTECTED_RPC_ACCESS_READ,
    };
    server_config = (protected_rpc_server_config_t) {
        .handler = sel4_rpc_bounded_search_service,
        .regions = &server_region,
        .region_count = 1,
        .max_requests = SERVER_SOFTWARE_CALLS,
    };

    uintptr_t global_pointer;
    __asm__ volatile("mv %0, gp" : "=r"(global_pointer));
    /* Publish the hardware entry and its trusted C runtime state before the
     * ordinary server blocks on the endpoint. */
    seL4_SetMR(0, (seL4_Word)(uintptr_t)hardware_search_entry);
    seL4_SetMR(1, global_pointer);
    seL4_SetMR(2, (seL4_Word)(uintptr_t)&server_config);
    seL4_Send(control, seL4_MessageInfo_new(0, 0, 0, 3));

    const protected_rpc_status_t status = protected_rpc_serve(
        (protected_rpc_endpoint_t){.opaque = endpoint}, &server_config);

    /* Let the test destroy the process only after the final reply completed. */
    seL4_Send(control, seL4_MessageInfo_new(status, 0, 0, 0));
    for (;;) {
        seL4_Yield();
    }
}
