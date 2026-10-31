/*
 * Exercise the backend-neutral protected-RPC API through ordinary seL4 IPC.
 * The same handler body is intended to be reused by the hardware backend.
 */

#include <inttypes.h>
#include <stdio.h>
#include <sel4/sel4.h>
#include <sel4utils/process.h>
#include <vka/capops.h>
#include <vka/object.h>
#include <vspace/vspace.h>

#include "protected_rpc.h"
#ifdef CONFIG_PLAT_BLACKPARROT
#include "protected_rpc_blackparrot.h"
#endif
#include "../helpers.h"

#define ADAPTER_WARMUP_CALLS 8
#define ADAPTER_MEASURED_CALLS 256
#define ADAPTER_VALID_CALLS (ADAPTER_WARMUP_CALLS + ADAPTER_MEASURED_CALLS)
#define ADAPTER_TOTAL_SERVER_CALLS (ADAPTER_VALID_CALLS + 2)
#define ADAPTER_REGION_TOKEN UINT64_C(0xa11ce001)

static volatile seL4_Word adapter_server_private_counter;

#ifdef CONFIG_PLAT_BLACKPARROT
static void __attribute__((naked, noinline, used, aligned(64)))
hardware_sum_entry(void)
{
    __asm__ volatile(
        ".option push\n.option norvc\n"
        "add a0, a0, a1\n"
        "add a0, a0, a2\n"
        "add a0, a0, a3\n"
        /* One reply word and PROTECTED_RPC_OK status. */
        "li a5, 1\n"
        "csrw 0x809, a0\n"
        "1: j 1b\n"
        ".option pop\n");
}

static inline uint64_t read_cycles(void)
{
    uint64_t value;
    __asm__ volatile("rdcycle %0" : "=r"(value));
    return value;
}

static protected_rpc_status_t buffer_service(
    const protected_rpc_call_context_t *context,
    const protected_rpc_message_t *request,
    protected_rpc_message_t *reply,
    void *cookie)
{
    (void)cookie;
    protected_rpc_buffer_ref_t ref;
    protected_rpc_buffer_view_t view;
    if (request->length != 4
        || !protected_rpc_decode_buffer(request, 0, &ref)) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }

    protected_rpc_status_t status = protected_rpc_resolve_buffer(
        context, ref,
        PROTECTED_RPC_ACCESS_READ | PROTECTED_RPC_ACCESS_WRITE, &view);
    if (status != PROTECTED_RPC_OK) {
        return status;
    }
    if (view.length != sizeof(seL4_Word)) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }

    volatile seL4_Word *word = view.data;
    adapter_server_private_counter++;
    *word += request->words[3] + adapter_server_private_counter;
    reply->length = 2;
    reply->words[0] = *word;
    reply->words[1] = adapter_server_private_counter;
    return PROTECTED_RPC_OK;
}

static int adapter_server(seL4_Word endpoint, seL4_Word shared_base,
                          seL4_Word unused2, seL4_Word unused3)
{
    (void)unused2;
    (void)unused3;
    adapter_server_private_counter = 0;
    const protected_rpc_region_binding_t region = {
        .region = {.opaque = ADAPTER_REGION_TOKEN},
        .local_base = (void *)shared_base,
        .size = BIT(seL4_PageBits),
        .access = PROTECTED_RPC_ACCESS_READ | PROTECTED_RPC_ACCESS_WRITE,
    };
    const protected_rpc_server_config_t config = {
        .handler = buffer_service,
        .regions = &region,
        .region_count = 1,
        .max_requests = ADAPTER_TOTAL_SERVER_CALLS,
    };
    return protected_rpc_serve(
        (protected_rpc_endpoint_t){.opaque = endpoint}, &config);
}

static protected_rpc_status_t sum_service(
    const protected_rpc_call_context_t *context,
    const protected_rpc_message_t *request,
    protected_rpc_message_t *reply,
    void *cookie)
{
    (void)context;
    (void)cookie;
    if (request->length != 4) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }
    reply->length = 1;
    reply->words[0] = request->words[0] + request->words[1]
                      + request->words[2] + request->words[3];
    return PROTECTED_RPC_OK;
}

static int sum_server(seL4_Word endpoint, seL4_Word unused1,
                      seL4_Word unused2, seL4_Word unused3)
{
    (void)unused1;
    (void)unused2;
    (void)unused3;
    const protected_rpc_server_config_t config = {
        .handler = sum_service,
        .max_requests = 1,
    };
    return protected_rpc_serve(
        (protected_rpc_endpoint_t){.opaque = endpoint}, &config);
}

