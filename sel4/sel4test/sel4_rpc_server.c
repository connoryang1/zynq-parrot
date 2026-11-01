/* Minimal server image for the focused BlackParrot protected-RPC test. */

#include <stdint.h>
#include <stdlib.h>
#include <sel4/sel4.h>

#include "protected_rpc.h"

#define SERVER_SOFTWARE_CALLS 8

static void __attribute__((naked, noinline, used, aligned(64)))
hardware_sum_entry(void)
{
    __asm__ volatile(
        ".option push\n.option norvc\n"
        "add a0, a0, a1\n"
        "add a0, a0, a2\n"
        "add a0, a0, a3\n"
        /* One reply word and PROTECTED_RPC_OK status. */
        "li a5, 1\n"
        "csrw 0x809, a0\n"
        "1: j 1b\n"
        ".option pop\n");
}

static protected_rpc_status_t sum_service(
    const protected_rpc_call_context_t *context,
    const protected_rpc_message_t *request,
    protected_rpc_message_t *reply,
    void *cookie)
{
    (void)context;
    (void)cookie;
    if (request->length != 4) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }
    reply->length = 1;
    reply->words[0] = request->words[0] + request->words[1]
                      + request->words[2] + request->words[3];
    return PROTECTED_RPC_OK;
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }

    const seL4_CPtr endpoint = (seL4_CPtr)strtoull(argv[0], NULL, 0);
    const seL4_CPtr control = (seL4_CPtr)strtoull(argv[1], NULL, 0);
    if (endpoint == 0 || control == 0) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }

    /* Publish the address in this VSpace before blocking on the endpoint. */
    seL4_SetMR(0, (seL4_Word)(uintptr_t)hardware_sum_entry);
    seL4_Send(control, seL4_MessageInfo_new(0, 0, 0, 1));

    const protected_rpc_server_config_t config = {
        .handler = sum_service,
        .max_requests = SERVER_SOFTWARE_CALLS,
    };
    const protected_rpc_status_t status = protected_rpc_serve(
        (protected_rpc_endpoint_t){.opaque = endpoint}, &config);

    /* Let the test destroy the process only after the final reply completed. */
    seL4_Send(control, seL4_MessageInfo_new(status, 0, 0, 0));
    for (;;) {
        seL4_Yield();
    }
}
