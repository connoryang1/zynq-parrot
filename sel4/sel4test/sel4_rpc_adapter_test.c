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
#define ADAPTER_BP_SOFTWARE_CALLS 8
#define ADAPTER_VALID_CALLS (ADAPTER_WARMUP_CALLS + ADAPTER_MEASURED_CALLS)
#define ADAPTER_TOTAL_SERVER_CALLS (ADAPTER_VALID_CALLS + 2)
#define ADAPTER_REGION_TOKEN UINT64_C(0xa11ce001)
#define ADAPTER_BP_SERVER_IMAGE "sel4-rpc-server"
#define ADAPTER_BP_SERVER_ARGS 2

static volatile seL4_Word adapter_server_private_counter;

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

static void destroy_sum_server(env_t env, sel4utils_process_t *server,
                               void *shadow_stack,
                               vka_object_t *control_endpoint)
{
    if (shadow_stack != NULL) {
        vspace_unmap_pages(&server->vspace, shadow_stack, 1,
                           seL4_PageBits, VSPACE_FREE);
    }
    seL4_TCB_Suspend(server->thread.tcb.cptr);
    /* The process borrows the test's fault endpoint; it does not own it. */
    server->fault_endpoint.cptr = 0;
    sel4utils_destroy_process(server, &env->vka);
    vka_free_object(&env->vka, control_endpoint);
}

#ifdef CONFIG_PLAT_BLACKPARROT
static int same_vspace_receiver(seL4_Word endpoint, seL4_Word unused1,
                                seL4_Word unused2, seL4_Word unused3)
{
    (void)unused1;
    (void)unused2;
    (void)unused3;
    seL4_Word badge = 0;
    (void)seL4_Recv((seL4_CPtr)endpoint, &badge);
    return 0;
}

static int test_blackparrot_rejects_same_vspace(env_t env)
{
    const seL4_CPtr endpoint = vka_alloc_endpoint_leaky(&env->vka);
    test_assert(endpoint != 0);

    helper_thread_t server;
    create_helper_thread(env, &server);
    set_helper_priority(env, &server, OUR_PRIO);
    start_helper(env, &server, (helper_fn_t)same_vspace_receiver,
                 endpoint, 0, 0, 0);
    /* Run the helper until it becomes the endpoint's sole receiver. */
    seL4_Yield();

    const protected_rpc_blackparrot_binding_t binding = {
        .server_tcb = get_helper_tcb(&server),
        .server_entry = (uintptr_t)same_vspace_receiver,
        .server_sp = get_helper_initial_stack_pointer(&server),
        .request_words = 4,
        .reply_words = 1,
    };
    test_eq(protected_rpc_blackparrot_bind(
                (protected_rpc_endpoint_t){.opaque = endpoint}, &binding),
            PROTECTED_RPC_DENIED);
    cleanup_helper(env, &server);
    return sel4test_get_result();
}

