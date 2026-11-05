#include "protected_rpc_backend.h"

static protected_rpc_status_t hardware_not_available(
    protected_rpc_endpoint_t endpoint,
    const protected_rpc_message_t *request,
    protected_rpc_attempt_result_t *result)
{
    (void)endpoint;
    (void)request;
    result->disposition = PROTECTED_RPC_ATTEMPT_FALLBACK_SAFE;
    result->status = PROTECTED_RPC_UNSUPPORTED;
    result->path = PROTECTED_RPC_PATH_HARDWARE;
    return result->status;
}

const protected_rpc_backend_t protected_rpc_hardware_backend = {
    .try_call = hardware_not_available,
};
