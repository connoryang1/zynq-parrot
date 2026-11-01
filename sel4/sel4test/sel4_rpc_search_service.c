#include <stdint.h>
#include <string.h>

#include "sel4_rpc_search_service.h"

protected_rpc_status_t sel4_rpc_bounded_search_service(
    const protected_rpc_call_context_t *context,
    const protected_rpc_message_t *request,
    protected_rpc_message_t *reply,
    void *cookie)
{
    (void)cookie;
    protected_rpc_buffer_ref_t ref;
    protected_rpc_buffer_view_t view;
    if (request->length != 4
        || !protected_rpc_decode_buffer(request, 0, &ref)
        || request->words[3] > UINT8_MAX) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }
    protected_rpc_status_t status = protected_rpc_resolve_buffer(
        context, ref, PROTECTED_RPC_ACCESS_READ, &view);
    if (status != PROTECTED_RPC_OK) {
        return status;
    }

    const unsigned char *bytes = view.data;
    const unsigned char *match = memchr(
        bytes, (int)request->words[3], (size_t)view.length);
    const unsigned char *terminator = memchr(bytes, 0, (size_t)view.length);
    reply->length = 2;
    reply->words[0] = match == NULL ? view.length
                                    : (uint64_t)(match - bytes);
    reply->words[1] = terminator == NULL ? view.length
                                         : (uint64_t)(terminator - bytes);
    return PROTECTED_RPC_OK;
}
