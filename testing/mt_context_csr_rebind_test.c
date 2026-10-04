/* Verify explicit CSR-image rebinding for an initialized resident context.
 * Ordinary NPC reseeding must preserve the target's private CSRs. Rebinding
 * must then clone the caller's current CSRs without disturbing target GPRs.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "CSR rebind regression requires two resident slots and four contexts"
#endif

#define SOURCE_FIRST UINT64_C(0x111)
#define SOURCE_REBIND UINT64_C(0x333)
#define TARGET_PRIVATE UINT64_C(0x222)
#define TARGET_INITIAL_GPR UINT64_C(0x1234)
#define TARGET_PRIVATE_GPR UINT64_C(0x5678)
#define SOURCE_GPR UINT64_C(0x6abc)

static volatile struct {
  uint64_t context[3];
  uint64_t scratch[3];
  uint64_t satp[3];
  uint64_t gpr[3];
} result;

#define TARGET_ENTRY(name, index, update)                                      \
static __attribute__((naked, noinline, noreturn, used, aligned(8)))            \
void name(void)                                                                \
{                                                                              \
  __asm__ volatile(                                                            \
    ".option push\n.option norvc\nla t0, result\n"                            \
    "csrr t1, 0x800\nsd t1, " #index "*8(t0)\n"                              \
    "csrr t1, mscratch\nsd t1, (3+" #index ")*8(t0)\n"                     \
    "csrr t1, satp\nsd t1, (6+" #index ")*8(t0)\n"                         \
    "sd s11, (9+" #index ")*8(t0)\n" update                                 \
    "fence rw, rw\ncsrwi 0x800, 0\n1: j 1b\n.option pop\n");                  \
}

TARGET_ENTRY(target_first, 0,
  "li t1, 0x222\ncsrw mscratch, t1\ncsrw satp, t1\nli s11, 0x5678\n")
TARGET_ENTRY(target_ordinary, 1, "")
TARGET_ENTRY(target_rebound, 2, "")

int main(void)
{
  uint64_t source_scratch, source_satp, source_gpr, source_gp;
  __asm__ volatile("li s11, 0x6abc\nli t0, 0x111\n"
                   "csrw mscratch, t0\ncsrw satp, t0"
                   : : : "s11", "t0", "memory");
  __asm__ volatile("mv %0, gp" : "=r"(source_gp));
  seed_reg(1, 3, source_gp);
  seed_reg(1, 27, TARGET_INITIAL_GPR);
  seed_npc(1, (uint64_t)target_first);
  __asm__ volatile("csrwi 0x800, 1" : : : "memory");

  seed_npc(1, (uint64_t)target_ordinary);
  __asm__ volatile("csrwi 0x800, 1" : : : "memory");

  __asm__ volatile("li t0, 0x333\ncsrw mscratch, t0\ncsrw satp, t0"
                   : : : "t0", "memory");
  seed_npc_rebind(1, (uint64_t)target_rebound);
  __asm__ volatile("csrwi 0x800, 1" : : : "memory");

  __asm__ volatile("csrr %0, mscratch\ncsrr %1, satp\nmv %2, s11"
                   : "=r"(source_scratch), "=r"(source_satp), "=r"(source_gpr));
  const int pass = result.context[0] == 1 && result.context[1] == 1
    && result.context[2] == 1
    && result.scratch[0] == SOURCE_FIRST
    && result.satp[0] == SOURCE_FIRST
    && result.gpr[0] == TARGET_INITIAL_GPR
    && result.scratch[1] == TARGET_PRIVATE
    && result.satp[1] == TARGET_PRIVATE
    && result.gpr[1] == TARGET_PRIVATE_GPR
    && result.scratch[2] == SOURCE_REBIND
    && result.satp[2] == SOURCE_REBIND
    && result.gpr[2] == TARGET_PRIVATE_GPR
    && source_scratch == SOURCE_REBIND && source_satp == SOURCE_REBIND
    && source_gpr == SOURCE_GPR;
  if (pass) {
    bp_print_string("[BSG-PASS] resident context CSR rebind preserved target GPR state\n");
    bp_finish(0);
  }
  bp_print_string("[BSG-FAIL] resident context CSR rebind\n");
  for (int i = 0; i < 3; ++i) {
    bp_hprint_uint64(result.context[i]);
    bp_hprint_uint64(result.scratch[i]);
    bp_hprint_uint64(result.satp[i]);
    bp_hprint_uint64(result.gpr[i]);
  }
  bp_hprint_uint64(source_scratch);
  bp_hprint_uint64(source_satp);
  bp_hprint_uint64(source_gpr);
  bp_finish(1);
  return 1;
}
