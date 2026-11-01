#ifndef PROTECTED_RPC_RUNTIME_H
#define PROTECTED_RPC_RUNTIME_H

#include "protected_rpc.h"

/* Trusted runtime layout behind the public opaque call-context type. */
struct protected_rpc_call_context {
    uint64_t caller_badge;
    const protected_rpc_server_config_t *server_config;
};

#endif
