#include <sel4/sel4.h>
#include <stdint.h>
#include <string.h>

#include "protected_rpc_backend.h"

static protected_rpc_status_t sel4_try_call(
    protected_rpc_endpoint_t endpoint,
    const protected_rpc_message_t *request,
    protected_rpc_attempt_result_t *result)
{
    result->path = PROTECTED_RPC_PATH_SOFTWARE;
    if (endpoint.opaque == 0 || !protected_rpc_message_valid(request)) {
        result->disposition = PROTECTED_RPC_ATTEMPT_REJECTED;
        result->status = PROTECTED_RPC_INVALID_ARGUMENT;
        return result->status;
    }

    for (size_t word = 0; word < request->length; word++) {
        seL4_SetMR((int)word, request->words[word]);
    }

    const seL4_MessageInfo_t info = seL4_Call(
        (seL4_CPtr)endpoint.opaque,
        seL4_MessageInfo_new(0, 0, 0, request->length));
    const seL4_Word reply_length = seL4_MessageInfo_get_length(info);
    const seL4_Word status = seL4_MessageInfo_get_label(info);

    if (reply_length > PROTECTED_RPC_MAX_WORDS
        || status > PROTECTED_RPC_BACKEND_ERROR) {
        result->disposition = PROTECTED_RPC_ATTEMPT_COMMITTED_FAILED;
        result->status = PROTECTED_RPC_BACKEND_ERROR;
        return result->status;
    }

    result->reply.length = (uint8_t)reply_length;
    for (size_t word = 0; word < reply_length; word++) {
        result->reply.words[word] = seL4_GetMR((int)word);
    }
    result->disposition = PROTECTED_RPC_ATTEMPT_COMPLETED;
    result->status = (protected_rpc_status_t)status;
    return result->status;
}

const protected_rpc_backend_t protected_rpc_software_backend = {
    .try_call = sel4_try_call,
};

protected_rpc_status_t protected_rpc_resolve_buffer(
    const protected_rpc_call_context_t *context,
    protected_rpc_buffer_ref_t ref,
    protected_rpc_access_t required_access,
    protected_rpc_buffer_view_t *view)
{
    if (context == NULL || context->runtime_private == NULL || view == NULL
        || required_access == 0
        || (required_access & ~(PROTECTED_RPC_ACCESS_READ
                                | PROTECTED_RPC_ACCESS_WRITE)) != 0) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }

    const protected_rpc_server_config_t *config = context->runtime_private;
    for (size_t index = 0; index < config->region_count; index++) {
        const protected_rpc_region_binding_t *binding = &config->regions[index];
        if (binding->region.opaque != ref.region.opaque) {
            continue;
        }
        if ((binding->access & required_access) != required_access) {
            return PROTECTED_RPC_DENIED;
        }
        if (!protected_rpc_buffer_range_valid(binding->size, &ref)) {
            return PROTECTED_RPC_INVALID_ARGUMENT;
        }

        view->data = (uint8_t *)binding->local_base + ref.offset;
        view->length = ref.length;
        return PROTECTED_RPC_OK;
    }
    return PROTECTED_RPC_REVOKED;
}

protected_rpc_status_t protected_rpc_serve(
    protected_rpc_endpoint_t endpoint,
    const protected_rpc_server_config_t *config)
{
    if (endpoint.opaque == 0 || config == NULL || config->handler == NULL
        || (config->region_count != 0 && config->regions == NULL)) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }

    seL4_Word badge = 0;
    seL4_MessageInfo_t info = seL4_Recv((seL4_CPtr)endpoint.opaque, &badge);
    uint64_t handled = 0;

    for (;;) {
        protected_rpc_message_t request;
        protected_rpc_message_t reply;
        memset(&request, 0, sizeof(request));
        memset(&reply, 0, sizeof(reply));

        const seL4_Word request_length = seL4_MessageInfo_get_length(info);
        protected_rpc_status_t status = PROTECTED_RPC_INVALID_ARGUMENT;
        if (request_length <= PROTECTED_RPC_MAX_WORDS) {
            request.length = (uint8_t)request_length;
            for (size_t word = 0; word < request_length; word++) {
                request.words[word] = seL4_GetMR((int)word);
            }

            const protected_rpc_call_context_t context = {
                .caller_badge = badge,
                .runtime_private = (void *)config,
            };
            status = config->handler(&context, &request, &reply,
                                     config->cookie);
            if (!protected_rpc_message_valid(&reply)) {
                memset(&reply, 0, sizeof(reply));
                status = PROTECTED_RPC_BACKEND_ERROR;
            }
        }

        for (size_t word = 0; word < reply.length; word++) {
            seL4_SetMR((int)word, reply.words[word]);
        }
        const seL4_MessageInfo_t reply_info = seL4_MessageInfo_new(
            status, 0, 0, reply.length);

        handled++;
        if (config->max_requests != 0 && handled >= config->max_requests) {
            seL4_Reply(reply_info);
            return PROTECTED_RPC_OK;
        }
        info = seL4_ReplyRecv((seL4_CPtr)endpoint.opaque, reply_info, &badge);
    }
}
