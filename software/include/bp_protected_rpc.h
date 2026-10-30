#ifndef BP_PROTECTED_RPC_H
#define BP_PROTECTED_RPC_H

#include <stddef.h>
#include <stdint.h>

/*
 * A pointer is meaningful only in the address space that created it.  Shared
 * RPC buffers therefore travel across the ABI as offsets into an explicitly
 * shared region, never as raw virtual addresses.  Each side translates the
 * offset using its own mapping and validates the complete byte range first.
 */
typedef uint64_t bp_rpc_offset_t;

static inline int
bp_rpc_shared_range_valid(size_t region_size, bp_rpc_offset_t offset,
                          size_t length)
{
  return offset <= region_size && length <= region_size - (size_t)offset;
}

static inline void *
bp_rpc_shared_ptr(void *local_base, size_t region_size, bp_rpc_offset_t offset,
                  size_t length)
{
  if (!bp_rpc_shared_range_valid(region_size, offset, length))
    return NULL;
  return (uint8_t *)local_base + (size_t)offset;
}

/*
 * Invoke a monitor-installed protected service.  The current hardware ABI
 * carries four argument registers across pcall and one result register across
 * preturn.  Capability 1 is the sole descriptor implemented by the prototype.
 */
static inline uint64_t
bp_protected_rpc_call4(uint64_t capability, uint64_t arg0, uint64_t arg1,
                       uint64_t arg2, uint64_t arg3)
{
  register uint64_t rpc_a0 __asm__("a0") = arg0;
  register uint64_t rpc_a1 __asm__("a1") = arg1;
  register uint64_t rpc_a2 __asm__("a2") = arg2;
  register uint64_t rpc_a3 __asm__("a3") = arg3;
  register uint64_t rpc_cap __asm__("a4") = capability;

  __asm__ volatile(
    "csrw 0x808, %4"
    : "+r"(rpc_a0), "+r"(rpc_a1), "+r"(rpc_a2), "+r"(rpc_a3)
    : "r"(rpc_cap)
    : "memory");
  return rpc_a0;
}

#endif
