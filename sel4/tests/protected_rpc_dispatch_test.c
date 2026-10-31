#include <assert.h>
#include <string.h>

#include "protected_rpc_backend.h"

static protected_rpc_attempt_disposition_t hardware_disposition;
static protected_rpc_status_t hardware_status;
static unsigned hardware_calls;
static unsigned software_calls;

static protected_rpc_status_t mock_hardware_call(
    protected_rpc_endpoint_t endpoint,
    const protected_rpc_message_t *request,
    protected_rpc_attempt_result_t *result)
{
    (void)endpoint;
    (void)request;
    hardware_calls++;
    result->disposition = hardware_disposition;
    result->status = hardware_status;
    result->path = PROTECTED_RPC_PATH_HARDWARE;
    result->reply.length = 1;
    result->reply.words[0] = 0x48415244;
    return result->status;
}

static protected_rpc_status_t mock_software_call(
    protected_rpc_endpoint_t endpoint,
    const protected_rpc_message_t *request,
    protected_rpc_attempt_result_t *result)
{
    (void)endpoint;
    (void)request;
    software_calls++;
    result->disposition = PROTECTED_RPC_ATTEMPT_COMPLETED;
    result->status = PROTECTED_RPC_OK;
    result->path = PROTECTED_RPC_PATH_SOFTWARE;
    result->reply.length = 1;
    result->reply.words[0] = 0x534f4654;
    return result->status;
}

const protected_rpc_backend_t protected_rpc_hardware_backend = {
    .try_call = mock_hardware_call,
};

const protected_rpc_backend_t protected_rpc_software_backend = {
    .try_call = mock_software_call,
};

static void reset(protected_rpc_attempt_disposition_t disposition,
                  protected_rpc_status_t status)
{
    hardware_disposition = disposition;
    hardware_status = status;
    hardware_calls = 0;
    software_calls = 0;
}

int main(void)
{
    const protected_rpc_endpoint_t endpoint = {.opaque = 7};
    const protected_rpc_message_t request = {.length = 1, .words = {42}};
    protected_rpc_call_result_t result;
    protected_rpc_call_options_t options = {.route = PROTECTED_RPC_ROUTE_AUTO};

    reset(PROTECTED_RPC_ATTEMPT_COMPLETED, PROTECTED_RPC_OK);
    assert(protected_rpc_call(endpoint, &request, &options, &result)
           == PROTECTED_RPC_OK);
    assert(hardware_calls == 1 && software_calls == 0);
    assert(result.path == PROTECTED_RPC_PATH_HARDWARE);
    assert(result.reply.words[0] == 0x48415244);

    reset(PROTECTED_RPC_ATTEMPT_FALLBACK_SAFE, PROTECTED_RPC_UNSUPPORTED);
    assert(protected_rpc_call(endpoint, &request, &options, &result)
           == PROTECTED_RPC_OK);
    assert(hardware_calls == 1 && software_calls == 1);
    assert(result.path == PROTECTED_RPC_PATH_SOFTWARE);
    assert(result.reply.words[0] == 0x534f4654);

    reset(PROTECTED_RPC_ATTEMPT_REJECTED, PROTECTED_RPC_DENIED);
    assert(protected_rpc_call(endpoint, &request, &options, &result)
           == PROTECTED_RPC_DENIED);
    assert(hardware_calls == 1 && software_calls == 0);

    reset(PROTECTED_RPC_ATTEMPT_COMMITTED_FAILED,
          PROTECTED_RPC_SERVER_FAULT);
    assert(protected_rpc_call(endpoint, &request, &options, &result)
           == PROTECTED_RPC_SERVER_FAULT);
    assert(hardware_calls == 1 && software_calls == 0);

    options.route = PROTECTED_RPC_ROUTE_HARDWARE;
    reset(PROTECTED_RPC_ATTEMPT_FALLBACK_SAFE, PROTECTED_RPC_UNSUPPORTED);
    assert(protected_rpc_call(endpoint, &request, &options, &result)
           == PROTECTED_RPC_UNSUPPORTED);
    assert(hardware_calls == 1 && software_calls == 0);

    reset(PROTECTED_RPC_ATTEMPT_FALLBACK_SAFE, PROTECTED_RPC_REVOKED);
    assert(protected_rpc_call(endpoint, &request, &options, &result)
           == PROTECTED_RPC_REVOKED);
    assert(hardware_calls == 1 && software_calls == 0);
    assert(result.path == PROTECTED_RPC_PATH_HARDWARE);

    options.route = PROTECTED_RPC_ROUTE_SOFTWARE;
    reset(PROTECTED_RPC_ATTEMPT_COMPLETED, PROTECTED_RPC_OK);
    assert(protected_rpc_call(endpoint, &request, &options, &result)
           == PROTECTED_RPC_OK);
    assert(hardware_calls == 0 && software_calls == 1);

    protected_rpc_message_t invalid = request;
    invalid.length = PROTECTED_RPC_MAX_WORDS + 1;
    reset(PROTECTED_RPC_ATTEMPT_COMPLETED, PROTECTED_RPC_OK);
    assert(protected_rpc_call(endpoint, &invalid, &options, &result)
           == PROTECTED_RPC_INVALID_ARGUMENT);
    assert(hardware_calls == 0 && software_calls == 0);

    return 0;
}
