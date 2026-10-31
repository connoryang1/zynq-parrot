#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "protected_rpc.h"

int main(void)
{
    protected_rpc_message_t message;
    memset(&message, 0, sizeof(message));

    const protected_rpc_buffer_ref_t input = {
        .region = {.opaque = UINT64_C(0x12340007)},
        .offset = 4088,
        .length = 8,
    };
    protected_rpc_buffer_ref_t output;

    assert(protected_rpc_encode_buffer(&message, 1, input));
    assert(message.length == 4);
    assert(protected_rpc_decode_buffer(&message, 1, &output));
    assert(output.region.opaque == input.region.opaque);
    assert(output.offset == input.offset);
    assert(output.length == input.length);
    assert(protected_rpc_buffer_range_valid(4096, &output));

    output.offset = 4089;
    assert(!protected_rpc_buffer_range_valid(4096, &output));
    output.offset = UINT64_MAX - 3;
    output.length = 8;
    assert(!protected_rpc_buffer_range_valid(UINT64_MAX, &output));

    assert(!protected_rpc_encode_buffer(&message, 2, input));
    message.length = 3;
    assert(!protected_rpc_decode_buffer(&message, 1, &output));
    message.length = PROTECTED_RPC_MAX_WORDS + 1;
    assert(!protected_rpc_message_valid(&message));
    return 0;
}
