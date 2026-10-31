#ifndef PROTECTED_RPC_BLACKPARROT_H
#define PROTECTED_RPC_BLACKPARROT_H

#include <stdint.h>

#include "protected_rpc.h"

/*
 * Trusted-runtime boundary for the initial one-slot implementation. The token
 * is returned by the kernel binding operation; application code continues to
 * call protected_rpc_call() with its ordinary opaque endpoint.
 *
 * Attach/detach run while application calls are stopped. Kernel descriptor
 * revocation must complete before detach returns a token to the allocator.
 */
protected_rpc_status_t protected_rpc_blackparrot_attach(
    protected_rpc_endpoint_t endpoint, uint64_t token);

protected_rpc_status_t protected_rpc_blackparrot_detach(
    protected_rpc_endpoint_t endpoint);

/*
 * Trusted seL4 runtime input. The kernel derives both address spaces, the
 * endpoint badge, slot, token, and hardware context IDs. These values name
 * only the fixed server entry state inside the server's own VSpace.
 */
typedef struct {
    uint64_t server_tcb;
    uint64_t server_entry;
    uint64_t server_sp;
    uint64_t server_gp;
    uint64_t server_tp;
    uint8_t request_words;
    uint8_t reply_words;
} protected_rpc_blackparrot_binding_t;

/* Atomically create/remove the kernel binding and update the caller adapter. */
protected_rpc_status_t protected_rpc_blackparrot_bind(
    protected_rpc_endpoint_t endpoint,
    const protected_rpc_blackparrot_binding_t *binding);

protected_rpc_status_t protected_rpc_blackparrot_unbind(
    protected_rpc_endpoint_t endpoint);

#endif