static int test_blackparrot_hardware_binding(env_t env)
{
    test_eq(test_blackparrot_rejects_same_vspace(env), 0);

    sel4utils_process_t server = {0};
    cspacepath_t endpoint_path;
    seL4_CPtr endpoint = vka_alloc_endpoint_leaky(&env->vka);
    test_assert(endpoint != 0);

    vka_object_t control_endpoint = {0};
    test_eq(vka_alloc_endpoint(&env->vka, &control_endpoint), 0);
    if (control_endpoint.cptr == 0) {
        return sel4test_get_result();
    }

    sel4utils_process_config_t config = process_config_default_simple(
        &env->simple, ADAPTER_BP_SERVER_IMAGE, OUR_PRIO);
    config = process_config_asid_pool(config, env->asid_pool);
    config = process_config_create_cnode(config, 10);
    vka_object_t fault_endpoint = {.cptr = env->endpoint};
    config = process_config_fault_endpoint(config, fault_endpoint);
    int error = sel4utils_configure_process_custom(
        &server, &env->vka, &env->vspace, config);
    test_eq(error, 0);
    if (error != 0) {
        vka_free_object(&env->vka, &control_endpoint);
        return sel4test_get_result();
    }

    void *shadow_stack = vspace_new_pages(
        &server.vspace, seL4_AllRights, 1, seL4_PageBits);
    test_assert(shadow_stack != NULL);
    if (shadow_stack == NULL) {
        destroy_sum_server(env, &server, NULL, &control_endpoint);
        return sel4test_get_result();
    }

    vka_cspace_make_path(&env->vka, endpoint, &endpoint_path);
    const seL4_CPtr remote_endpoint =
        sel4utils_copy_path_to_process(&server, endpoint_path);
    test_assert(remote_endpoint != (seL4_CPtr)-1);
    cspacepath_t control_path;
    vka_cspace_make_path(&env->vka, control_endpoint.cptr, &control_path);
    const seL4_CPtr remote_control =
        sel4utils_copy_path_to_process(&server, control_path);
    test_assert(remote_control != (seL4_CPtr)-1);
    if (remote_endpoint == (seL4_CPtr)-1
        || remote_control == (seL4_CPtr)-1) {
        destroy_sum_server(env, &server, shadow_stack, &control_endpoint);
        return sel4test_get_result();
    }

    char arg_strings[ADAPTER_BP_SERVER_ARGS][WORD_STRING_SIZE];
    char *args[ADAPTER_BP_SERVER_ARGS];
    sel4utils_create_word_args(arg_strings, args, ADAPTER_BP_SERVER_ARGS,
                               remote_endpoint, remote_control);
    error = sel4utils_spawn_process_v(&server, &env->vka, &env->vspace,
                                      ADAPTER_BP_SERVER_ARGS, args, 1);
    test_eq(error, 0);
    if (error != 0) {
        destroy_sum_server(env, &server, shadow_stack, &control_endpoint);
        return sel4test_get_result();
    }

    seL4_Word badge = 0;
    seL4_MessageInfo_t ready = seL4_Recv(control_endpoint.cptr, &badge);
    test_eq(seL4_MessageInfo_get_label(ready), 0);
    test_eq(seL4_MessageInfo_get_length(ready), 1);
    const seL4_Word hardware_entry = seL4_GetMR(0);
    test_assert(hardware_entry != 0);
    /* Let the ordinary fallback server reach its endpoint receive queue. */
    seL4_Yield();

    const protected_rpc_endpoint_t rpc_endpoint = {.opaque = endpoint};
    const protected_rpc_blackparrot_binding_t binding = {
        .server_tcb = server.thread.tcb.cptr,
        .server_entry = hardware_entry,
        .server_sp = (uintptr_t)shadow_stack + BIT(seL4_PageBits),
        .request_words = 4,
        .reply_words = 1,
    };
    protected_rpc_status_t bind_status = protected_rpc_blackparrot_bind(
        rpc_endpoint, &binding);
    test_eq(bind_status, PROTECTED_RPC_OK);
    if (bind_status != PROTECTED_RPC_OK) {
        /* A rejected bind cannot produce meaningful forced-hardware results. */
        destroy_sum_server(env, &server, shadow_stack, &control_endpoint);
        return sel4test_get_result();
    }

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
        protected_rpc_status_t call_status = protected_rpc_call(
            rpc_endpoint, &request, &hardware, &result);
        test_eq(call_status, PROTECTED_RPC_OK);
        if (call_status != PROTECTED_RPC_OK) {
            /* One rejected forced-hardware call is conclusive. Avoid turning
             * a transport failure into hundreds of slow serial assertions. */
            test_eq(protected_rpc_blackparrot_unbind(rpc_endpoint),
                    PROTECTED_RPC_OK);
            destroy_sum_server(env, &server, shadow_stack,
                               &control_endpoint);
            return sel4test_get_result();
        }
        test_eq(result.path, PROTECTED_RPC_PATH_HARDWARE);
        test_eq(result.reply.length, 1);
        test_eq(result.reply.words[0], 60);
    }
    const uint64_t elapsed = read_cycles() - start;

    test_eq(protected_rpc_blackparrot_unbind(rpc_endpoint), PROTECTED_RPC_OK);

    /* With the binding revoked, AUTO must make one precise non-executed
     * hardware attempt and then reach the same service through ordinary IPC. */
    const protected_rpc_call_options_t fallback = {
        .route = PROTECTED_RPC_ROUTE_AUTO,
    };
    const uint64_t software_start = read_cycles();
    for (seL4_Word call = 0; call < ADAPTER_BP_SOFTWARE_CALLS; call++) {
        test_eq(protected_rpc_call(rpc_endpoint, &request, &fallback, &result),
                PROTECTED_RPC_OK);
        test_eq(result.path, PROTECTED_RPC_PATH_SOFTWARE);
        test_eq(result.reply.length, 1);
        test_eq(result.reply.words[0], 60);
    }
    const uint64_t software_elapsed = read_cycles() - software_start;
    seL4_MessageInfo_t finished = seL4_Recv(control_endpoint.cptr, &badge);
    test_eq(seL4_MessageInfo_get_label(finished), PROTECTED_RPC_OK);
    test_eq(seL4_MessageInfo_get_length(finished), 0);

    destroy_sum_server(env, &server, shadow_stack, &control_endpoint);
    printf("SEL4_RPC_ADAPTER path=hardware calls=%u total_cycles=%" PRIu64
           " cycles_per_call=%" PRIu64 "\n",
           ADAPTER_MEASURED_CALLS, elapsed,
           elapsed / ADAPTER_MEASURED_CALLS);
    printf("SEL4_RPC_ADAPTER path=software-fallback calls=%u total_cycles=%" PRIu64
           " cycles_per_call=%" PRIu64 "\n",
           ADAPTER_BP_SOFTWARE_CALLS, software_elapsed,
           software_elapsed / ADAPTER_BP_SOFTWARE_CALLS);
    return 0;
}
#endif

#if defined(SEL4TEST_RPC_ONLY) && !defined(CONFIG_PLAT_BLACKPARROT)
/* Qualify the dedicated server image and control handshake under fast QEMU.
 * BlackParrot runs the same image through the hardware/fallback gate above. */