static int test_blackparrot_hardware_binding(env_t env)
{
    helper_thread_t server;
    cspacepath_t endpoint_path;
    seL4_CPtr endpoint = vka_alloc_endpoint_leaky(&env->vka);
    test_assert(endpoint != 0);

    create_helper_process(env, &server);
    set_helper_priority(env, &server, OUR_PRIO);
    void *shadow_stack = vspace_new_pages(
        &server.process.vspace, seL4_AllRights, 1, seL4_PageBits);
    test_assert(shadow_stack != NULL);

    vka_cspace_make_path(&env->vka, endpoint, &endpoint_path);
    const seL4_CPtr remote_endpoint =
        sel4utils_copy_path_to_process(&server.process, endpoint_path);
    test_assert(remote_endpoint != (seL4_CPtr)-1);
    start_helper(env, &server, (helper_fn_t)sum_server,
                 remote_endpoint, 0, 0, 0);
    /* Let the ordinary fallback server reach its endpoint receive queue. */
    seL4_Yield();

    const protected_rpc_endpoint_t rpc_endpoint = {.opaque = endpoint};
    const protected_rpc_blackparrot_binding_t binding = {
        .server_tcb = get_helper_tcb(&server),
        .server_entry = (uintptr_t)hardware_sum_entry,
        .server_sp = (uintptr_t)shadow_stack + BIT(seL4_PageBits),
        .request_words = 4,
        .reply_words = 1,
    };
    test_eq(protected_rpc_blackparrot_bind(rpc_endpoint, &binding),
            PROTECTED_RPC_OK);

    const protected_rpc_call_options_t hardware = {
        .route = PROTECTED_RPC_ROUTE_HARDWARE,
    };
    protected_rpc_message_t request = {
        .length = 4,
        .words = {11, 13, 17, 19},
    };
    protected_rpc_call_result_t result;
    uint64_t start = read_cycles();
    for (seL4_Word call = 0; call < ADAPTER_MEASURED_CALLS; call++) {
        test_eq(protected_rpc_call(rpc_endpoint, &request, &hardware, &result),
                PROTECTED_RPC_OK);
        test_eq(result.path, PROTECTED_RPC_PATH_HARDWARE);
        test_eq(result.reply.length, 1);
        test_eq(result.reply.words[0], 60);
    }
    const uint64_t elapsed = read_cycles() - start;

    test_eq(protected_rpc_blackparrot_unbind(rpc_endpoint), PROTECTED_RPC_OK);

    /* The same service remains reachable through ordinary endpoint IPC. */
    const protected_rpc_call_options_t software = {
        .route = PROTECTED_RPC_ROUTE_SOFTWARE,
    };
    test_eq(protected_rpc_call(rpc_endpoint, &request, &software, &result),
            PROTECTED_RPC_OK);
    test_eq(result.path, PROTECTED_RPC_PATH_SOFTWARE);
    test_eq(result.reply.length, 1);
    test_eq(result.reply.words[0], 60);
    test_eq(wait_for_helper(&server), PROTECTED_RPC_OK);

    vspace_unmap_pages(&server.process.vspace, shadow_stack, 1,
                       seL4_PageBits, VSPACE_FREE);
    cleanup_helper(env, &server);
    printf("SEL4_RPC_ADAPTER path=hardware calls=%u total_cycles=%" PRIu64
           " cycles_per_call=%" PRIu64 "\n",
           ADAPTER_MEASURED_CALLS, elapsed,
           elapsed / ADAPTER_MEASURED_CALLS);
    return 0;
}
#endif

