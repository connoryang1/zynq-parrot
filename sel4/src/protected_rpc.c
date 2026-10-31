#include <string.h>

#include "protected_rpc_backend.h"

static protected_rpc_status_t finish_attempt(
    const protected_rpc_attempt_result_t *attempt,
    protected_rpc_call_result_t *result)
{
    result->status = attempt->status;
    result->path = attempt->path;
    if (attempt->disposition == PROTECTED_RPC_ATTEMPT_COMPLETED) {
        result->reply = attempt->reply;
    } else {
        memset(&result->reply, 0, sizeof(result->reply));
    }
    return result->status;
}

static protected_rpc_status_t run_backend(
    const protected_rpc_backend_t *backend,
    protected_rpc_endpoint_t endpoint,
    const protected_rpc_message_t *request,
    protected_rpc_attempt_result_t *attempt)
{
    memset(attempt, 0, sizeof(*attempt));
    attempt->status = backend->try_call(endpoint, request, attempt);
    return attempt->status;
}

protected_rpc_status_t protected_rpc_call(
    protected_rpc_endpoint_t endpoint,
    const protected_rpc_message_t *request,
    const protected_rpc_call_options_t *options,
    protected_rpc_call_result_t *result)
{
    if (!protected_rpc_message_valid(request) || result == NULL) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }

    memset(result, 0, sizeof(*result));
    protected_rpc_route_t route = options == NULL
                                  ? PROTECTED_RPC_ROUTE_AUTO
                                  : options->route;
    if (route > PROTECTED_RPC_ROUTE_HARDWARE) {
        result->status = PROTECTED_RPC_INVALID_ARGUMENT;
        return result->status;
    }

    protected_rpc_attempt_result_t attempt;
    if (route == PROTECTED_RPC_ROUTE_SOFTWARE) {
        run_backend(&protected_rpc_software_backend, endpoint, request,
                    &attempt);
        if (attempt.disposition == PROTECTED_RPC_ATTEMPT_FALLBACK_SAFE) {
            result->status = PROTECTED_RPC_BACKEND_ERROR;
            result->path = PROTECTED_RPC_PATH_SOFTWARE;
            return result->status;
        }
        return finish_attempt(&attempt, result);
    }

    run_backend(&protected_rpc_hardware_backend, endpoint, request, &attempt);
    if (attempt.disposition != PROTECTED_RPC_ATTEMPT_FALLBACK_SAFE) {
        return finish_attempt(&attempt, result);
    }

    if (route == PROTECTED_RPC_ROUTE_HARDWARE) {
        result->status = PROTECTED_RPC_UNSUPPORTED;
        result->path = PROTECTED_RPC_PATH_HARDWARE;
        return result->status;
    }

    run_backend(&protected_rpc_software_backend, endpoint, request, &attempt);
    if (attempt.disposition == PROTECTED_RPC_ATTEMPT_FALLBACK_SAFE) {
        result->status = PROTECTED_RPC_BACKEND_ERROR;
        result->path = PROTECTED_RPC_PATH_SOFTWARE;
        return result->status;
    }
    return finish_attempt(&attempt, result);
}