static int test_dedicated_sum_server_software(env_t env)
{
    sel4utils_process_t server = {0};
    seL4_CPtr endpoint = vka_alloc_endpoint_leaky(&env->vka);
    test_assert(endpoint != 0);

    vka_object_t control_endpoint = {0};
    test_eq(vka_alloc_endpoint(&env->vka, &control_endpoint), 0);
    if (control_endpoint.cptr == 0) {
        return sel4test_get_result();
    }

    sel4utils_process_config_t config = process_config_default_simple(
        &env->simple, ADAPTER_BP_SERVER_IMAGE, OUR_PRIO);
    config = process_config_asid_pool(config, env->asid_pool);
    config = process_config_create_cnode(config, 10);
    vka_object_t fault_endpoint = {.cptr = env->endpoint};
    config = process_config_fault_endpoint(config, fault_endpoint);
    int error = sel4utils_configure_process_custom(
        &server, &env->vka, &env->vspace, config);
    test_eq(error, 0);
    if (error != 0) {
        vka_free_object(&env->vka, &control_endpoint);
        return sel4test_get_result();
    }

    cspacepath_t endpoint_path;
    vka_cspace_make_path(&env->vka, endpoint, &endpoint_path);
    const seL4_CPtr remote_endpoint =
        sel4utils_copy_path_to_process(&server, endpoint_path);
    cspacepath_t control_path;
    vka_cspace_make_path(&env->vka, control_endpoint.cptr, &control_path);
    const seL4_CPtr remote_control =
        sel4utils_copy_path_to_process(&server, control_path);
    test_assert(remote_endpoint != (seL4_CPtr)-1);
    test_assert(remote_control != (seL4_CPtr)-1);
    if (remote_endpoint == (seL4_CPtr)-1
        || remote_control == (seL4_CPtr)-1) {
        destroy_sum_server(env, &server, NULL, &control_endpoint);
        return sel4test_get_result();
    }

    char arg_strings[ADAPTER_BP_SERVER_ARGS][WORD_STRING_SIZE];
    char *args[ADAPTER_BP_SERVER_ARGS];
    sel4utils_create_word_args(arg_strings, args, ADAPTER_BP_SERVER_ARGS,
                               remote_endpoint, remote_control);
    error = sel4utils_spawn_process_v(&server, &env->vka, &env->vspace,
                                      ADAPTER_BP_SERVER_ARGS, args, 1);
    test_eq(error, 0);
    if (error != 0) {
        destroy_sum_server(env, &server, NULL, &control_endpoint);
        return sel4test_get_result();
    }

    seL4_Word badge = 0;
    seL4_MessageInfo_t ready = seL4_Recv(control_endpoint.cptr, &badge);
    test_eq(seL4_MessageInfo_get_label(ready), 0);
    test_eq(seL4_MessageInfo_get_length(ready), 1);
    test_assert(seL4_GetMR(0) != 0);

    const protected_rpc_endpoint_t rpc_endpoint = {.opaque = endpoint};
    const protected_rpc_call_options_t software = {
        .route = PROTECTED_RPC_ROUTE_SOFTWARE,
    };
    const protected_rpc_message_t request = {
        .length = 4,
        .words = {11, 13, 17, 19},
    };
    protected_rpc_call_result_t result;
    const uint64_t start = read_cycles();
    for (seL4_Word call = 0; call < ADAPTER_BP_SOFTWARE_CALLS; call++) {
        test_eq(protected_rpc_call(rpc_endpoint, &request, &software, &result),
                PROTECTED_RPC_OK);
        test_eq(result.path, PROTECTED_RPC_PATH_SOFTWARE);
        test_eq(result.reply.length, 1);
        test_eq(result.reply.words[0], 60);
    }
    const uint64_t elapsed = read_cycles() - start;

    seL4_MessageInfo_t finished = seL4_Recv(control_endpoint.cptr, &badge);
    test_eq(seL4_MessageInfo_get_label(finished), PROTECTED_RPC_OK);
    test_eq(seL4_MessageInfo_get_length(finished), 0);
    destroy_sum_server(env, &server, NULL, &control_endpoint);

    printf("SEL4_RPC_ADAPTER path=software-dedicated calls=%u total_cycles=%"
           PRIu64 " cycles_per_call=%" PRIu64 "\n",
           ADAPTER_BP_SOFTWARE_CALLS, elapsed,
           elapsed / ADAPTER_BP_SOFTWARE_CALLS);
    return sel4test_get_result();
}
#endif

static int test_sel4_rpc_adapter(env_t env)
{
#if defined(CONFIG_PLAT_BLACKPARROT)
    /* The cycle-accurate model runs the focused hardware/fallback gate; QEMU
     * retains the larger shared-buffer software regression below. */
    test_eq(test_blackparrot_hardware_binding(env), 0);
    return sel4test_get_result();
#elif defined(SEL4TEST_RPC_ONLY)
    return test_dedicated_sum_server_software(env);
#else

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
    return sel4test_get_result();
#endif
}

DEFINE_TEST(SEL4IPCRPC0002,
            "Backend-neutral protected RPC over ordinary seL4 IPC",
            test_sel4_rpc_adapter,
            !config_set(CONFIG_KERNEL_MCS))
