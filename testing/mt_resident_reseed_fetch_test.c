/* Exercise a cold first fetch after reseeding an already-resident U context.
 * The second NPC operand was captured and validated in Linux: 0x8000011cb8
 * (logical context 1, VA 0x11cb8). A controlled Sv39 code-page mapping keeps
 * that entry address while isolating cache/replay behavior from Linux. This
 * is a correctness regression, not a reproduction of the full Linux process.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "Resident reseed regression requires two resident slots and four logical contexts"
#endif

#define DRAM_BASE 0x80000000ULL
#define SOURCE_ALIAS 0x40000000ULL
#define FIRST_ENTRY 0x11c18ULL
#define SECOND_ENTRY 0x11cb8ULL
#define SOURCE_CSR 0x1357ULL
#define TARGET_CSR 0x2468ULL
#define INITIAL_GPR 0x1234ULL
#define PRIVATE_GPR 0x5678ULL

/* This buffer contains no PC-relative references outside itself. Padding
 * places instructions at the captured virtual offsets, not timing gaps.
 * The first return PC deliberately reports failure if stale APC/replay sends
 * the second launch there, so the baseline need not spin until timeout.
 */
extern const unsigned char reseed_code_page[];
__asm__(
  ".pushsection .rodata.reseed_code,\"a\",@progbits\n"
  ".balign 4096\n.global reseed_code_page\nreseed_code_page:\n"
  ".option push\n.option norvc\n"
  ".org reseed_code_page + 0xc18\n"
  ".global reseed_first_entry\nreseed_first_entry:\n"
  "li a0, 1\necall\n"
  "addi a1, a1, 4\naddi a2, a2, -1\nli s11, 0x5678\n"
  "fence rw, rw\ncsrwi 0x800, 0\n"
  ".global reseed_old_park\nreseed_old_park:\n"
  "li a0, 127\necall\n1: j 1b\n"
  ".org reseed_code_page + 0xcb8\n"
  ".global reseed_second_entry\nreseed_second_entry:\n"
  "li a0, 2\necall\nfence rw, rw\ncsrwi 0x800, 0\n"
  "li a0, 127\necall\n2: j 2b\n"
  ".org reseed_code_page + 4096\n"
  ".option pop\n.popsection\n");

static uint64_t root[512] __attribute__((aligned(4096)));
static uint64_t middle[512] __attribute__((aligned(4096)));
static uint64_t leaves[512] __attribute__((aligned(4096)));
static uint64_t peer_stack[128] __attribute__((aligned(16)));
static uint64_t expected_satp, peer_sp, peer_gp;

/* Fixed 64-bit slots are shared with the naked M-mode trap handler below. */
static volatile struct {
  uint64_t first_seen, second_seen, old_park, unexpected;
  uint64_t cause, pc, tval, finish_context, finish_scratch, finish_satp;
  uint64_t target_scratch, target_s11, target_a1, target_a2;
} outcome __attribute__((used));

static void __attribute__((used, noinline, noreturn)) machine_finish(void)
{
  if (outcome.first_seen == 1 && outcome.second_seen == 1
      && !outcome.old_park && !outcome.unexpected
      && outcome.finish_context == 0 && outcome.finish_scratch == SOURCE_CSR
      && outcome.finish_satp == expected_satp
      && outcome.target_scratch == TARGET_CSR && outcome.target_s11 == PRIVATE_GPR
      && outcome.target_a1 == 0x300 && outcome.target_a2 == 7) {
    bp_print_string("[BSG-PASS] resident reseed cold-fetch and CSR preservation\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] resident reseed cold-fetch and CSR preservation\n");
    if (outcome.old_park)
      bp_print_string("stale return reached the previous target park path\n");
    bp_print_string("first/second/old-park/unexpected/cause/pc/tval: ");
    bp_hprint_uint64(outcome.first_seen);
    bp_hprint_uint64(outcome.second_seen);
    bp_hprint_uint64(outcome.old_park);
    bp_hprint_uint64(outcome.unexpected);
    bp_hprint_uint64(outcome.cause);
    bp_hprint_uint64(outcome.pc);
    bp_hprint_uint64(outcome.tval);
    bp_print_string("\nfinish context/mscratch/satp; target mscratch/s11/a1/a2: ");
    bp_hprint_uint64(outcome.finish_context);
    bp_hprint_uint64(outcome.finish_scratch);
    bp_hprint_uint64(outcome.finish_satp);
    bp_hprint_uint64(outcome.target_scratch);
    bp_hprint_uint64(outcome.target_s11);
    bp_hprint_uint64(outcome.target_a1);
    bp_hprint_uint64(outcome.target_a2);
    bp_print_string("\n");
    bp_finish(1);
  }
  for (;;) ;
}

