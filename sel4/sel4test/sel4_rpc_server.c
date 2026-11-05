/* Minimal server image for the focused protected-RPC integration test. */

#include <stdint.h>
#include <stdlib.h>
#include <sel4/config.h>
#include <sel4/sel4.h>

#include "protected_rpc.h"
#include "protected_rpc_runtime.h"
#ifdef CONFIG_PLAT_BLACKPARROT
#include "protected_rpc_blackparrot.h"
#endif
#include "sel4_rpc_search_service.h"

#define SERVER_SOFTWARE_CALLS SEL4_RPC_SEARCH_SOFTWARE_REQUESTS
#define SERVER_NOTIFICATION_CALLS SEL4_RPC_SEARCH_NOTIFICATION_REQUESTS

static protected_rpc_region_binding_t server_region;
static protected_rpc_server_config_t server_config;
static uint64_t server_expected_badge;

static protected_rpc_status_t serve_notifications(
    seL4_CPtr request_notification, seL4_CPtr reply_notification,
    volatile sel4_rpc_notification_mailbox_t *mailbox)
{
    for (uint64_t expected = 1; expected <= SERVER_NOTIFICATION_CALLS;
         expected++) {
        seL4_Wait(request_notification, NULL);
        const uint64_t sequence = __atomic_load_n(
            &mailbox->request_sequence, __ATOMIC_ACQUIRE);
        protected_rpc_message_t request = {0};
        protected_rpc_message_t reply;
        protected_rpc_status_t status = PROTECTED_RPC_BACKEND_ERROR;
        if (sequence == expected
            && mailbox->request_length <= PROTECTED_RPC_MAX_WORDS) {
            request.length = (uint8_t)mailbox->request_length;
            for (size_t word = 0; word < PROTECTED_RPC_MAX_WORDS; word++) {
                request.words[word] = mailbox->request_words[word];
            }
            status = protected_rpc_dispatch(
                &server_config, 0, &request, &reply);
        } else {
            reply = (protected_rpc_message_t) {0};
        }
        mailbox->reply_length = reply.length;
        for (size_t word = 0; word < PROTECTED_RPC_MAX_WORDS; word++) {
            mailbox->reply_words[word] = reply.words[word];
        }
        mailbox->status = status;
        __atomic_store_n(&mailbox->reply_sequence, expected, __ATOMIC_RELEASE);
        seL4_Signal(reply_notification);
    }
    return PROTECTED_RPC_OK;
}

int main(int argc, char **argv)
{
    if (argc != 4 && argc != 7) {
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
        .cookie = &server_expected_badge,
    };

    /* Publish the hardware entry and its trusted C runtime state before the
     * ordinary server blocks on the endpoint. */
#ifdef CONFIG_PLAT_BLACKPARROT
    protected_rpc_blackparrot_server_runtime_t runtime;
    if (protected_rpc_blackparrot_server_prepare(&server_config, &runtime)
        != PROTECTED_RPC_OK) {
        return PROTECTED_RPC_BACKEND_ERROR;
    }
    seL4_SetMR(0, runtime.server_entry);
    seL4_SetMR(1, runtime.server_gp);
    seL4_SetMR(2, runtime.server_tp);
#else
    seL4_SetMR(0, 0);
    seL4_SetMR(1, 0);
    seL4_SetMR(2, 0);
#endif
    seL4_Send(control, seL4_MessageInfo_new(0, 0, 0, 3));

    if (argc == 7) {
        const seL4_CPtr request_notification =
            (seL4_CPtr)strtoull(argv[4], NULL, 0);
        const seL4_CPtr reply_notification =
            (seL4_CPtr)strtoull(argv[5], NULL, 0);
        volatile sel4_rpc_notification_mailbox_t *mailbox =
            (void *)(uintptr_t)strtoull(argv[6], NULL, 0);
        if (request_notification == 0 || reply_notification == 0
            || mailbox == NULL
            || serve_notifications(request_notification, reply_notification,
                                   mailbox) != PROTECTED_RPC_OK) {
            return PROTECTED_RPC_BACKEND_ERROR;
        }
    }

#ifdef CONFIG_PLAT_BLACKPARROT
    /* The server receives on an unbadged cap, while the caller binds and
     * invokes through its minted cap. Both the ordinary and protected paths
     * must authenticate the same kernel-derived nonzero badge. */
    server_expected_badge = SEL4_RPC_SEARCH_CALLER_BADGE;
#endif

    const protected_rpc_status_t status = protected_rpc_serve(
        (protected_rpc_endpoint_t){.opaque = endpoint}, &server_config);

    /* Let the test destroy the process only after the final reply completed. */
    seL4_Send(control, seL4_MessageInfo_new(status, 0, 0, 0));
    for (;;) {
        seL4_Yield();
    }
}
