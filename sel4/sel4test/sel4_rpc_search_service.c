#include <stdint.h>
#include <string.h>
#include <sel4/config.h>

#include "sel4_rpc_search_service.h"

static inline uint64_t search_read_cycles(void)
{
    uint64_t value;
#ifdef CONFIG_PLAT_BLACKPARROT
    /* rdcycle is intentionally unavailable in the clean protected-server CSR
     * image. BlackParrot's 0xCC0 counter is core-wide and is therefore also
     * the correct common timebase across caller/server context transitions. */
    __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
#else
    __asm__ volatile("rdcycle %0" : "=r"(value) : : "memory");
#endif
    return value;
}

protected_rpc_status_t sel4_rpc_bounded_search_service(
    const protected_rpc_call_context_t *context,
    const protected_rpc_message_t *request,
    protected_rpc_message_t *reply,
    void *cookie)
{
    if (context == NULL
        || (cookie != NULL
            && context->caller_badge != *(const uint64_t *)cookie)) {
        return PROTECTED_RPC_DENIED;
    }
    const uint64_t service_entry_cycles = search_read_cycles();
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
    reply->length = 4;
    reply->words[0] = match == NULL ? view.length
                                    : (uint64_t)(match - bytes);
    reply->words[1] = terminator == NULL ? view.length
                                         : (uint64_t)(terminator - bytes);
    reply->words[2] = service_entry_cycles;
    reply->words[3] = search_read_cycles();
    return PROTECTED_RPC_OK;
}