/* Every entry must be a checked U ECALL. Target CSR writes happen here because
 * U-mode cannot access mscratch. They establish a private target CSR value
 * that an overly broad 'clone CSR state on every reseed' fix would destroy.
 * The handler uses only t0/t1/t2 and leaves the peer's arguments/s11 intact.
 */
static void __attribute__((naked, aligned(4))) trap_entry(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "la t2, outcome\n"
    "csrr t0, mcause\nsd t0, 32(t2)\n"
    "csrr t0, mepc\nsd t0, 40(t2)\n"
    "csrr t0, mtval\nsd t0, 48(t2)\n"
    "csrr t0, 0x800\nsd t0, 56(t2)\n"
    "csrr t1, mscratch\nsd t1, 64(t2)\n"
    "li t1, 1\nbne t0, t1, 1f\n"
    "csrr t0, mscratch\nsd t0, 80(t2)\nsd s11, 88(t2)\n"
    "sd a1, 96(t2)\nsd a2, 104(t2)\n"
    "1: csrr t0, satp\nsd t0, 72(t2)\n"
    "la t1, expected_satp\nld t1, 0(t1)\nbne t0, t1, 8f\n"
    "ld t0, 32(t2)\nli t1, 8\nbne t0, t1, 8f\n"
    "li t0, 127\nbeq a0, t0, 7f\n"
    "li t0, 3\nbeq a0, t0, 6f\n"
    "ld t0, 56(t2)\nli t1, 1\nbne t0, t1, 8f\n"
    "li t0, 1\nbeq a0, t0, 2f\n"
    "li t0, 2\nbeq a0, t0, 3f\nj 8f\n"
    /* First entry: inherited CSR and original remote arguments. */
    "2: ld t0, 0(t2)\nbnez t0, 8f\n"
    "csrr t0, mepc\nli t1, 0x11c1c\nbne t0, t1, 8f\n"
    "csrr t0, mscratch\nli t1, 0x1357\nbne t0, t1, 8f\n"
    "li t0, 0x1234\nbne s11, t0, 8f\n"
    "li t0, 0x100\nbne a1, t0, 8f\nli t0, 1\nbne a2, t0, 8f\n"
    "sd t0, 0(t2)\nli t0, 0x2468\ncsrw mscratch, t0\nj 4f\n"
    /* Second entry: private CSR/GPR preserved, consumed arguments reseeded. */
    "3: ld t0, 0(t2)\nli t1, 1\nbne t0, t1, 8f\n"
    "ld t0, 8(t2)\nbnez t0, 8f\n"
    "csrr t0, mepc\nli t1, 0x11cbc\nbne t0, t1, 8f\n"
    "csrr t0, mscratch\nli t1, 0x2468\nbne t0, t1, 8f\n"
    "li t0, 0x5678\nbne s11, t0, 8f\n"
    "li t0, 0x300\nbne a1, t0, 8f\nli t0, 7\nbne a2, t0, 8f\n"
    "li t0, 1\nsd t0, 8(t2)\n"
    "4: csrr t0, mepc\naddi t0, t0, 4\ncsrw mepc, t0\nmret\n"
    "6: ld t0, 56(t2)\nbnez t0, 8f\nj 9f\n"
    "7: li t0, 1\nsd t0, 16(t2)\nj 9f\n"
    "8: li t0, 1\nsd t0, 24(t2)\n"
    "9: csrr t0, mstatus\nli t1, 0x1800\nor t0, t0, t1\ncsrw mstatus, t0\n"
    "la t0, machine_finish\ncsrw mepc, t0\nmret\n"
    ".option pop\n");
}

