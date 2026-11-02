#ifndef BLACKPARROT_RPC_ABI_H
#define BLACKPARROT_RPC_ABI_H

#include <stdint.h>

/* seL4's freestanding stdint.h provides the types but not this C99 macro. */
#ifndef UINT64_C
#define UINT64_C(value) value##ULL
#endif

/* Private seL4/OpenSBI/BlackParrot boundary; not an application API. */
#define BP_RPC_ABI_VERSION_V1 1u
#define BP_RPC_ABI_VERSION_V2 2u
#define BP_RPC_ABI_VERSION BP_RPC_ABI_VERSION_V1
#define BP_RPC_DESCRIPTOR_V1_SIZE 112u
#define BP_RPC_DESCRIPTOR_V2_SIZE BP_RPC_DESCRIPTOR_V1_SIZE
#define BP_RPC_DESCRIPTOR_FLAG_FAULT_COMPLETION (1u << 0)
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
#define BP_RPC_FAILURE_META_CLASS_MASK UINT64_C(0xff)
#define BP_RPC_SEL4_BIND_LABEL UINT64_C(0x42505201)
#define BP_RPC_SEL4_UNBIND_LABEL UINT64_C(0x42505202)
#define BP_RPC_SEL4_BIND_ARGUMENTS 5u
#define BP_RPC_SEL4_BIND_REGION_ARGUMENTS 10u
#define BP_RPC_REGION_ACCESS_READ (1u << 0)
#define BP_RPC_REGION_ACCESS_WRITE (1u << 1)

typedef enum {
    BP_RPC_OUTCOME_COMPLETED = 0,
    BP_RPC_OUTCOME_NOT_STARTED = 1,
    BP_RPC_OUTCOME_REVOKED = 2,
    BP_RPC_OUTCOME_COMMITTED_FAILED = 3,
} bp_rpc_outcome_t;

/* a5 when the call outcome is COMMITTED_FAILED. Zero is the version-1
 * unspecified failure and maps fail-closed to BACKEND_ERROR. */
typedef enum {
    BP_RPC_FAILURE_UNSPECIFIED = 0,
    BP_RPC_FAILURE_SERVER_FAULT = 1,
    BP_RPC_FAILURE_CANCELED = 2,
    BP_RPC_FAILURE_BACKEND_ERROR = 3,
} bp_rpc_failure_class_t;

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
    BP_RPC_CONTROL_PREPARE = 4,
} bp_rpc_control_command_t;

typedef enum {
    BP_RPC_PREPARE_GPR_LINE0 = 0,
    BP_RPC_PREPARE_GPR_LINE1 = 1,
    BP_RPC_PREPARE_CSR = 2,
    BP_RPC_PREPARE_COMPONENTS = 3,
} bp_rpc_prepare_component_t;

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
#define BP_RPC_CONFIG_FAULT_COMPLETION_SHIFT 48u
#define BP_RPC_CONFIG_FAULT_COMPLETION \
    (UINT64_C(1) << BP_RPC_CONFIG_FAULT_COMPLETION_SHIFT)

static inline uint64_t bp_rpc_control_word(
    bp_rpc_control_command_t command, bp_rpc_descriptor_field_t field,
    uint32_t slot)
{
    return ((uint64_t)command << BP_RPC_CONTROL_COMMAND_SHIFT)
           | ((uint64_t)field << BP_RPC_CONTROL_FIELD_SHIFT)
           | (uint64_t)slot;
}

static inline uint64_t bp_rpc_prepare_word(
    bp_rpc_prepare_component_t component, uint32_t slot)
{
    return ((uint64_t)BP_RPC_CONTROL_PREPARE << BP_RPC_CONTROL_COMMAND_SHIFT)
           | ((uint64_t)component << BP_RPC_CONTROL_FIELD_SHIFT)
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

static inline uint64_t bp_rpc_config_word_v2(
    uint8_t request_words, uint8_t reply_words, uint16_t caller_context,
    uint16_t server_context)
{
    return bp_rpc_config_word(request_words, reply_words, caller_context,
                              server_context)
           | BP_RPC_CONFIG_FAULT_COMPLETION;
}

static inline uint64_t bp_rpc_sel4_counts(uint8_t request_words,
                                          uint8_t reply_words)
{
    return (uint64_t)request_words | ((uint64_t)reply_words << 8);
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

/* Version 2 deliberately preserves the installation-image size and offsets.
 * Its required flag opts into synchronous-fault completion. */
typedef bp_rpc_descriptor_v1_t bp_rpc_descriptor_v2_t;

static inline int bp_rpc_user_address_valid(uint64_t address)
{
    /* Version 1 admits only the positive Sv39 user half. */
    return address < (UINT64_C(1) << 38);
}

static inline int bp_rpc_descriptor_fields_valid(
    const bp_rpc_descriptor_v1_t *descriptor)
{
    if (descriptor == (void *)0
        || descriptor->size != BP_RPC_DESCRIPTOR_V1_SIZE
        || descriptor->slot != 0
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
    for (unsigned int index = 0; index < 3; index++) {
        if (descriptor->reserved1[index] != 0) {
            return 0;
        }
    }
    return 1;
}

static inline int bp_rpc_descriptor_v1_valid(
    const bp_rpc_descriptor_v1_t *descriptor)
{
    return descriptor != (void *)0
           && descriptor->version == BP_RPC_ABI_VERSION_V1
           && descriptor->flags == 0
           && bp_rpc_descriptor_fields_valid(descriptor);
}

static inline int bp_rpc_descriptor_v2_valid(
    const bp_rpc_descriptor_v2_t *descriptor)
{
    return descriptor != (void *)0
           && descriptor->version == BP_RPC_ABI_VERSION_V2
           && descriptor->flags == BP_RPC_DESCRIPTOR_FLAG_FAULT_COMPLETION
           && bp_rpc_descriptor_fields_valid(descriptor);
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

static inline uint64_t bp_rpc_failure_meta(bp_rpc_failure_class_t failure)
{
    return (uint64_t)failure;
}

static inline bp_rpc_failure_class_t bp_rpc_failure_class(uint64_t meta)
{
    return (bp_rpc_failure_class_t)(meta & BP_RPC_FAILURE_META_CLASS_MASK);
}

static inline int bp_rpc_failure_meta_valid(uint64_t meta)
{
    return (meta & ~BP_RPC_FAILURE_META_CLASS_MASK) == 0
           && bp_rpc_failure_class(meta) <= BP_RPC_FAILURE_BACKEND_ERROR;
}

#if defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
#include <stddef.h>
_Static_assert(sizeof(bp_rpc_descriptor_v1_t) == BP_RPC_DESCRIPTOR_V1_SIZE,
               "protected-RPC descriptor ABI size changed");
_Static_assert(sizeof(bp_rpc_descriptor_v2_t) == BP_RPC_DESCRIPTOR_V2_SIZE,
               "protected-RPC v2 descriptor ABI size changed");
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
