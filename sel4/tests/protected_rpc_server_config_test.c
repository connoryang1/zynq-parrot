#include <assert.h>
#include <stdint.h>
#include <string.h>

#include <sel4/sel4.h>

#include "protected_rpc.h"
#include "protected_rpc_runtime.h"

seL4_Word mock_sel4_mrs[16];
seL4_CPtr mock_sel4_caps[4];

static unsigned receive_calls;
static unsigned handler_calls;
static uint64_t seen_badge;
static unsigned handler_mode;

seL4_MessageInfo_t seL4_Call(seL4_CPtr endpoint, seL4_MessageInfo_t info)
{
    (void)endpoint;
    return info;
}

seL4_MessageInfo_t seL4_Recv(seL4_CPtr endpoint, seL4_Word *badge)
{
    (void)endpoint;
    (void)badge;
    receive_calls++;
    return seL4_MessageInfo_new(0, 0, 0, 0);
}

void seL4_Reply(seL4_MessageInfo_t info)
{
    (void)info;
}

seL4_MessageInfo_t seL4_ReplyRecv(
    seL4_CPtr endpoint, seL4_MessageInfo_t info, seL4_Word *badge)
{
    (void)endpoint;
    (void)badge;
    return info;
}

static protected_rpc_status_t handler(
    const protected_rpc_call_context_t *context,
    const protected_rpc_message_t *request,
    protected_rpc_message_t *reply,
    void *cookie)
{
    (void)request;
    (void)cookie;
    handler_calls++;
    seen_badge = protected_rpc_caller_badge(context);
    reply->length = 1;
    reply->words[0] = UINT64_C(0x7265706c79);
    if (handler_mode == 1) {
        reply->length = PROTECTED_RPC_MAX_WORDS + 1;
    } else if (handler_mode == 2) {
        return (protected_rpc_status_t)(PROTECTED_RPC_BACKEND_ERROR + 1);
    }
    return PROTECTED_RPC_OK;
}

static void poison_view(protected_rpc_buffer_view_t *view)
{
    view->data = (void *)(uintptr_t)UINT64_C(0xa5a5);
    view->length = UINT64_C(0xa5a5a5a5);
}

static void assert_view_cleared(const protected_rpc_buffer_view_t *view)
{
    assert(view->data == NULL);
    assert(view->length == 0);
}

static void assert_bad_region(protected_rpc_region_binding_t region)
{
    const protected_rpc_server_config_t config = {
        .handler = handler,
        .regions = &region,
        .region_count = 1,
    };
    const protected_rpc_call_context_t context = {
        .server_config = &config,
    };
    const protected_rpc_buffer_ref_t ref = {
        .region = region.region,
    };
    protected_rpc_buffer_view_t view;
    protected_rpc_message_t request = {0};
    protected_rpc_message_t reply;

    poison_view(&view);
    assert(protected_rpc_resolve_buffer(
               &context, ref, PROTECTED_RPC_ACCESS_READ, &view)
           == PROTECTED_RPC_BACKEND_ERROR);
    assert_view_cleared(&view);

    memset(&reply, 0xa5, sizeof(reply));
    handler_calls = 0;
    assert(protected_rpc_dispatch(&config, 9, &request, &reply)
           == PROTECTED_RPC_INVALID_ARGUMENT);
    assert(handler_calls == 0);
    assert(reply.length == 0);
    assert(reply.words[0] == 0);

    receive_calls = 0;
    assert(protected_rpc_serve(
               (protected_rpc_endpoint_t){.opaque = 1}, &config)
           == PROTECTED_RPC_INVALID_ARGUMENT);
    assert(receive_calls == 0);
}

