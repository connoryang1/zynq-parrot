/*
 * Exercise the backend-neutral protected-RPC API through ordinary seL4 IPC.
 * The same handler body is intended to be reused by the hardware backend.
 */

#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <sel4/sel4.h>
#include <sel4utils/process.h>
#include <vka/capops.h>
#include <vka/object.h>
#include <vspace/vspace.h>

#include "protected_rpc.h"
#include "sel4_rpc_search_service.h"
#ifdef CONFIG_PLAT_BLACKPARROT
#include "protected_rpc_blackparrot.h"
#endif
#include "../helpers.h"

#define ADAPTER_WARMUP_CALLS 8
#define ADAPTER_MEASURED_CALLS 256
#define ADAPTER_BP_SOFTWARE_CALLS SEL4_RPC_SEARCH_MEASURED_CALLS
#define ADAPTER_DISTRIBUTION_CALLS SEL4_RPC_SEARCH_DISTRIBUTION_CALLS
#define ADAPTER_L1D_COLD_CALLS SEL4_RPC_SEARCH_L1D_COLD_CALLS
#define ADAPTER_HIERARCHY_COLD_CALLS SEL4_RPC_SEARCH_HIERARCHY_COLD_CALLS
#define ADAPTER_BP_FALLBACK_CALLS SEL4_RPC_SEARCH_FALLBACK_CALLS
#define ADAPTER_NOTIFICATION_CALLS SEL4_RPC_SEARCH_MEASURED_CALLS
#define ADAPTER_VALID_CALLS (ADAPTER_WARMUP_CALLS + ADAPTER_MEASURED_CALLS)
#define ADAPTER_TOTAL_SERVER_CALLS (ADAPTER_VALID_CALLS + 2)
#define ADAPTER_REGION_TOKEN UINT64_C(0xa11ce001)
#define ADAPTER_BP_SERVER_IMAGE "sel4-rpc-server"
#define ADAPTER_BP_SERVER_ARGS 7
#define ADAPTER_SOFTWARE_SERVER_ARGS 4
#define ADAPTER_SEARCH_BYTES SEL4_RPC_SEARCH_BYTES
#define ADAPTER_SEARCH_NEEDLE ((seL4_Word)SEL4_RPC_SEARCH_NEEDLE)
#define ADAPTER_CACHE_LINE_BYTES 64u
#define ADAPTER_L2_EVICTION_BYTES (4u * BIT(seL4_PageBits))

static volatile seL4_Word adapter_server_private_counter;
#ifdef CONFIG_PLAT_BLACKPARROT
static unsigned char adapter_l2_eviction[ADAPTER_L2_EVICTION_BYTES]
    __attribute__((aligned(BIT(seL4_PageBits))));
static volatile uint64_t adapter_l2_eviction_sink;
#endif

static inline uint64_t read_cycles(void)
{
    uint64_t value;
#ifdef CONFIG_PLAT_BLACKPARROT
    /* The physical counter is not virtualized across resident contexts. */
    __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
#else
    __asm__ volatile("rdcycle %0" : "=r"(value) : : "memory");
#endif
    return value;
}

#ifdef CONFIG_PLAT_BLACKPARROT
static inline void flush_l1_data_cache(void)
{
    /* BlackParrot's custom whole-cache flush: write back dirty L1D lines and
     * invalidate every L1D tag. The instruction does not invalidate L1I or
     * the shared lower cache, so results are explicitly L1D-cold/L2-warm. */
    __asm__ volatile(".word 0x0020700f" : : : "memory");
}

static void evict_data_cache_hierarchy(void)
{
    /* This endpoint has a 4 KiB, 2-way, 64-byte-line L2. Four page-aligned
     * pages cover every physical L2 set eight times. Flush before the scan so
     * prior dirty state is below L1, then flush again so neither the workload
     * nor eviction lines remain in L1 when timing begins. */
    flush_l1_data_cache();
    uint64_t sum = adapter_l2_eviction_sink;
    for (size_t offset = 0; offset < ADAPTER_L2_EVICTION_BYTES;
         offset += ADAPTER_CACHE_LINE_BYTES) {
        sum += *(volatile const uint64_t *)&adapter_l2_eviction[offset];
    }
    adapter_l2_eviction_sink = sum;
    flush_l1_data_cache();
}

static protected_rpc_status_t notification_call(
    seL4_CPtr request_notification, seL4_CPtr reply_notification,
    volatile sel4_rpc_notification_mailbox_t *mailbox, uint64_t sequence,
    const protected_rpc_message_t *request, protected_rpc_message_t *reply)
{
    if (!protected_rpc_message_valid(request) || reply == NULL
        || sequence == 0) {
        return PROTECTED_RPC_INVALID_ARGUMENT;
    }
    mailbox->request_length = request->length;
    for (size_t word = 0; word < PROTECTED_RPC_MAX_WORDS; word++) {
        mailbox->request_words[word] = request->words[word];
    }
    __atomic_store_n(&mailbox->request_sequence, sequence, __ATOMIC_RELEASE);
    seL4_Signal(request_notification);
    seL4_Wait(reply_notification, NULL);
    if (__atomic_load_n(&mailbox->reply_sequence, __ATOMIC_ACQUIRE)
        != sequence
        || mailbox->reply_length > PROTECTED_RPC_MAX_WORDS
        || mailbox->status > PROTECTED_RPC_BACKEND_ERROR) {
        return PROTECTED_RPC_BACKEND_ERROR;
    }
    reply->length = (uint8_t)mailbox->reply_length;
    for (size_t word = 0; word < PROTECTED_RPC_MAX_WORDS; word++) {
        reply->words[word] = mailbox->reply_words[word];
    }
    return (protected_rpc_status_t)mailbox->status;
}
#endif

