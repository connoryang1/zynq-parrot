#ifndef BLACKPARROT_RPC_ABI_H
#define BLACKPARROT_RPC_ABI_H

#include <stddef.h>
#include <stdint.h>

/* Private seL4/OpenSBI/BlackParrot boundary; not an application API. */
#define BP_RPC_ABI_VERSION 1u
#define BP_RPC_DESCRIPTOR_V1_SIZE 112u
#define BP_RPC_MAX_WORDS 4u
#define BP_RPC_REPLY_META_LENGTH_MASK UINT64_C(0xff)
#define BP_RPC_REPLY_META_STATUS_SHIFT 8u
#define BP_RPC_REPLY_META_STATUS_MASK (UINT64_C(0xff) << BP_RPC_REPLY_META_STATUS_SHIFT)

typedef enum {
    BP_RPC_OUTCOME_COMPLETED = 0,
    BP_RPC_OUTCOME_NOT_STARTED = 1,
    BP_RPC_OUTCOME_REVOKED = 2,
    BP_RPC_OUTCOME_COMMITTED_FAILED = 3,
} bp_rpc_outcome_t;

typedef enum {
    BP_RPC_CONTROL_INSTALL = 0,
    BP_RPC_CONTROL_REVOKE = 1,
    BP_RPC_CONTROL_QUERY = 2,
} bp_rpc_control_operation_t;

typedef enum {
    BP_RPC_CONTROL_OK = 0,
    BP_RPC_CONTROL_STALE = 1,
    BP_RPC_CONTROL_BUSY = 2,
    BP_RPC_CONTROL_UNSUPPORTED = 3,
    BP_RPC_CONTROL_INVALID = 4,
} bp_rpc_control_status_t;

/*
 * Fixed little-endian RV64 image copied by the M-mode installer before the
 * descriptor becomes visible. Reserved fields and flags must be zero.
 */
typedef struct {
    uint32_t version;
    uint16_t size;
    uint16_t flags;

    uint32_t slot;
    uint8_t request_words;
    uint8_t reply_words;
    uint16_t reserved0;

    uint64_t token;
    uint64_t caller_satp;
    uint64_t server_satp;
    uint64_t server_entry;
    uint64_t server_sp;
    uint64_t server_gp;
    uint64_t server_tp;
    uint64_t caller_badge;

    uint32_t caller_context;
    uint32_t server_context;
    uint64_t reserved1[3];
} bp_rpc_descriptor_v1_t;

static inline uint64_t bp_rpc_reply_meta(uint8_t length, uint8_t status)
{
    return (uint64_t)length
           | ((uint64_t)status << BP_RPC_REPLY_META_STATUS_SHIFT);
}

static inline uint8_t bp_rpc_reply_length(uint64_t meta)
{
    return (uint8_t)(meta & BP_RPC_REPLY_META_LENGTH_MASK);
}

static inline uint8_t bp_rpc_reply_status(uint64_t meta)
{
    return (uint8_t)((meta & BP_RPC_REPLY_META_STATUS_MASK)
                     >> BP_RPC_REPLY_META_STATUS_SHIFT);
}

static inline int bp_rpc_reply_meta_valid(uint64_t meta)
{
    return (meta & ~(BP_RPC_REPLY_META_LENGTH_MASK
                     | BP_RPC_REPLY_META_STATUS_MASK)) == 0
           && bp_rpc_reply_length(meta) <= BP_RPC_MAX_WORDS;
}

#if defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
_Static_assert(sizeof(bp_rpc_descriptor_v1_t) == BP_RPC_DESCRIPTOR_V1_SIZE,
               "protected-RPC descriptor ABI size changed");
_Static_assert(offsetof(bp_rpc_descriptor_v1_t, token) == 16,
               "protected-RPC token ABI offset changed");
_Static_assert(offsetof(bp_rpc_descriptor_v1_t, caller_satp) == 24,
               "protected-RPC caller SATP ABI offset changed");
_Static_assert(offsetof(bp_rpc_descriptor_v1_t, server_entry) == 40,
               "protected-RPC entry ABI offset changed");
_Static_assert(offsetof(bp_rpc_descriptor_v1_t, caller_badge) == 72,
               "protected-RPC badge ABI offset changed");
#endif

#endif
