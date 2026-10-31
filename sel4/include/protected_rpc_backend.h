#ifndef PROTECTED_RPC_BACKEND_H
#define PROTECTED_RPC_BACKEND_H

#include "protected_rpc.h"

/*
 * Result of one atomic backend attempt.  There is intentionally no separate
 * eligibility probe: checking and committing must not race revocation,
 * scheduling changes, or endpoint state.
 */
typedef enum {
    /* Service definitely did not begin; AUTO must invoke software exactly once. */
    PROTECTED_RPC_ATTEMPT_FALLBACK_SAFE = 0,

    /* Service completed and reply is valid. */
    PROTECTED_RPC_ATTEMPT_COMPLETED,

    /* Service did not begin, but policy/arguments forbid fallback. */
    PROTECTED_RPC_ATTEMPT_REJECTED,

    /* Service crossed its commit point and failed; it must never be retried. */
    PROTECTED_RPC_ATTEMPT_COMMITTED_FAILED,
} protected_rpc_attempt_disposition_t;

typedef struct {
    protected_rpc_attempt_disposition_t disposition;
    protected_rpc_status_t status;
    protected_rpc_path_t path;
    protected_rpc_message_t reply;
} protected_rpc_attempt_result_t;

typedef protected_rpc_status_t (*protected_rpc_try_call_fn)(
    protected_rpc_endpoint_t endpoint,
    const protected_rpc_message_t *request,
    protected_rpc_attempt_result_t *result);

typedef struct {
    protected_rpc_try_call_fn try_call;
} protected_rpc_backend_t;

extern const protected_rpc_backend_t protected_rpc_software_backend;
extern const protected_rpc_backend_t protected_rpc_hardware_backend;

#endif