static void print_cycle_distribution(const char *path, uint64_t *samples,
                                     size_t count)
{
    for (size_t index = 1; index < count; index++) {
        const uint64_t value = samples[index];
        size_t position = index;
        while (position != 0 && samples[position - 1] > value) {
            samples[position] = samples[position - 1];
            position--;
        }
        samples[position] = value;
    }
    const size_t median_index = count / 2;
    const size_t p95_index = (count * 95 + 99) / 100 - 1;
    printf("SEL4_RPC_DISTRIBUTION path=%s samples=%zu min=%" PRIu64
           " median=%" PRIu64 " p95=%" PRIu64 " max=%" PRIu64 "\n",
           path, count, samples[0], samples[median_index],
           samples[p95_index], samples[count - 1]);
}

static void sort_cycle_samples(uint64_t *samples, size_t count)
{
    for (size_t index = 1; index < count; index++) {
        const uint64_t value = samples[index];
        size_t position = index;
        while (position != 0 && samples[position - 1] > value) {
            samples[position] = samples[position - 1];
            position--;
        }
        samples[position] = value;
    }
}

static void print_cycle_components(const char *path, uint64_t *pre_samples,
                                   uint64_t *service_samples,
                                   uint64_t *post_samples, size_t count)
{
    sort_cycle_samples(pre_samples, count);
    sort_cycle_samples(service_samples, count);
    sort_cycle_samples(post_samples, count);
    printf("SEL4_RPC_COMPONENTS path=%s samples=%zu pre_median=%" PRIu64
           " service_median=%" PRIu64 " post_median=%" PRIu64 "\n",
           path, count, pre_samples[count / 2], service_samples[count / 2],
           post_samples[count / 2]);
}

