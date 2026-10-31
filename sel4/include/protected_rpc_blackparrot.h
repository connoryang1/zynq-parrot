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

#endif
