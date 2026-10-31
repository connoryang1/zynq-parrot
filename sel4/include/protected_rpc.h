#ifndef PROTECTED_RPC_H
#define PROTECTED_RPC_H

#include <stddef.h>
#include <stdint.h>

/*
 * Backend-neutral synchronous protected-RPC API.
 *
 * Endpoint and region values are opaque, kernel-issued authority.  They are
 * never a hardware context number, SATP, entry PC, or virtual address.
 */

#define PROTECTED_RPC_MAX_WORDS 4u
#define PROTECTED_RPC_BUFFER_WORDS 3u

typedef struct {
    uint64_t opaque;
} protected_rpc_endpoint_t;

typedef struct {
    uint64_t opaque;
} protected_rpc_region_t;

typedef struct {
    uint8_t length;
    uint64_t words[PROTECTED_RPC_MAX_WORDS];
} protected_rpc_message_t;

/*
 * A shared buffer is identified by a registered region plus a byte range.
 * It consumes three message words when encoded.  Region permissions and
 * direction are fixed when the kernel creates the binding; a caller cannot
 * widen them by changing message data.
 */
typedef struct {
    protected_rpc_region_t region;
    uint64_t offset;
    uint64_t length;
} protected_rpc_buffer_ref_t;

typedef enum {
    PROTECTED_RPC_ROUTE_AUTO = 0,
    PROTECTED_RPC_ROUTE_SOFTWARE,
    PROTECTED_RPC_ROUTE_HARDWARE,
} protected_rpc_route_t;

typedef enum {
    PROTECTED_RPC_PATH_NONE = 0,
    PROTECTED_RPC_PATH_SOFTWARE,
    PROTECTED_RPC_PATH_HARDWARE,
} protected_rpc_path_t;

typedef enum {
    PROTECTED_RPC_OK = 0,
    PROTECTED_RPC_INVALID_ARGUMENT,
    PROTECTED_RPC_DENIED,
    PROTECTED_RPC_REVOKED,
    PROTECTED_RPC_UNSUPPORTED,
    PROTECTED_RPC_SERVER_FAULT,
    PROTECTED_RPC_CANCELED,
    PROTECTED_RPC_BACKEND_ERROR,
} protected_rpc_status_t;

typedef struct {
    protected_rpc_route_t route;
} protected_rpc_call_options_t;

typedef struct {
    protected_rpc_status_t status;
    protected_rpc_path_t path;
    protected_rpc_message_t reply;
} protected_rpc_call_result_t;

/*
 * Execute one synchronous request.  AUTO may use software only when a
 * hardware attempt reports that the service has definitely not begun.
 * HARDWARE never silently falls back, which makes matched tests auditable.
 */
protected_rpc_status_t protected_rpc_call(
    protected_rpc_endpoint_t endpoint,
    const protected_rpc_message_t *request,
    const protected_rpc_call_options_t *options,
    protected_rpc_call_result_t *result);

typedef struct {
    uint64_t caller_badge;
    void *runtime_private;
} protected_rpc_call_context_t;

typedef enum {
    PROTECTED_RPC_ACCESS_READ = 1u << 0,
    PROTECTED_RPC_ACCESS_WRITE = 1u << 1,
} protected_rpc_access_t;

typedef struct {
    void *data;
    uint64_t length;
} protected_rpc_buffer_view_t;

/*
 * Resolve a reference using the service's local mapping.  The runtime checks
 * the region generation, complete byte range, and binding-time permissions;
 * service code must never cast the opaque region value into a pointer.
 */
protected_rpc_status_t protected_rpc_resolve_buffer(
    const protected_rpc_call_context_t *context,
    protected_rpc_buffer_ref_t ref,
    protected_rpc_access_t required_access,
    protected_rpc_buffer_view_t *view);

typedef protected_rpc_status_t (*protected_rpc_handler_t)(
    const protected_rpc_call_context_t *context,
    const protected_rpc_message_t *request,
    protected_rpc_message_t *reply,
    void *cookie);

typedef struct {
    protected_rpc_region_t region;
    void *local_base;
    uint64_t size;
    uint32_t access;
} protected_rpc_region_binding_t;

typedef struct {
    protected_rpc_handler_t handler;
    void *cookie;
    const protected_rpc_region_binding_t *regions;
    size_t region_count;

    /* Zero serves forever; a finite count is useful for tests and teardown. */
    uint64_t max_requests;
} protected_rpc_server_config_t;

/*
 * Run the same handler body behind either a seL4 ReplyRecv loop or a protected
 * hardware entry/return stub.  The runtime, not the handler, owns reply
 * authority and continuation state.
 */
protected_rpc_status_t protected_rpc_serve(
    protected_rpc_endpoint_t endpoint,
    const protected_rpc_server_config_t *config);

static inline int protected_rpc_message_valid(
    const protected_rpc_message_t *message)
{
    return message != NULL && message->length <= PROTECTED_RPC_MAX_WORDS;
}

static inline int protected_rpc_buffer_range_valid(
    uint64_t region_size, const protected_rpc_buffer_ref_t *ref)
{
    return ref != NULL && ref->offset <= region_size
           && ref->length <= region_size - ref->offset;
}

static inline int protected_rpc_encode_buffer(
    protected_rpc_message_t *message, size_t first_word,
    protected_rpc_buffer_ref_t ref)
{
    if (message == NULL
        || first_word > PROTECTED_RPC_MAX_WORDS - PROTECTED_RPC_BUFFER_WORDS) {
        return 0;
    }

    message->words[first_word] = ref.region.opaque;
    message->words[first_word + 1] = ref.offset;
    message->words[first_word + 2] = ref.length;
    if (message->length < first_word + PROTECTED_RPC_BUFFER_WORDS) {
        message->length = (uint8_t)(first_word + PROTECTED_RPC_BUFFER_WORDS);
    }
    return 1;
}

static inline int protected_rpc_decode_buffer(
    const protected_rpc_message_t *message, size_t first_word,
    protected_rpc_buffer_ref_t *ref)
{
    if (!protected_rpc_message_valid(message) || ref == NULL
        || first_word > message->length
        || message->length - first_word < PROTECTED_RPC_BUFFER_WORDS) {
        return 0;
    }

    ref->region.opaque = message->words[first_word];
    ref->offset = message->words[first_word + 1];
    ref->length = message->words[first_word + 2];
    return 1;
}

#endif