int main(void)
{
    assert(protected_rpc_caller_badge(NULL) == 0);
    uint8_t data[16];
    const protected_rpc_region_binding_t region = {
        .region = {.opaque = 7},
        .local_base = data,
        .size = sizeof(data),
        .access = PROTECTED_RPC_ACCESS_READ | PROTECTED_RPC_ACCESS_WRITE,
    };
    const protected_rpc_server_config_t config = {
        .handler = handler,
        .regions = &region,
        .region_count = 1,
    };
    const protected_rpc_call_context_t context = {
        .server_config = &config,
    };
    protected_rpc_buffer_view_t view;
    protected_rpc_buffer_ref_t ref = {
        .region = {.opaque = 7},
        .offset = 4,
        .length = 5,
    };
    protected_rpc_message_t request = {0};
    protected_rpc_message_t reply;

    handler_mode = 0;
    handler_calls = 0;
    memset(&reply, 0xa5, sizeof(reply));
    assert(protected_rpc_dispatch(
               &config, UINT64_C(0x1234), &request, &reply)
           == PROTECTED_RPC_OK);
    assert(handler_calls == 1);
    assert(seen_badge == UINT64_C(0x1234));
    assert(reply.length == 1);
    assert(reply.words[0] == UINT64_C(0x7265706c79));
    assert(reply.words[1] == 0);

    request.length = PROTECTED_RPC_MAX_WORDS + 1;
    handler_calls = 0;
    memset(&reply, 0xa5, sizeof(reply));
    assert(protected_rpc_dispatch(&config, 0, &request, &reply)
           == PROTECTED_RPC_INVALID_ARGUMENT);
    assert(handler_calls == 0);
    assert(reply.length == 0);
    assert(reply.words[0] == 0);
    request.length = 0;

    handler_mode = 1;
    memset(&reply, 0xa5, sizeof(reply));
    assert(protected_rpc_dispatch(&config, 0, &request, &reply)
           == PROTECTED_RPC_BACKEND_ERROR);
    assert(reply.length == 0);
    assert(reply.words[0] == 0);

    handler_mode = 2;
    memset(&reply, 0xa5, sizeof(reply));
    assert(protected_rpc_dispatch(&config, 0, &request, &reply)
           == PROTECTED_RPC_BACKEND_ERROR);
    assert(reply.length == 0);
    assert(reply.words[0] == 0);
    handler_mode = 0;

    handler_calls = 0;
    assert(protected_rpc_dispatch(&config, 0, &request, NULL)
           == PROTECTED_RPC_INVALID_ARGUMENT);
    assert(handler_calls == 0);

    assert(protected_rpc_resolve_buffer(
               &context, ref, PROTECTED_RPC_ACCESS_WRITE, &view)
           == PROTECTED_RPC_OK);
    assert(view.data == &data[4]);
    assert(view.length == 5);

    ref.region.opaque = 8;
    poison_view(&view);
    assert(protected_rpc_resolve_buffer(
               &context, ref, PROTECTED_RPC_ACCESS_READ, &view)
           == PROTECTED_RPC_REVOKED);
    assert_view_cleared(&view);

    ref.region.opaque = 7;
    ref.offset = 15;
    ref.length = 2;
    poison_view(&view);
    assert(protected_rpc_resolve_buffer(
               &context, ref, PROTECTED_RPC_ACCESS_READ, &view)
           == PROTECTED_RPC_INVALID_ARGUMENT);
    assert_view_cleared(&view);

    protected_rpc_region_binding_t read_only = region;
    read_only.access = PROTECTED_RPC_ACCESS_READ;
    protected_rpc_server_config_t read_only_config = config;
    read_only_config.regions = &read_only;
    protected_rpc_call_context_t read_only_context = context;
    read_only_context.server_config = &read_only_config;
    ref.offset = 0;
    ref.length = 1;
    poison_view(&view);
    assert(protected_rpc_resolve_buffer(
               &read_only_context, ref, PROTECTED_RPC_ACCESS_WRITE, &view)
           == PROTECTED_RPC_DENIED);
    assert_view_cleared(&view);

    protected_rpc_region_binding_t bad = region;
    bad.region.opaque = 0;
    assert_bad_region(bad);
    bad = region;
    bad.local_base = NULL;
    assert_bad_region(bad);
    bad = region;
    bad.size = 0;
    assert_bad_region(bad);
    bad = region;
    bad.access = 0;
    assert_bad_region(bad);
    bad = region;
    bad.access = PROTECTED_RPC_ACCESS_READ | (1u << 8);
    assert_bad_region(bad);
    bad = region;
    bad.local_base = (void *)(uintptr_t)(UINTPTR_MAX - 7u);
    bad.size = 8;
    assert_bad_region(bad);

    const protected_rpc_region_binding_t duplicates[2] = {region, region};
    protected_rpc_server_config_t duplicate_config = config;
    duplicate_config.regions = duplicates;
    duplicate_config.region_count = 2;
    protected_rpc_call_context_t duplicate_context = context;
    duplicate_context.server_config = &duplicate_config;
    poison_view(&view);
    assert(protected_rpc_resolve_buffer(
               &duplicate_context, ref, PROTECTED_RPC_ACCESS_READ, &view)
           == PROTECTED_RPC_BACKEND_ERROR);
    assert_view_cleared(&view);
    receive_calls = 0;
    assert(protected_rpc_serve(
               (protected_rpc_endpoint_t){.opaque = 1}, &duplicate_config)
           == PROTECTED_RPC_INVALID_ARGUMENT);
    assert(receive_calls == 0);

    receive_calls = 0;
    assert(protected_rpc_serve(
               (protected_rpc_endpoint_t){.opaque = 0}, &config)
           == PROTECTED_RPC_INVALID_ARGUMENT);
    assert(receive_calls == 0);
    return 0;
}
