#ifndef BLACKPARROT_RPC_ABI_H
#define BLACKPARROT_RPC_ABI_H

#include <stddef.h>
#include <stdint.h>

/* Private seL4/OpenSBI/BlackParrot boundary; not an application API. */
#define BP_RPC_ABI_VERSION 1u
#define BP_RPC_DESCRIPTOR_V1_SIZE 112u
#define BP_RPC_MAX_WORDS 4u
#define BP_RPC_CSR_CALL 0x808
#define BP_RPC_CSR_RETURN 0x809
#define BP_RPC_CSR_M_DATA 0x7c3
#define BP_RPC_CSR_M_CONTROL 0x7c4
#define BP_RPC_SBI_VENDOR_BASE UINT64_C(0x09000000)
#define BP_RPC_SBI_VENDOR_MASK UINT64_C(0x00ffffff)
#define BP_RPC_REQUEST_META_LENGTH_MASK UINT64_C(0xff)
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
    BP_RPC_SBI_INSTALL = 0,
    BP_RPC_SBI_REVOKE = 1,
    BP_RPC_SBI_QUERY = 2,
} bp_rpc_sbi_operation_t;

static inline uint64_t bp_rpc_sbi_extension_id(uint64_t mvendorid)
{
    return BP_RPC_SBI_VENDOR_BASE | (mvendorid & BP_RPC_SBI_VENDOR_MASK);
}

typedef enum {
    BP_RPC_CONTROL_OK = 0,
    BP_RPC_CONTROL_STALE = 1,
    BP_RPC_CONTROL_BUSY = 2,
    BP_RPC_CONTROL_UNSUPPORTED = 3,
    BP_RPC_CONTROL_INVALID = 4,
} bp_rpc_control_status_t;

typedef enum {
    BP_RPC_CONTROL_STAGE = 0,
    BP_RPC_CONTROL_COMMIT = 1,
    BP_RPC_CONTROL_REVOKE = 2,
    BP_RPC_CONTROL_READ_STATUS = 3,
} bp_rpc_control_command_t;

typedef enum {
    BP_RPC_FIELD_TOKEN = 0,
    BP_RPC_FIELD_CALLER_SATP = 1,
    BP_RPC_FIELD_SERVER_SATP = 2,
    BP_RPC_FIELD_SERVER_ENTRY = 3,
    BP_RPC_FIELD_SERVER_SP = 4,
    BP_RPC_FIELD_SERVER_GP = 5,
    BP_RPC_FIELD_SERVER_TP = 6,
    BP_RPC_FIELD_CALLER_BADGE = 7,
    BP_RPC_FIELD_CONFIG = 8,
} bp_rpc_descriptor_field_t;

#define BP_RPC_CONTROL_COMMAND_SHIFT 56u
#define BP_RPC_CONTROL_FIELD_SHIFT 48u
#define BP_RPC_CONTROL_SLOT_MASK UINT64_C(0xffffffff)
#define BP_RPC_CONFIG_REQUEST_WORDS_SHIFT 0u
#define BP_RPC_CONFIG_REPLY_WORDS_SHIFT 8u
#define BP_RPC_CONFIG_CALLER_CONTEXT_SHIFT 16u
#define BP_RPC_CONFIG_SERVER_CONTEXT_SHIFT 32u

static inline uint64_t bp_rpc_control_word(
    bp_rpc_control_command_t command, bp_rpc_descriptor_field_t field,
    uint32_t slot)
{
    return ((uint64_t)command << BP_RPC_CONTROL_COMMAND_SHIFT)
           | ((uint64_t)field << BP_RPC_CONTROL_FIELD_SHIFT)
           | (uint64_t)slot;
}

static inline uint64_t bp_rpc_config_word(
    uint8_t request_words, uint8_t reply_words, uint16_t caller_context,
    uint16_t server_context)
{
    return ((uint64_t)request_words << BP_RPC_CONFIG_REQUEST_WORDS_SHIFT)
           | ((uint64_t)reply_words << BP_RPC_CONFIG_REPLY_WORDS_SHIFT)
           | ((uint64_t)caller_context << BP_RPC_CONFIG_CALLER_CONTEXT_SHIFT)
           | ((uint64_t)server_context << BP_RPC_CONFIG_SERVER_CONTEXT_SHIFT);
}

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

static inline int bp_rpc_user_address_valid(uint64_t address)
{
    /* Version 1 admits only the positive Sv39 user half. */
    return address < (UINT64_C(1) << 38);
}

static inline int bp_rpc_descriptor_v1_valid(
    const bp_rpc_descriptor_v1_t *descriptor)
{
    if (descriptor == NULL
        || descriptor->version != BP_RPC_ABI_VERSION
        || descriptor->size != BP_RPC_DESCRIPTOR_V1_SIZE
        || descriptor->flags != 0 || descriptor->slot != 0
        || descriptor->request_words > BP_RPC_MAX_WORDS
        || descriptor->reply_words > BP_RPC_MAX_WORDS
        || descriptor->reserved0 != 0 || descriptor->token == 0
        || descriptor->caller_context != 0
        || descriptor->server_context != 1
        || descriptor->caller_satp == descriptor->server_satp
        || descriptor->caller_satp >> 60 != 8
        || descriptor->server_satp >> 60 != 8
        || descriptor->server_entry == 0
        || !bp_rpc_user_address_valid(descriptor->server_entry)
        || (descriptor->server_entry & 1) != 0
        || descriptor->server_sp == 0
        || !bp_rpc_user_address_valid(descriptor->server_sp)
        || (descriptor->server_sp & 15) != 0
        || !bp_rpc_user_address_valid(descriptor->server_gp)
        || !bp_rpc_user_address_valid(descriptor->server_tp)) {
        return 0;
    }
    for (size_t index = 0; index < 3; index++) {
        if (descriptor->reserved1[index] != 0) {
            return 0;
        }
    }
    return 1;
}

static inline uint64_t bp_rpc_request_meta(uint8_t length)
{
    return (uint64_t)length;
}

static inline uint8_t bp_rpc_request_length(uint64_t meta)
{
    return (uint8_t)(meta & BP_RPC_REQUEST_META_LENGTH_MASK);
}

static inline int bp_rpc_request_meta_valid(uint64_t meta)
{
    return (meta & ~BP_RPC_REQUEST_META_LENGTH_MASK) == 0
           && bp_rpc_request_length(meta) <= BP_RPC_MAX_WORDS;
}

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