static int record_cycle_components(
    uint64_t call_start, uint64_t call_end,
    const protected_rpc_message_t *reply, uint64_t *pre,
    uint64_t *service, uint64_t *post)
{
    if (reply == NULL || reply->length != 4
        || reply->words[2] < call_start
        || reply->words[3] < reply->words[2]
        || call_end < reply->words[3]) {
        return 0;
    }
    *pre = reply->words[2] - call_start;
    *service = reply->words[3] - reply->words[2];
    *post = call_end - reply->words[3];
    return 1;
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

static void destroy_rpc_server(env_t env, sel4utils_process_t *server,
                               void *shadow_stack, void *caller_shared,
                               void *caller_mailbox,
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
    if (caller_shared != NULL) {
        vspace_unmap_pages(&env->vspace, caller_shared, 1,
                           seL4_PageBits, VSPACE_FREE);
    }
    if (caller_mailbox != NULL) {
        vspace_unmap_pages(&env->vspace, caller_mailbox, 1,
                           seL4_PageBits, VSPACE_FREE);
    }
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
        destroy_rpc_server(env, &server, NULL, NULL, NULL, &control_endpoint);
        return sel4test_get_result();
    }

    void *shared_base = vspace_new_pages(
        &env->vspace, seL4_AllRights, 1, seL4_PageBits);
    test_assert(shared_base != NULL);
    if (shared_base == NULL) {
        destroy_rpc_server(env, &server, shadow_stack, NULL, NULL,
                           &control_endpoint);
        return sel4test_get_result();
    }
    memset(shared_base, 'a', ADAPTER_SEARCH_BYTES);
    ((unsigned char *)shared_base)[ADAPTER_SEARCH_BYTES - 1] =
        (unsigned char)ADAPTER_SEARCH_NEEDLE;
    void *server_shared_base = vspace_share_mem(
        &env->vspace, &server.vspace, shared_base, 1, seL4_PageBits,
        seL4_CapRights_new(false, false, true, false), true);
    test_assert(server_shared_base != NULL);
    if (server_shared_base == NULL) {
        destroy_rpc_server(env, &server, shadow_stack, shared_base,
                           NULL,
                           &control_endpoint);
        return sel4test_get_result();
    }

    void *mailbox_base = vspace_new_pages(
        &env->vspace, seL4_AllRights, 1, seL4_PageBits);
    test_assert(mailbox_base != NULL);
    if (mailbox_base == NULL) {
        destroy_rpc_server(env, &server, shadow_stack, shared_base, NULL,
                           &control_endpoint);
        return sel4test_get_result();
    }
    memset(mailbox_base, 0, BIT(seL4_PageBits));
    void *server_mailbox_base = vspace_share_mem(
        &env->vspace, &server.vspace, mailbox_base, 1, seL4_PageBits,
        seL4_CapRights_new(false, false, true, true), true);
    test_assert(server_mailbox_base != NULL);
    if (server_mailbox_base == NULL) {
        destroy_rpc_server(env, &server, shadow_stack, shared_base,
                           mailbox_base, &control_endpoint);
        return sel4test_get_result();
    }

    const seL4_CPtr request_notification =
        vka_alloc_notification_leaky(&env->vka);
    const seL4_CPtr reply_notification =
        vka_alloc_notification_leaky(&env->vka);
    test_assert(request_notification != 0);
    test_assert(reply_notification != 0);
    if (request_notification == 0 || reply_notification == 0) {
        destroy_rpc_server(env, &server, shadow_stack, shared_base,
                           mailbox_base, &control_endpoint);
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
    cspacepath_t request_notification_path;
    vka_cspace_make_path(&env->vka, request_notification,
                         &request_notification_path);
    const seL4_CPtr remote_request_notification =
        sel4utils_copy_path_to_process(&server, request_notification_path);
    cspacepath_t reply_notification_path;
    vka_cspace_make_path(&env->vka, reply_notification,
                         &reply_notification_path);
    const seL4_CPtr remote_reply_notification =
        sel4utils_copy_path_to_process(&server, reply_notification_path);
    test_assert(remote_control != (seL4_CPtr)-1);
    test_assert(remote_request_notification != (seL4_CPtr)-1);
    test_assert(remote_reply_notification != (seL4_CPtr)-1);
    if (remote_endpoint == (seL4_CPtr)-1
        || remote_control == (seL4_CPtr)-1
        || remote_request_notification == (seL4_CPtr)-1
        || remote_reply_notification == (seL4_CPtr)-1) {
        destroy_rpc_server(env, &server, shadow_stack, shared_base,
                           mailbox_base,
                           &control_endpoint);
        return sel4test_get_result();
    }

    char arg_strings[ADAPTER_BP_SERVER_ARGS][WORD_STRING_SIZE];
    char *args[ADAPTER_BP_SERVER_ARGS];
    sel4utils_create_word_args(arg_strings, args, ADAPTER_BP_SERVER_ARGS,
                               remote_endpoint, remote_control,
                               (seL4_Word)server_shared_base,
                               ADAPTER_REGION_TOKEN,
                               remote_request_notification,
                               remote_reply_notification,
                               (seL4_Word)server_mailbox_base);
    error = sel4utils_spawn_process_v(&server, &env->vka, &env->vspace,
                                      ADAPTER_BP_SERVER_ARGS, args, 1);
    test_eq(error, 0);
    if (error != 0) {
        destroy_rpc_server(env, &server, shadow_stack, shared_base,
                           mailbox_base,
                           &control_endpoint);
        return sel4test_get_result();
    }

    seL4_Word badge = 0;
    seL4_MessageInfo_t ready = seL4_Recv(control_endpoint.cptr, &badge);
    test_eq(seL4_MessageInfo_get_label(ready), 0);
    test_eq(seL4_MessageInfo_get_length(ready), 3);
    const seL4_Word hardware_entry = seL4_GetMR(0);
    const seL4_Word hardware_gp = seL4_GetMR(1);
    const seL4_Word hardware_state = seL4_GetMR(2);
    test_assert(hardware_entry != 0);
    test_assert(hardware_gp != 0);
    test_assert(hardware_state != 0);
    /* The server first waits on the request notification. After the matched
     * notification calls below it enters the ordinary endpoint receive loop. */

    cspacepath_t caller_endpoint_path;
    error = vka_cspace_alloc_path(&env->vka, &caller_endpoint_path);
    test_eq(error, 0);
    if (error == 0) {
        error = vka_cnode_mint(&caller_endpoint_path, &endpoint_path,
                               seL4_AllRights,
                               SEL4_RPC_SEARCH_CALLER_BADGE);
        test_eq(error, 0);
    }
    if (error != 0) {
        destroy_rpc_server(env, &server, shadow_stack, shared_base,
                           mailbox_base, &control_endpoint);
        return sel4test_get_result();
    }
    const protected_rpc_endpoint_t rpc_endpoint = {
        .opaque = caller_endpoint_path.capPtr,
    };
    protected_rpc_message_t request = {0};
    const protected_rpc_buffer_ref_t search_ref = {
        .region = {.opaque = ADAPTER_REGION_TOKEN},
        .offset = 0,
        .length = ADAPTER_SEARCH_BYTES,
    };
    test_assert(protected_rpc_encode_buffer(&request, 0, search_ref));
    request.words[3] = ADAPTER_SEARCH_NEEDLE;
    request.length = 4;

    const protected_rpc_region_binding_t local_region = {
        .region = {.opaque = ADAPTER_REGION_TOKEN},
        .local_base = shared_base,
        .size = BIT(seL4_PageBits),
        .access = PROTECTED_RPC_ACCESS_READ,
    };
    const protected_rpc_server_config_t local_config = {
        .handler = sel4_rpc_bounded_search_service,
        .regions = &local_region,
        .region_count = 1,
    };
    const protected_rpc_call_context_t local_context = {
        .runtime_private = (void *)&local_config,
    };
    protected_rpc_message_t local_reply = {0};
    uint64_t direct_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t hardware_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t software_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t notification_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t direct_pre_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t direct_service_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t direct_post_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t hardware_pre_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t hardware_service_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t hardware_post_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t software_pre_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t software_service_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t software_post_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t notification_pre_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t notification_service_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t notification_post_samples[ADAPTER_DISTRIBUTION_CALLS];
    uint64_t direct_l1d_cold_samples[ADAPTER_L1D_COLD_CALLS];
    uint64_t hardware_l1d_cold_samples[ADAPTER_L1D_COLD_CALLS];
    uint64_t software_l1d_cold_samples[ADAPTER_L1D_COLD_CALLS];
    uint64_t notification_l1d_cold_samples[ADAPTER_L1D_COLD_CALLS];
    uint64_t direct_hierarchy_cold_samples[ADAPTER_HIERARCHY_COLD_CALLS];
    uint64_t hardware_hierarchy_cold_samples[ADAPTER_HIERARCHY_COLD_CALLS];
    uint64_t software_hierarchy_cold_samples[ADAPTER_HIERARCHY_COLD_CALLS];
    uint64_t notification_hierarchy_cold_samples[
        ADAPTER_HIERARCHY_COLD_CALLS];
    uint64_t direct_start = 0;
    for (seL4_Word call = 0;
         call < ADAPTER_WARMUP_CALLS + ADAPTER_MEASURED_CALLS; call++) {
        if (call == ADAPTER_WARMUP_CALLS) {
            direct_start = read_cycles();
        }
        test_eq(sel4_rpc_bounded_search_service(
                    &local_context, &request, &local_reply, NULL),
                PROTECTED_RPC_OK);
        test_eq(local_reply.length, 4);
        test_eq(local_reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(local_reply.words[1], ADAPTER_SEARCH_BYTES);
    }
    const uint64_t direct_elapsed = read_cycles() - direct_start;
    for (size_t sample = 0; sample < ADAPTER_DISTRIBUTION_CALLS; sample++) {
        const uint64_t sample_start = read_cycles();
        protected_rpc_status_t status = sel4_rpc_bounded_search_service(
            &local_context, &request, &local_reply, NULL);
        const uint64_t sample_end = read_cycles();
        direct_samples[sample] = sample_end - sample_start;
        test_assert(record_cycle_components(
            sample_start, sample_end, &local_reply,
            &direct_pre_samples[sample], &direct_service_samples[sample],
            &direct_post_samples[sample]));
        test_eq(status, PROTECTED_RPC_OK);
        test_eq(local_reply.length, 4);
        test_eq(local_reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(local_reply.words[1], ADAPTER_SEARCH_BYTES);
    }
    for (size_t sample = 0; sample < ADAPTER_L1D_COLD_CALLS; sample++) {
        flush_l1_data_cache();
        const uint64_t sample_start = read_cycles();
        protected_rpc_status_t status = sel4_rpc_bounded_search_service(
            &local_context, &request, &local_reply, NULL);
        direct_l1d_cold_samples[sample] = read_cycles() - sample_start;
        test_eq(status, PROTECTED_RPC_OK);
        test_eq(local_reply.length, 4);
        test_eq(local_reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(local_reply.words[1], ADAPTER_SEARCH_BYTES);
    }
    for (size_t sample = 0; sample < ADAPTER_HIERARCHY_COLD_CALLS; sample++) {
        evict_data_cache_hierarchy();
        const uint64_t sample_start = read_cycles();
        protected_rpc_status_t status = sel4_rpc_bounded_search_service(
            &local_context, &request, &local_reply, NULL);
        direct_hierarchy_cold_samples[sample] = read_cycles() - sample_start;
        test_eq(status, PROTECTED_RPC_OK);
        test_eq(local_reply.length, 4);
        test_eq(local_reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(local_reply.words[1], ADAPTER_SEARCH_BYTES);
    }

    volatile sel4_rpc_notification_mailbox_t *notification_mailbox =
        mailbox_base;
    protected_rpc_message_t notification_reply = {0};
    uint64_t notification_sequence = 0;
    uint64_t notification_start = 0;
    for (seL4_Word call = 0;
         call < ADAPTER_WARMUP_CALLS + ADAPTER_NOTIFICATION_CALLS; call++) {
        if (call == ADAPTER_WARMUP_CALLS) {
            notification_start = read_cycles();
        }
        notification_sequence++;
        test_eq(notification_call(
                    request_notification, reply_notification,
                    notification_mailbox, notification_sequence, &request,
                    &notification_reply),
                PROTECTED_RPC_OK);
        test_eq(notification_reply.length, 4);
        test_eq(notification_reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(notification_reply.words[1], ADAPTER_SEARCH_BYTES);
    }
    const uint64_t notification_elapsed =
        read_cycles() - notification_start;
    for (size_t sample = 0; sample < ADAPTER_DISTRIBUTION_CALLS; sample++) {
        notification_sequence++;
        const uint64_t sample_start = read_cycles();
        protected_rpc_status_t status = notification_call(
            request_notification, reply_notification, notification_mailbox,
            notification_sequence, &request, &notification_reply);
        const uint64_t sample_end = read_cycles();
        notification_samples[sample] = sample_end - sample_start;
        test_assert(record_cycle_components(
            sample_start, sample_end, &notification_reply,
            &notification_pre_samples[sample],
            &notification_service_samples[sample],
            &notification_post_samples[sample]));
        test_eq(status, PROTECTED_RPC_OK);
        test_eq(notification_reply.length, 4);
        test_eq(notification_reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(notification_reply.words[1], ADAPTER_SEARCH_BYTES);
    }
    for (size_t sample = 0; sample < ADAPTER_L1D_COLD_CALLS; sample++) {
        flush_l1_data_cache();
        notification_sequence++;
        const uint64_t sample_start = read_cycles();
        protected_rpc_status_t status = notification_call(
            request_notification, reply_notification, notification_mailbox,
            notification_sequence, &request, &notification_reply);
        notification_l1d_cold_samples[sample] =
            read_cycles() - sample_start;
        test_eq(status, PROTECTED_RPC_OK);
        test_eq(notification_reply.length, 4);
        test_eq(notification_reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(notification_reply.words[1], ADAPTER_SEARCH_BYTES);
    }
    for (size_t sample = 0; sample < ADAPTER_HIERARCHY_COLD_CALLS; sample++) {
        evict_data_cache_hierarchy();
        notification_sequence++;
        const uint64_t sample_start = read_cycles();
        protected_rpc_status_t status = notification_call(
            request_notification, reply_notification, notification_mailbox,
            notification_sequence, &request, &notification_reply);
        notification_hierarchy_cold_samples[sample] =
            read_cycles() - sample_start;
        test_eq(status, PROTECTED_RPC_OK);
        test_eq(notification_reply.length, 4);
        test_eq(notification_reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(notification_reply.words[1], ADAPTER_SEARCH_BYTES);
    }
    test_eq(notification_sequence, SEL4_RPC_SEARCH_NOTIFICATION_REQUESTS);
    /* Let the server leave its notification loop and block on the endpoint. */
    seL4_Yield();

    const protected_rpc_call_options_t software = {
        .route = PROTECTED_RPC_ROUTE_SOFTWARE,
    };
    protected_rpc_call_result_t result;
    uint64_t software_start = 0;
    for (seL4_Word call = 0;
         call < ADAPTER_WARMUP_CALLS + ADAPTER_BP_SOFTWARE_CALLS; call++) {
        if (call == ADAPTER_WARMUP_CALLS) {
            software_start = read_cycles();
        }
        test_eq(protected_rpc_call(rpc_endpoint, &request, &software, &result),
                PROTECTED_RPC_OK);
        test_eq(result.path, PROTECTED_RPC_PATH_SOFTWARE);
        test_eq(result.reply.length, 4);
        test_eq(result.reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(result.reply.words[1], ADAPTER_SEARCH_BYTES);
    }
    const uint64_t software_elapsed = read_cycles() - software_start;
    for (size_t sample = 0; sample < ADAPTER_DISTRIBUTION_CALLS; sample++) {
        const uint64_t sample_start = read_cycles();
        protected_rpc_status_t status = protected_rpc_call(
            rpc_endpoint, &request, &software, &result);
        const uint64_t sample_end = read_cycles();
        software_samples[sample] = sample_end - sample_start;
        test_assert(record_cycle_components(
            sample_start, sample_end, &result.reply,
            &software_pre_samples[sample], &software_service_samples[sample],
            &software_post_samples[sample]));
        test_eq(status, PROTECTED_RPC_OK);
        test_eq(result.path, PROTECTED_RPC_PATH_SOFTWARE);
        test_eq(result.reply.length, 4);
        test_eq(result.reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(result.reply.words[1], ADAPTER_SEARCH_BYTES);
    }
    for (size_t sample = 0; sample < ADAPTER_L1D_COLD_CALLS; sample++) {
        flush_l1_data_cache();
        const uint64_t sample_start = read_cycles();
        protected_rpc_status_t status = protected_rpc_call(
            rpc_endpoint, &request, &software, &result);
        software_l1d_cold_samples[sample] = read_cycles() - sample_start;
        test_eq(status, PROTECTED_RPC_OK);
        test_eq(result.path, PROTECTED_RPC_PATH_SOFTWARE);
        test_eq(result.reply.length, 4);
        test_eq(result.reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(result.reply.words[1], ADAPTER_SEARCH_BYTES);
    }
    for (size_t sample = 0; sample < ADAPTER_HIERARCHY_COLD_CALLS; sample++) {
        evict_data_cache_hierarchy();
        const uint64_t sample_start = read_cycles();
        protected_rpc_status_t status = protected_rpc_call(
            rpc_endpoint, &request, &software, &result);
        software_hierarchy_cold_samples[sample] = read_cycles() - sample_start;
        test_eq(status, PROTECTED_RPC_OK);
        test_eq(result.path, PROTECTED_RPC_PATH_SOFTWARE);
        test_eq(result.reply.length, 4);
        test_eq(result.reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(result.reply.words[1], ADAPTER_SEARCH_BYTES);
    }

    const protected_rpc_blackparrot_binding_t binding = {
        .server_tcb = server.thread.tcb.cptr,
        .server_entry = hardware_entry,
        .server_sp = (uintptr_t)shadow_stack + BIT(seL4_PageBits),
        .server_gp = hardware_gp,
        .server_tp = hardware_state,
        .request_words = 4,
        .reply_words = 4,
        .region = {
            .region = {.opaque = ADAPTER_REGION_TOKEN},
            .caller_base = (uintptr_t)shared_base,
            .server_base = (uintptr_t)server_shared_base,
            .size = BIT(seL4_PageBits),
            .access = PROTECTED_RPC_ACCESS_READ,
        },
    };

    /* The region name alone grants nothing. The kernel must reject both a
     * different physical page and a permission wider than the server map. */
    protected_rpc_blackparrot_binding_t invalid_binding = binding;
    invalid_binding.region.server_base = (uintptr_t)shadow_stack;
    test_eq(protected_rpc_blackparrot_bind(rpc_endpoint, &invalid_binding),
            PROTECTED_RPC_DENIED);
    invalid_binding = binding;
    invalid_binding.region.access = PROTECTED_RPC_ACCESS_READ
                                    | PROTECTED_RPC_ACCESS_WRITE;
    test_eq(protected_rpc_blackparrot_bind(rpc_endpoint, &invalid_binding),
            PROTECTED_RPC_DENIED);
    invalid_binding = binding;
    invalid_binding.server_tp = BIT(37);
    test_eq(protected_rpc_blackparrot_bind(rpc_endpoint, &invalid_binding),
            PROTECTED_RPC_DENIED);
    printf("SEL4_RPC_REGION_GUARD physical-mismatch=denied "
           "write-escalation=denied runtime-state=denied\n");

    protected_rpc_status_t bind_status = protected_rpc_blackparrot_bind(
        rpc_endpoint, &binding);
    test_eq(bind_status, PROTECTED_RPC_OK);
    if (bind_status != PROTECTED_RPC_OK) {
        /* A rejected bind cannot produce meaningful forced-hardware results. */
        destroy_rpc_server(env, &server, shadow_stack, shared_base,
                           mailbox_base,
                           &control_endpoint);
        return sel4test_get_result();
    }

    const protected_rpc_call_options_t hardware = {
        .route = PROTECTED_RPC_ROUTE_HARDWARE,
    };
    uint64_t hardware_start = 0;
    for (seL4_Word call = 0;
         call < ADAPTER_WARMUP_CALLS + ADAPTER_MEASURED_CALLS; call++) {
        if (call == ADAPTER_WARMUP_CALLS) {
            hardware_start = read_cycles();
        }
        protected_rpc_status_t call_status = protected_rpc_call(
            rpc_endpoint, &request, &hardware, &result);
        test_eq(call_status, PROTECTED_RPC_OK);
        if (call_status != PROTECTED_RPC_OK) {
            /* One rejected forced-hardware call is conclusive. Avoid turning
             * a transport failure into hundreds of slow serial assertions. */
            test_eq(protected_rpc_blackparrot_unbind(rpc_endpoint),
                    PROTECTED_RPC_OK);
            destroy_rpc_server(env, &server, shadow_stack, shared_base,
                               mailbox_base,
                               &control_endpoint);
            return sel4test_get_result();
        }
        test_eq(result.path, PROTECTED_RPC_PATH_HARDWARE);
        test_eq(result.reply.length, 4);
        test_eq(result.reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(result.reply.words[1], ADAPTER_SEARCH_BYTES);
    }
    const uint64_t hardware_elapsed = read_cycles() - hardware_start;
    for (size_t sample = 0; sample < ADAPTER_DISTRIBUTION_CALLS; sample++) {
        const uint64_t sample_start = read_cycles();
        protected_rpc_status_t status = protected_rpc_call(
            rpc_endpoint, &request, &hardware, &result);
        const uint64_t sample_end = read_cycles();
        hardware_samples[sample] = sample_end - sample_start;
        test_assert(record_cycle_components(
            sample_start, sample_end, &result.reply,
            &hardware_pre_samples[sample], &hardware_service_samples[sample],
            &hardware_post_samples[sample]));
        test_eq(status, PROTECTED_RPC_OK);
        test_eq(result.path, PROTECTED_RPC_PATH_HARDWARE);
        test_eq(result.reply.length, 4);
        test_eq(result.reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(result.reply.words[1], ADAPTER_SEARCH_BYTES);
    }
    for (size_t sample = 0; sample < ADAPTER_L1D_COLD_CALLS; sample++) {
        flush_l1_data_cache();
        const uint64_t sample_start = read_cycles();
        protected_rpc_status_t status = protected_rpc_call(
            rpc_endpoint, &request, &hardware, &result);
        hardware_l1d_cold_samples[sample] = read_cycles() - sample_start;
        test_eq(status, PROTECTED_RPC_OK);
        test_eq(result.path, PROTECTED_RPC_PATH_HARDWARE);
        test_eq(result.reply.length, 4);
        test_eq(result.reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(result.reply.words[1], ADAPTER_SEARCH_BYTES);
    }
    for (size_t sample = 0; sample < ADAPTER_HIERARCHY_COLD_CALLS; sample++) {
        evict_data_cache_hierarchy();
        const uint64_t sample_start = read_cycles();
        protected_rpc_status_t status = protected_rpc_call(
            rpc_endpoint, &request, &hardware, &result);
        hardware_hierarchy_cold_samples[sample] = read_cycles() - sample_start;
        test_eq(status, PROTECTED_RPC_OK);
        test_eq(result.path, PROTECTED_RPC_PATH_HARDWARE);
        test_eq(result.reply.length, 4);
        test_eq(result.reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(result.reply.words[1], ADAPTER_SEARCH_BYTES);
    }

    /* Mapping any page into a bound VSpace must synchronously revoke before
     * the mapping becomes visible.  The first stale-token call reports that
     * execution did not begin and clears the adapter's local association;
     * a fresh generation can then bind and execute normally. */
    void *revocation_probe = vspace_new_pages(
        &env->vspace, seL4_AllRights, 1, seL4_PageBits);
    test_assert(revocation_probe != NULL);
    if (revocation_probe == NULL) {
        test_eq(protected_rpc_blackparrot_unbind(rpc_endpoint),
                PROTECTED_RPC_OK);
        destroy_rpc_server(env, &server, shadow_stack, shared_base,
                           mailbox_base, &control_endpoint);
        return sel4test_get_result();
    }
    test_eq(protected_rpc_call(rpc_endpoint, &request, &hardware, &result),
            PROTECTED_RPC_REVOKED);
    test_eq(result.path, PROTECTED_RPC_PATH_HARDWARE);
    test_eq(result.reply.length, 0);

    bind_status = protected_rpc_blackparrot_bind(rpc_endpoint, &binding);
    test_eq(bind_status, PROTECTED_RPC_OK);
    if (bind_status != PROTECTED_RPC_OK) {
        vspace_unmap_pages(&env->vspace, revocation_probe, 1,
                           seL4_PageBits, VSPACE_FREE);
        destroy_rpc_server(env, &server, shadow_stack, shared_base,
                           mailbox_base, &control_endpoint);
        return sel4test_get_result();
    }
    test_eq(protected_rpc_call(rpc_endpoint, &request, &hardware, &result),
            PROTECTED_RPC_OK);
    test_eq(result.path, PROTECTED_RPC_PATH_HARDWARE);
    test_eq(result.reply.length, 4);
    test_eq(result.reply.words[0], ADAPTER_SEARCH_BYTES - 1);
    test_eq(result.reply.words[1], ADAPTER_SEARCH_BYTES);

    test_eq(protected_rpc_blackparrot_unbind(rpc_endpoint), PROTECTED_RPC_OK);
    vspace_unmap_pages(&env->vspace, revocation_probe, 1,
                       seL4_PageBits, VSPACE_FREE);
    printf("SEL4_RPC_LIFECYCLE map-revoke=verified stale-token=verified "
           "rebind=verified\n");

    /* With the binding revoked, AUTO must make one precise non-executed
     * hardware attempt and then reach the same service through ordinary IPC. */
    const protected_rpc_call_options_t fallback = {
        .route = PROTECTED_RPC_ROUTE_AUTO,
    };
    const uint64_t fallback_start = read_cycles();
    for (seL4_Word call = 0; call < ADAPTER_BP_FALLBACK_CALLS; call++) {
        test_eq(protected_rpc_call(rpc_endpoint, &request, &fallback, &result),
                PROTECTED_RPC_OK);
        test_eq(result.path, PROTECTED_RPC_PATH_SOFTWARE);
        test_eq(result.reply.length, 4);
        test_eq(result.reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(result.reply.words[1], ADAPTER_SEARCH_BYTES);
    }
    const uint64_t fallback_elapsed = read_cycles() - fallback_start;
    seL4_MessageInfo_t finished = seL4_Recv(control_endpoint.cptr, &badge);
    test_eq(seL4_MessageInfo_get_label(finished), PROTECTED_RPC_OK);
    test_eq(seL4_MessageInfo_get_length(finished), 0);

    destroy_rpc_server(env, &server, shadow_stack, shared_base, mailbox_base,
                       &control_endpoint);
    printf("SEL4_RPC_CALLER_BADGE value=%" PRIu64
           " software=verified hardware=verified\n",
           (uint64_t)SEL4_RPC_SEARCH_CALLER_BADGE);
    printf("SEL4_RPC_WORKLOAD name=libc-bounded-search bytes=%u\n",
           ADAPTER_SEARCH_BYTES);
    printf("SEL4_RPC_ADAPTER path=in-process calls=%u total_cycles=%" PRIu64
           " cycles_per_call=%" PRIu64 "\n",
           ADAPTER_MEASURED_CALLS, direct_elapsed,
           direct_elapsed / ADAPTER_MEASURED_CALLS);
    printf("SEL4_RPC_ADAPTER path=hardware calls=%u total_cycles=%" PRIu64
           " cycles_per_call=%" PRIu64 "\n",
           ADAPTER_MEASURED_CALLS, hardware_elapsed,
           hardware_elapsed / ADAPTER_MEASURED_CALLS);
    printf("SEL4_RPC_ADAPTER path=software calls=%u total_cycles=%" PRIu64
           " cycles_per_call=%" PRIu64 "\n",
           ADAPTER_BP_SOFTWARE_CALLS, software_elapsed,
           software_elapsed / ADAPTER_BP_SOFTWARE_CALLS);
    printf("SEL4_RPC_ADAPTER path=notification calls=%u total_cycles=%" PRIu64
           " cycles_per_call=%" PRIu64 "\n",
           ADAPTER_NOTIFICATION_CALLS, notification_elapsed,
           notification_elapsed / ADAPTER_NOTIFICATION_CALLS);
    printf("SEL4_RPC_ADAPTER path=software-fallback calls=%u total_cycles=%" PRIu64
           " cycles_per_call=%" PRIu64 "\n",
           ADAPTER_BP_FALLBACK_CALLS, fallback_elapsed,
           fallback_elapsed / ADAPTER_BP_FALLBACK_CALLS);
    print_cycle_distribution("in-process", direct_samples,
                             ADAPTER_DISTRIBUTION_CALLS);
    print_cycle_distribution("hardware", hardware_samples,
                             ADAPTER_DISTRIBUTION_CALLS);
    print_cycle_distribution("software", software_samples,
                             ADAPTER_DISTRIBUTION_CALLS);
    print_cycle_distribution("notification", notification_samples,
                             ADAPTER_DISTRIBUTION_CALLS);
    printf("SEL4_RPC_TIMEBASE counter=blackparrot-global-cycle-csr-0xcc0 "
           "scope=core-wide\n");
    print_cycle_components("in-process", direct_pre_samples,
                           direct_service_samples, direct_post_samples,
                           ADAPTER_DISTRIBUTION_CALLS);
    print_cycle_components("hardware", hardware_pre_samples,
                           hardware_service_samples, hardware_post_samples,
                           ADAPTER_DISTRIBUTION_CALLS);
    print_cycle_components("software", software_pre_samples,
                           software_service_samples, software_post_samples,
                           ADAPTER_DISTRIBUTION_CALLS);
    print_cycle_components("notification", notification_pre_samples,
                           notification_service_samples,
                           notification_post_samples,
                           ADAPTER_DISTRIBUTION_CALLS);
    printf("SEL4_RPC_NOTIFICATION_BASELINE mailbox=shared-rw "
           "data-region=server-ro request-signal=notification "
           "reply-signal=notification\n");
    printf("SEL4_RPC_CACHE_STATE kind=l1d-cold lower-cache=warm "
           "method=blackparrot-flush-all samples=%u\n",
           ADAPTER_L1D_COLD_CALLS);
    print_cycle_distribution("l1d-cold/in-process", direct_l1d_cold_samples,
                             ADAPTER_L1D_COLD_CALLS);
    print_cycle_distribution("l1d-cold/hardware", hardware_l1d_cold_samples,
                             ADAPTER_L1D_COLD_CALLS);
    print_cycle_distribution("l1d-cold/software", software_l1d_cold_samples,
                             ADAPTER_L1D_COLD_CALLS);
    print_cycle_distribution("l1d-cold/notification",
                             notification_l1d_cold_samples,
                             ADAPTER_L1D_COLD_CALLS);
    printf("SEL4_RPC_CACHE_STATE kind=data-hierarchy-cold l1d=cold l2=cold "
           "l1i=warm dram-row=uncontrolled method=4x-l2-evict samples=%u\n",
           ADAPTER_HIERARCHY_COLD_CALLS);
    print_cycle_distribution("data-hierarchy-cold/in-process",
                             direct_hierarchy_cold_samples,
                             ADAPTER_HIERARCHY_COLD_CALLS);
    print_cycle_distribution("data-hierarchy-cold/hardware",
                             hardware_hierarchy_cold_samples,
                             ADAPTER_HIERARCHY_COLD_CALLS);
    print_cycle_distribution("data-hierarchy-cold/software",
                             software_hierarchy_cold_samples,
                             ADAPTER_HIERARCHY_COLD_CALLS);
    print_cycle_distribution("data-hierarchy-cold/notification",
                             notification_hierarchy_cold_samples,
                             ADAPTER_HIERARCHY_COLD_CALLS);
    return 0;
}
#endif

#if defined(SEL4TEST_RPC_ONLY) && !defined(CONFIG_PLAT_BLACKPARROT)
/* Qualify the dedicated server image and control handshake under fast QEMU.
 * BlackParrot runs the same image through the hardware/fallback gate above. */
static int test_dedicated_search_server_software(env_t env)
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

    void *shared_base = vspace_new_pages(
        &env->vspace, seL4_AllRights, 1, seL4_PageBits);
    test_assert(shared_base != NULL);
    if (shared_base == NULL) {
        destroy_rpc_server(env, &server, NULL, NULL, NULL, &control_endpoint);
        return sel4test_get_result();
    }
    memset(shared_base, 'a', ADAPTER_SEARCH_BYTES);
    ((unsigned char *)shared_base)[ADAPTER_SEARCH_BYTES - 1] =
        (unsigned char)ADAPTER_SEARCH_NEEDLE;
    void *server_shared_base = vspace_share_mem(
        &env->vspace, &server.vspace, shared_base, 1, seL4_PageBits,
        seL4_CapRights_new(false, false, true, false), true);
    test_assert(server_shared_base != NULL);
    if (server_shared_base == NULL) {
        destroy_rpc_server(env, &server, NULL, shared_base, NULL,
                           &control_endpoint);
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
        destroy_rpc_server(env, &server, NULL, shared_base, NULL,
                           &control_endpoint);
        return sel4test_get_result();
    }

    char arg_strings[ADAPTER_SOFTWARE_SERVER_ARGS][WORD_STRING_SIZE];
    char *args[ADAPTER_SOFTWARE_SERVER_ARGS];
    sel4utils_create_word_args(arg_strings, args, ADAPTER_SOFTWARE_SERVER_ARGS,
                               remote_endpoint, remote_control,
                               (seL4_Word)server_shared_base,
                               ADAPTER_REGION_TOKEN);
    error = sel4utils_spawn_process_v(&server, &env->vka, &env->vspace,
                                      ADAPTER_SOFTWARE_SERVER_ARGS, args, 1);
    test_eq(error, 0);
    if (error != 0) {
        destroy_rpc_server(env, &server, NULL, shared_base, NULL,
                           &control_endpoint);
        return sel4test_get_result();
    }

    seL4_Word badge = 0;
    seL4_MessageInfo_t ready = seL4_Recv(control_endpoint.cptr, &badge);
    test_eq(seL4_MessageInfo_get_label(ready), 0);
    test_eq(seL4_MessageInfo_get_length(ready), 3);
#if defined(CONFIG_PLAT_BLACKPARROT)
    test_assert(seL4_GetMR(0) != 0);
    test_assert(seL4_GetMR(1) != 0);
    test_assert(seL4_GetMR(2) != 0);
#endif

    const protected_rpc_endpoint_t rpc_endpoint = {.opaque = endpoint};
    const protected_rpc_call_options_t software = {
        .route = PROTECTED_RPC_ROUTE_SOFTWARE,
    };
    protected_rpc_message_t request = {0};
    const protected_rpc_buffer_ref_t search_ref = {
        .region = {.opaque = ADAPTER_REGION_TOKEN},
        .offset = 0,
        .length = ADAPTER_SEARCH_BYTES,
    };
    test_assert(protected_rpc_encode_buffer(&request, 0, search_ref));
    request.words[3] = ADAPTER_SEARCH_NEEDLE;
    request.length = 4;
    protected_rpc_call_result_t result;
    uint64_t start = 0;
    uint64_t elapsed = 0;
    for (seL4_Word call = 0;
         call < SEL4_RPC_SEARCH_SOFTWARE_REQUESTS; call++) {
        if (call == ADAPTER_WARMUP_CALLS) {
            start = read_cycles();
        } else if (call == ADAPTER_WARMUP_CALLS
                           + ADAPTER_BP_SOFTWARE_CALLS) {
            elapsed = read_cycles() - start;
        }
        test_eq(protected_rpc_call(rpc_endpoint, &request, &software, &result),
                PROTECTED_RPC_OK);
        test_eq(result.path, PROTECTED_RPC_PATH_SOFTWARE);
        test_eq(result.reply.length, 4);
        test_eq(result.reply.words[0], ADAPTER_SEARCH_BYTES - 1);
        test_eq(result.reply.words[1], ADAPTER_SEARCH_BYTES);
    }

    seL4_MessageInfo_t finished = seL4_Recv(control_endpoint.cptr, &badge);
    test_eq(seL4_MessageInfo_get_label(finished), PROTECTED_RPC_OK);
    test_eq(seL4_MessageInfo_get_length(finished), 0);
    destroy_rpc_server(env, &server, NULL, shared_base, NULL,
                       &control_endpoint);

    printf("SEL4_RPC_WORKLOAD name=libc-bounded-search bytes=%u\n",
           ADAPTER_SEARCH_BYTES);
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
    return test_dedicated_search_server_software(env);
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
