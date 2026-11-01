#ifndef PROTECTED_RPC_RUNTIME_H
#define PROTECTED_RPC_RUNTIME_H

#include "protected_rpc.h"

/* Trusted runtime layout behind the public opaque call-context type. */
struct protected_rpc_call_context {
    uint64_t caller_badge;
    const protected_rpc_server_config_t *server_config;
};

/* Dispatch one already-received request through the trusted common boundary.
 * Transport runtimes supply the authenticated badge; application code cannot
 * forge a call context through the public interface. */
protected_rpc_status_t protected_rpc_dispatch(
    const protected_rpc_server_config_t *config,
    uint64_t caller_badge,
    const protected_rpc_message_t *request,
    protected_rpc_message_t *reply);

#endif