static void __attribute__((noinline, noreturn, aligned(4096))) user_entry(void)
{
  seed_reg(1, 3, peer_gp);
  seed_reg(1, 2, peer_sp);
  seed_reg(1, 27, INITIAL_GPR);
  seed_reg(1, 11, 0x100);
  seed_reg(1, 12, 1);
  seed_npc(1, FIRST_ENTRY);
  __asm__ volatile("csrwi 0x800, 1" : : : "memory");

  /* The completed peer has advanced a1, exhausted a2, changed private s11,
   * and retained TARGET_CSR. Preserve its private state while reseeding only
   * the arguments and NPC. Source code occupies another physical/virtual page.
   */
  const uint64_t peer_id = (1ULL & BP_TID_MASK) << BP_TID_SHIFT;
  const uint64_t a1_seed = peer_id | ((11ULL & BP_REG_MASK) << BP_REG_SHIFT)
    | (0x300ULL & BP_VAL_MASK);
  const uint64_t a2_seed = peer_id | ((12ULL & BP_REG_MASK) << BP_REG_SHIFT)
    | (7ULL & BP_VAL_MASK);
  const uint64_t next_npc = peer_id | (SECOND_ENTRY & BP_NPC_MASK);
  /* Prepare the register-form switch target before the argument writes and
   * fence, so its rs1 dependency cannot mask the NPC-seed dependency. Keep
   * the NPC write and switch adjacent within one assembly block; the first
   * launch above independently covers the immediate switch form.
   */
  __asm__ volatile(
    "li t3, 1\n"
    "csrw 0x802, %[a1_seed]\n"
    "csrw 0x802, %[a2_seed]\n"
    "fence.i\n"
    "csrw 0x801, %[next_npc]\n"
    "csrw 0x800, t3"
    : : [a1_seed] "r"(a1_seed), [a2_seed] "r"(a2_seed), [next_npc] "r"(next_npc)
    : "t3", "memory");
  register uint64_t finish_code __asm__("a0") = 3;
  __asm__ volatile("ecall" : "+r"(finish_code) : : "t0", "t1", "t2", "memory");
  for (;;) ;
}

int main(void)
{
  uint64_t status, gp;
  volatile uint64_t user_pc = (uint64_t)user_entry;
  bp_print_string("[BSG-INFO] resident reseed at captured VA 0x11cb8 with cold first fetch\n");
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile(
    "csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:"
    : : : "t0", "memory");
#endif
  __asm__ volatile("csrw medeleg, zero\ncsrw mideleg, zero\ncsrw mie, zero"
                   : : : "memory");
  const uint64_t broad = PTE_V | PTE_R | PTE_W | PTE_X | PTE_U | PTE_A | PTE_D;
  /* The source's code alias and its original physical stack/gp alias map DRAM.
   * Only low VA page 0x11000 maps the controlled instruction buffer. This is
   * intentionally a small page-table environment, not Linux address-space state.
   */
  root[1] = ((DRAM_BASE >> 12) << 10) | broad;
  root[2] = root[1];
  root[0] = ((((uint64_t)middle & 0xffffffffULL) >> 12) << 10) | PTE_V;
  middle[0] = ((((uint64_t)leaves & 0xffffffffULL) >> 12) << 10) | PTE_V;
  leaves[0x11] = ((((uint64_t)reseed_code_page & 0xffffffffULL) >> 12) << 10)
    | PTE_V | PTE_R | PTE_X | PTE_U | PTE_A;
  peer_sp = (uint64_t)&peer_stack[128] & 0xffffffffULL;
  __asm__ volatile("mv %0, gp" : "=r"(gp));
  peer_gp = gp & 0xffffffffULL;
  expected_satp = (8ULL << 60) | (((uint64_t)root & 0xffffffffULL) >> 12);
  __asm__ volatile("fence rw, rw\ncsrw satp, %0\nsfence.vma\nfence.i"
                   : : "r"(expected_satp) : "memory");
  user_pc = (user_pc & 0xffffffffULL) - DRAM_BASE + SOURCE_ALIAS;
  __asm__ volatile("csrw mtvec, %0" : : "r"((uint64_t)trap_entry) : "memory");
  __asm__ volatile("csrw mscratch, %0" : : "r"(SOURCE_CSR) : "memory");
  __asm__ volatile("csrw mepc, %0" : : "r"(user_pc) : "memory");
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  status &= ~((3ULL << 11) | (1ULL << 17));
  __asm__ volatile("csrw mstatus, %0\nmv gp, %1\nmret"
                   : : "r"(status), "r"(peer_gp) : "gp", "memory");
  __builtin_unreachable();
}
