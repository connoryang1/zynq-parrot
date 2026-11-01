#ifndef SEL4_RPC_SEARCH_SERVICE_H
#define SEL4_RPC_SEARCH_SERVICE_H

#include "protected_rpc.h"

#define SEL4_RPC_SEARCH_BYTES 1024u
#define SEL4_RPC_SEARCH_NEEDLE 'z'
#define SEL4_RPC_SEARCH_CALLER_BADGE UINT64_C(0x5e1a)
#define SEL4_RPC_SEARCH_WARMUP_CALLS 8u
#define SEL4_RPC_SEARCH_MEASURED_CALLS 256u
#define SEL4_RPC_SEARCH_DISTRIBUTION_CALLS 64u
#define SEL4_RPC_SEARCH_L1D_COLD_CALLS 64u
#define SEL4_RPC_SEARCH_HIERARCHY_COLD_CALLS 64u
#define SEL4_RPC_SEARCH_NOTIFICATION_REQUESTS \
    (SEL4_RPC_SEARCH_WARMUP_CALLS + SEL4_RPC_SEARCH_MEASURED_CALLS \
     + SEL4_RPC_SEARCH_DISTRIBUTION_CALLS \
     + SEL4_RPC_SEARCH_L1D_COLD_CALLS \
     + SEL4_RPC_SEARCH_HIERARCHY_COLD_CALLS)
#define SEL4_RPC_SEARCH_FALLBACK_CALLS 8u
#define SEL4_RPC_SEARCH_SOFTWARE_REQUESTS \
    (SEL4_RPC_SEARCH_WARMUP_CALLS + SEL4_RPC_SEARCH_MEASURED_CALLS \
     + SEL4_RPC_SEARCH_DISTRIBUTION_CALLS \
     + SEL4_RPC_SEARCH_L1D_COLD_CALLS \
     + SEL4_RPC_SEARCH_HIERARCHY_COLD_CALLS \
     + SEL4_RPC_SEARCH_FALLBACK_CALLS)

/* Notifications carry only a badge, so the comparison transport uses this
 * explicitly shared request/reply mailbox. It is a baseline, not the protected
 * RPC ABI: both processes can modify it and sequence numbers provide only
 * protocol integrity, not authority. */
typedef struct {
    uint64_t request_sequence;
    uint64_t request_length;
    uint64_t request_words[PROTECTED_RPC_MAX_WORDS];
    uint64_t reply_sequence;
    uint64_t reply_length;
    uint64_t reply_words[PROTECTED_RPC_MAX_WORDS];
    uint64_t status;
} sel4_rpc_notification_mailbox_t;

protected_rpc_status_t sel4_rpc_bounded_search_service(
    const protected_rpc_call_context_t *context,
    const protected_rpc_message_t *request,
    protected_rpc_message_t *reply,
    void *cookie);

#endif
