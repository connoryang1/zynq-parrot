#include <assert.h>
#include <stddef.h>
#include <stdint.h>

#include "blackparrot_rpc_abi.h"

int main(void)
{
    bp_rpc_descriptor_v1_t descriptor = {
        .version = BP_RPC_ABI_VERSION,
        .size = BP_RPC_DESCRIPTOR_V1_SIZE,
        .slot = 0,
        .request_words = BP_RPC_MAX_WORDS,
        .reply_words = BP_RPC_MAX_WORDS,
        .token = UINT64_C(0x123456789abcdef0),
        .caller_satp = UINT64_C(0x8000000000080200),
        .server_satp = UINT64_C(0x8000000000080300),
        .server_entry = UINT64_C(0x10000),
        .server_sp = UINT64_C(0x20000),
        .caller_context = 0,
        .server_context = 1,
    };

    assert(sizeof(descriptor) == 112);
    assert(offsetof(bp_rpc_descriptor_v1_t, token) == 16);
    assert(offsetof(bp_rpc_descriptor_v1_t, caller_satp) == 24);
    assert(offsetof(bp_rpc_descriptor_v1_t, server_entry) == 40);
    assert(offsetof(bp_rpc_descriptor_v1_t, caller_badge) == 72);
    assert(descriptor.caller_satp != descriptor.server_satp);
    assert(descriptor.request_words <= BP_RPC_MAX_WORDS);
    assert(descriptor.reply_words <= BP_RPC_MAX_WORDS);
    assert(bp_rpc_descriptor_v1_valid(&descriptor));

    bp_rpc_descriptor_v1_t invalid = descriptor;
    invalid.token = 0;
    assert(!bp_rpc_descriptor_v1_valid(&invalid));
    invalid = descriptor;
    invalid.server_satp = invalid.caller_satp;
    assert(!bp_rpc_descriptor_v1_valid(&invalid));
    invalid = descriptor;
    invalid.server_entry |= 1;
    assert(!bp_rpc_descriptor_v1_valid(&invalid));
    invalid = descriptor;
    invalid.server_sp += 8;
    assert(!bp_rpc_descriptor_v1_valid(&invalid));
    invalid = descriptor;
    invalid.reserved1[2] = 1;
    assert(!bp_rpc_descriptor_v1_valid(&invalid));
    assert(BP_RPC_OUTCOME_NOT_STARTED != BP_RPC_OUTCOME_COMPLETED);
    assert(bp_rpc_control_word(BP_RPC_CONTROL_STAGE,
                               BP_RPC_FIELD_SERVER_ENTRY, 2)
           == UINT64_C(0x0003000000000002));
    assert(bp_rpc_control_word(BP_RPC_CONTROL_COMMIT,
                               BP_RPC_FIELD_TOKEN, 0)
           == UINT64_C(0x0100000000000000));
    assert(bp_rpc_prepare_word(BP_RPC_PREPARE_CSR, 0)
           == UINT64_C(0x0402000000000000));
    assert(bp_rpc_config_word(4, 4, 0, 1)
           == UINT64_C(0x0000000100000404));
    assert(bp_rpc_sel4_counts(4, 2) == UINT64_C(0x204));
    assert(BP_RPC_SEL4_BIND_LABEL != BP_RPC_SEL4_UNBIND_LABEL);
    assert(bp_rpc_sbi_extension_id(0) == UINT64_C(0x09000000));
    assert(bp_rpc_sbi_extension_id(UINT64_C(0x12345678))
           == UINT64_C(0x09345678));
    const uint64_t request_meta = bp_rpc_request_meta(3);
    assert(bp_rpc_request_meta_valid(request_meta));
    assert(bp_rpc_request_length(request_meta) == 3);
    assert(!bp_rpc_request_meta_valid(bp_rpc_request_meta(5)));
    assert(!bp_rpc_request_meta_valid(UINT64_C(1) << 8));
    const uint64_t meta = bp_rpc_reply_meta(4, 7);
    assert(bp_rpc_reply_meta_valid(meta));
    assert(bp_rpc_reply_length(meta) == 4);
    assert(bp_rpc_reply_status(meta) == 7);
    assert(!bp_rpc_reply_meta_valid(bp_rpc_reply_meta(5, 0)));
    assert(!bp_rpc_reply_meta_valid(UINT64_C(1) << 16));
    return 0;
}
