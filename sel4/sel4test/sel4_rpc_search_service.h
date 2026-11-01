#ifndef SEL4_RPC_SEARCH_SERVICE_H
#define SEL4_RPC_SEARCH_SERVICE_H

#include "protected_rpc.h"

#define SEL4_RPC_SEARCH_BYTES 1024u
#define SEL4_RPC_SEARCH_NEEDLE 'z'
#define SEL4_RPC_SEARCH_WARMUP_CALLS 8u
#define SEL4_RPC_SEARCH_MEASURED_CALLS 256u
#define SEL4_RPC_SEARCH_DISTRIBUTION_CALLS 64u
#define SEL4_RPC_SEARCH_FALLBACK_CALLS 8u
#define SEL4_RPC_SEARCH_SOFTWARE_REQUESTS \
    (SEL4_RPC_SEARCH_WARMUP_CALLS + SEL4_RPC_SEARCH_MEASURED_CALLS \
     + SEL4_RPC_SEARCH_DISTRIBUTION_CALLS \
     + SEL4_RPC_SEARCH_FALLBACK_CALLS)

protected_rpc_status_t sel4_rpc_bounded_search_service(
    const protected_rpc_call_context_t *context,
    const protected_rpc_message_t *request,
    protected_rpc_message_t *reply,
    void *cookie);

#endif
