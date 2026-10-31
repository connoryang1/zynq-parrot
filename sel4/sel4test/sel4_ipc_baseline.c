/*
 * Matched seL4 synchronous IPC baseline for the protected-RPC backend.
 * The server is cloned into a separate CSpace/VSpace by the sel4test helpers.
 */

#include <inttypes.h>
#include <stdio.h>
#include <sel4/sel4.h>
#include <sel4utils/process.h>
#include <vka/capops.h>
#include <vka/object.h>

#include "../helpers.h"

#define IPC_WARMUP_CALLS  8
#define IPC_MEASURED_CALLS 256
#define IPC_TOTAL_CALLS   (IPC_WARMUP_CALLS + IPC_MEASURED_CALLS)

static volatile seL4_Word server_private_counter;

static inline uint64_t read_cycles(void)
{
    uint64_t value;
    __asm__ volatile("rdcycle %0" : "=r"(value));
    return value;
}

static seL4_Word service_result(seL4_Word arg0, seL4_Word arg1,
                                seL4_Word arg2, seL4_Word arg3,
                                seL4_Word counter)
{
    return arg0 + arg1 + 2 * arg2 + 4 * arg3 + counter;
}

static int ipc_baseline_server(seL4_Word endpoint, seL4_Word total_calls,
                               seL4_Word unused2, seL4_Word unused3)
{
    seL4_MessageInfo_t request = seL4_Recv(endpoint, NULL);

    for (seL4_Word call = 0; call < total_calls; call++) {
        const seL4_Word arg0 = seL4_GetMR(0);
        const seL4_Word arg1 = seL4_GetMR(1);
        const seL4_Word arg2 = seL4_GetMR(2);
        const seL4_Word arg3 = seL4_GetMR(3);

        server_private_counter++;
        const seL4_Word valid = seL4_MessageInfo_get_length(request) == 4;
        const seL4_Word result = valid
                                 ? service_result(arg0, arg1, arg2, arg3,
                                                  server_private_counter)
                                 : UINT64_MAX;

        seL4_SetMR(0, result);
        seL4_SetMR(1, server_private_counter);
        const seL4_MessageInfo_t reply = seL4_MessageInfo_new(0, 0, 0, 2);

        if (call + 1 == total_calls) {
            seL4_Reply(reply);
        } else {
            request = seL4_ReplyRecv(endpoint, reply, NULL);
        }
    }

    return SUCCESS;
}

static int test_sel4_ipc_rpc_baseline(env_t env)
{
    helper_thread_t server;
    cspacepath_t endpoint_path;
    seL4_CPtr endpoint = vka_alloc_endpoint_leaky(&env->vka);
    test_assert(endpoint != 0);

    server_private_counter = 0;
    create_helper_process(env, &server);
    set_helper_priority(env, &server, OUR_PRIO);

    vka_cspace_make_path(&env->vka, endpoint, &endpoint_path);
    const seL4_CPtr remote_endpoint =
        sel4utils_copy_path_to_process(&server.process, endpoint_path);
    test_assert(remote_endpoint != (seL4_CPtr)-1);

    start_helper(env, &server, (helper_fn_t)ipc_baseline_server,
                 remote_endpoint, IPC_TOTAL_CALLS, 0, 0);

    uint64_t start = 0;
    for (seL4_Word call = 0; call < IPC_TOTAL_CALLS; call++) {
        const seL4_Word arg0 = 7 + call;
        const seL4_Word arg1 = 9 + call;
        const seL4_Word arg2 = 3 + call;
        const seL4_Word arg3 = 5 + call;

        seL4_SetMR(0, arg0);
        seL4_SetMR(1, arg1);
        seL4_SetMR(2, arg2);
        seL4_SetMR(3, arg3);

        if (call == IPC_WARMUP_CALLS) {
            start = read_cycles();
        }
        const seL4_MessageInfo_t reply =
            seL4_Call(endpoint, seL4_MessageInfo_new(0, 0, 0, 4));

        const seL4_Word counter = call + 1;
        test_eq(seL4_MessageInfo_get_length(reply), 2);
        test_eq(seL4_GetMR(0), service_result(arg0, arg1, arg2, arg3,
                                               counter));
        test_eq(seL4_GetMR(1), counter);
    }
    const uint64_t elapsed = read_cycles() - start;

    test_eq(wait_for_helper(&server), SUCCESS);
    test_eq(server_private_counter, 0);
    cleanup_helper(env, &server);

    printf("SEL4_IPC_BASELINE calls=%u total_cycles=%" PRIu64
           " cycles_per_call=%" PRIu64 "\n",
           IPC_MEASURED_CALLS, elapsed, elapsed / IPC_MEASURED_CALLS);
    return sel4test_get_result();
}

DEFINE_TEST(SEL4IPCRPC0001,
            "Cross-address-space four-register synchronous IPC baseline",
            test_sel4_ipc_rpc_baseline,
            !config_set(CONFIG_KERNEL_MCS))
