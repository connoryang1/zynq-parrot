#ifndef PROTECTED_RPC_BLACKPARROT_H
#define PROTECTED_RPC_BLACKPARROT_H

#include <stdint.h>

#include "protected_rpc.h"

/*
 * Trusted seL4 runtime input. The kernel derives both address spaces, the
 * endpoint badge, slot, token, and hardware context IDs. These values name
 * only the fixed server entry state inside the server's own VSpace.
 */
typedef struct {
    protected_rpc_region_t region;
    uint64_t caller_base;
    uint64_t server_base;
    uint64_t size;
    uint32_t access;
} protected_rpc_blackparrot_region_binding_t;

typedef struct {
    uint64_t server_tcb;
    uint64_t server_entry;
    uint64_t server_sp;
    uint64_t server_gp;
    uint64_t server_tp;
    uint8_t request_words;
    uint8_t reply_words;
    /* Version 1 supports zero or one page-sized, physically shared region. */
    protected_rpc_blackparrot_region_binding_t region;
} protected_rpc_blackparrot_binding_t;

/*
 * Fixed protected-entry state exported by the trusted server runtime. Service
 * code supplies only its transport-neutral dispatcher configuration; it never
 * reads hardware-installed registers or emits the protected-return CSR.
 */
typedef struct {
    uint64_t server_entry;
    uint64_t server_gp;
    uint64_t server_tp;
} protected_rpc_blackparrot_server_runtime_t;

protected_rpc_status_t protected_rpc_blackparrot_server_prepare(
    const protected_rpc_server_config_t *config,
    protected_rpc_blackparrot_server_runtime_t *runtime);

#ifdef PROTECTED_RPC_BLACKPARROT_SERVER_TEST_HOOK
protected_rpc_status_t protected_rpc_blackparrot_server_test_dispatch(
    const protected_rpc_server_config_t *config, uint64_t caller_badge,
    uint64_t request_meta, uint64_t words[PROTECTED_RPC_MAX_WORDS],
    uint64_t *reply_meta);
#endif

/*
 * Atomically create/remove the kernel binding and update the caller adapter.
 * The returned kernel token never crosses this trusted-runtime boundary;
 * application code continues to call protected_rpc_call() with its endpoint.
 */
protected_rpc_status_t protected_rpc_blackparrot_bind(
    protected_rpc_endpoint_t endpoint,
    const protected_rpc_blackparrot_binding_t *binding);

protected_rpc_status_t protected_rpc_blackparrot_unbind(
    protected_rpc_endpoint_t endpoint);

#endif