static int test_sel4_rpc_adapter(env_t env)
{
    helper_thread_t server;
    cspacepath_t endpoint_path;
    seL4_CPtr endpoint = vka_alloc_endpoint_leaky(&env->vka);
    test_assert(endpoint != 0);

    void *shared_base = vspace_new_pages(&env->vspace, seL4_AllRights, 1,
                                         seL4_PageBits);
    test_assert(shared_base != NULL);
    volatile seL4_Word *shared = shared_base;
    shared[0] = 10;
    shared[1] = 20;
    adapter_server_private_counter = 0;

    create_helper_process(env, &server);
    set_helper_priority(env, &server, OUR_PRIO);
    void *server_shared_base = vspace_share_mem(
        &env->vspace, &server.process.vspace, shared_base, 1, seL4_PageBits,
        seL4_AllRights, true);
    test_assert(server_shared_base != NULL);

    vka_cspace_make_path(&env->vka, endpoint, &endpoint_path);
    const seL4_CPtr remote_endpoint =
        sel4utils_copy_path_to_process(&server.process, endpoint_path);
    test_assert(remote_endpoint != (seL4_CPtr)-1);
    start_helper(env, &server, (helper_fn_t)adapter_server,
                 remote_endpoint, (seL4_Word)server_shared_base, 0, 0);

    const protected_rpc_endpoint_t rpc_endpoint = {.opaque = endpoint};
    protected_rpc_call_options_t options = {
        .route = PROTECTED_RPC_ROUTE_HARDWARE,
    };
    protected_rpc_message_t request = {0};
    protected_rpc_call_result_t result;

    test_eq(protected_rpc_call(rpc_endpoint, &request, &options, &result),
            PROTECTED_RPC_UNSUPPORTED);
    test_eq(result.path, PROTECTED_RPC_PATH_HARDWARE);

    options.route = PROTECTED_RPC_ROUTE_SOFTWARE;
    protected_rpc_buffer_ref_t invalid = {
        .region = {.opaque = ADAPTER_REGION_TOKEN},
        .offset = BIT(seL4_PageBits) - 4,
        .length = sizeof(seL4_Word),
    };
    test_assert(protected_rpc_encode_buffer(&request, 0, invalid));
    request.words[3] = 1;
    request.length = 4;
    test_eq(protected_rpc_call(rpc_endpoint, &request, &options, &result),
            PROTECTED_RPC_INVALID_ARGUMENT);
    test_eq(result.path, PROTECTED_RPC_PATH_SOFTWARE);

    invalid.region.opaque++;
    invalid.offset = 0;
    test_assert(protected_rpc_encode_buffer(&request, 0, invalid));
    request.words[3] = 1;
    request.length = 4;
    test_eq(protected_rpc_call(rpc_endpoint, &request, &options, &result),
            PROTECTED_RPC_REVOKED);

    seL4_Word expected[2] = {10, 20};
    uint64_t start = 0;
    for (seL4_Word call = 0; call < ADAPTER_VALID_CALLS; call++) {
        const size_t index = call & 1;
        const seL4_Word delta = 3 + call;
        const protected_rpc_buffer_ref_t ref = {
            .region = {.opaque = ADAPTER_REGION_TOKEN},
            .offset = index * sizeof(seL4_Word),
            .length = sizeof(seL4_Word),
        };
        request.length = 0;
        test_assert(protected_rpc_encode_buffer(&request, 0, ref));
        request.words[3] = delta;
        request.length = 4;

        if (call == ADAPTER_WARMUP_CALLS) {
            start = read_cycles();
        }
        test_eq(protected_rpc_call(rpc_endpoint, &request, &options, &result),
                PROTECTED_RPC_OK);

        expected[index] += delta + call + 1;
        test_eq(result.path, PROTECTED_RPC_PATH_SOFTWARE);
        test_eq(result.reply.length, 2);
        test_eq(result.reply.words[0], expected[index]);
        test_eq(result.reply.words[1], call + 1);
        test_eq(shared[index], expected[index]);
    }
    const uint64_t elapsed = read_cycles() - start;

    test_eq(wait_for_helper(&server), PROTECTED_RPC_OK);
    test_eq(adapter_server_private_counter, 0);
    cleanup_helper(env, &server);
    vspace_unmap_pages(&env->vspace, shared_base, 1, seL4_PageBits,
                       VSPACE_FREE);

    printf("SEL4_RPC_ADAPTER path=software calls=%u total_cycles=%" PRIu64
           " cycles_per_call=%" PRIu64 "\n",
           ADAPTER_MEASURED_CALLS, elapsed,
           elapsed / ADAPTER_MEASURED_CALLS);
#ifdef CONFIG_PLAT_BLACKPARROT
    test_eq(test_blackparrot_hardware_binding(env), 0);
#endif
    return sel4test_get_result();
}

DEFINE_TEST(SEL4IPCRPC0002,
            "Backend-neutral protected RPC over ordinary seL4 IPC",
            test_sel4_rpc_adapter,
            !config_set(CONFIG_KERNEL_MCS))
