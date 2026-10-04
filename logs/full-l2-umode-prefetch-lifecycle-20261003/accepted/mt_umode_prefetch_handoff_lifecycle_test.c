/* Repeat prefetch/switch/load launches in U-mode with 4 KiB Sv39 data leaves.
 * A 16-page sweep precedes each launch, applying cache and DTLB pressure before
 * two resident contexts traverse four private request pages apiece.
 */
#include <stdint.h>
#include "bp_prefetch.h"
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 10
#error "Translated lifecycle test requires two resident and ten logical contexts"
#endif

#define DRAM_BASE UINT64_C(0x80000000)
#define SOURCE_VA UINT64_C(0x40000000)
#define PEER_VA UINT64_C(0x40004000)
#define EVICTION_VA UINT64_C(0x40008000)
#define EPOCHS 6
#define LINES 256
#define LINE_BYTES 64
#define EVICTION_LINES 1024
#define PEER_DONE UINT64_C(0x50415353)
#define EXPECTED_SUM UINT64_C(32640)

static volatile unsigned char source_data[LINES * LINE_BYTES]
  __attribute__((aligned(4096), used));
static volatile unsigned char peer_data[LINES * LINE_BYTES]
  __attribute__((aligned(4096), used));
static volatile unsigned char eviction[EVICTION_LINES * LINE_BYTES]
  __attribute__((aligned(4096), used));
static uint64_t root[512] __attribute__((aligned(4096)));
static uint64_t middle[512] __attribute__((aligned(4096)));
static uint64_t leaves[512] __attribute__((aligned(4096)));
static volatile uint64_t expected_address[2] __attribute__((aligned(64), used));
static volatile uint64_t observed_address[2] __attribute__((aligned(64), used));
static volatile uint64_t mismatch_iteration[2] __attribute__((aligned(64), used));
static volatile uint64_t result_sum[2] __attribute__((aligned(64), used));
static volatile uint64_t peer_done, eviction_sink, completed_epochs;
static volatile uint64_t unexpected_cause, unexpected_pc, unexpected_value;

#define WORKER_BODY(id, target, base, after_return, mismatch, done) \
  ".option push\n.option norvc\nli a0, " base "\nli a2, 256\nli t5, 0\n" \
  "la a4, expected_address\nla a5, observed_address\n" \
  "la a6, mismatch_iteration\naddi a4, a4, " #id "*8\n" \
  "addi a5, a5, " #id "*8\naddi a6, a6, " #id "*8\n" \
  "1: addi t3, a2, -1\nslli t0, t3, 6\nadd t0, a0, t0\n" \
  "sd t0, 0(a4)\n" BP_PREFETCH_R_ASM("t0") \
  "csrw 0x800, " #target "\n" after_return \
  "ld t1, 0(a4)\nbeq t0, t1, 2f\nsd t0, 0(a5)\nsd a2, 0(a6)\n" \
  mismatch \
  "2: ld t2, 0(t0)\nadd t5, t5, t2\naddi a2, a2, -1\n" \
  "bnez a2, 1b\nla t0, result_sum\nsd t5, " #id "*8(t0)\n" done \
  ".option pop\n"

static __attribute__((naked, noinline, noreturn, used, aligned(4096)))
void peer(void)
{
  __asm__ volatile(WORKER_BODY(1, 0, "0x40004000", "",
    "fence rw,rw\ncsrwi 0x800, 0\n3: j 3b\n",
    "la t0, peer_done\nli t1, 0x50415353\nsd t1, 0(t0)\n"
    "fence rw,rw\ncsrwi 0x800, 0\n3: j 3b\n"));
}

static __attribute__((naked, noinline, used, aligned(4096)))
void source(void)
{
  __asm__ volatile(WORKER_BODY(0, 1, "0x40000000",
    "la t4, mismatch_iteration\nld t4, 8(t4)\nbnez t4, 8f\n",
    "ret\n", "8: ret\n"));
}

static void __attribute__((used, noinline, noreturn)) machine_finish(void)
{
  if (!unexpected_cause && completed_epochs == EPOCHS
      && peer_done == PEER_DONE && !mismatch_iteration[0]
      && !mismatch_iteration[1] && result_sum[0] == EXPECTED_SUM
      && result_sum[1] == EXPECTED_SUM) {
    bp_print_string("[BSG-PASS] translated repeated prefetch handoff lifecycle\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] translated repeated prefetch handoff lifecycle\n");
    bp_print_string("epochs/done/mismatch/sums/cause/pc/tval: ");
    bp_hprint_uint64(completed_epochs);
    bp_hprint_uint64(peer_done);
    bp_hprint_uint64(mismatch_iteration[0]);
    bp_hprint_uint64(mismatch_iteration[1]);
    bp_hprint_uint64(result_sum[0]);
    bp_hprint_uint64(result_sum[1]);
    bp_hprint_uint64(unexpected_cause);
    bp_hprint_uint64(unexpected_pc);
    bp_hprint_uint64(unexpected_value);
    bp_print_string("\n");
    bp_finish(1);
  }
  for (;;) ;
}

static void __attribute__((naked, aligned(4))) trap_entry(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "csrr t0, mcause\nli t1, 8\nbne t0, t1, 4f\n"
    "li t1, 1\nbeq a0, t1, 2f\nli t1, 3\nbeq a0, t1, 3f\nj 4f\n"
    "2: csrr t0, mepc\naddi t0, t0, 4\ncsrw mepc, t0\nmret\n"
    "3: csrr t0, mstatus\nli t1, 0x1800\nor t0, t0, t1\n"
    "csrw mstatus, t0\nla t0, machine_finish\ncsrw mepc, t0\nmret\n"
    "4: la t1, unexpected_cause\nsd t0, 0(t1)\n"
    "csrr t0, mepc\nla t1, unexpected_pc\nsd t0, 0(t1)\n"
    "csrr t0, mtval\nla t1, unexpected_value\nsd t0, 0(t1)\n"
    "j 3b\n.option pop\n");
}

static void __attribute__((noinline, noreturn, aligned(4096))) user_entry(void)
{
  uint64_t gp_value;
  volatile uint64_t peer_pc = (uint64_t)peer;
  __asm__ volatile("mv %0, gp" : "=r"(gp_value));
  seed_reg(1, 3, gp_value);

  /* Prove source U-mode entry before context 1 inherits translated state. */
  register uint64_t init_a0 __asm__("a0") = 1;
  __asm__ volatile("ecall" : "+r"(init_a0) : : "t0", "t1", "memory");

  volatile unsigned char *evict = (volatile unsigned char *)EVICTION_VA;
  for (unsigned epoch = 0; epoch < EPOCHS; ++epoch) {
    uint64_t displaced = 0;
    for (unsigned i = 0; i < EVICTION_LINES; ++i)
      displaced += evict[i * LINE_BYTES];
    eviction_sink = displaced;
    __asm__ volatile("fence rw, rw" : : : "memory");

    peer_done = 0;
    expected_address[0] = expected_address[1] = 0;
    observed_address[0] = observed_address[1] = 0;
    mismatch_iteration[0] = mismatch_iteration[1] = 0;
    result_sum[0] = result_sum[1] = 0;
    seed_npc(1, peer_pc);
    source();
    if (!mismatch_iteration[0] && !mismatch_iteration[1])
      __asm__ volatile("csrwi 0x800, 1" : : : "memory");
    if (peer_done != PEER_DONE || mismatch_iteration[0]
        || mismatch_iteration[1] || result_sum[0] != EXPECTED_SUM
        || result_sum[1] != EXPECTED_SUM)
      break;
    completed_epochs = epoch + 1;
  }

  register uint64_t finish_a0 __asm__("a0") = 3;
  __asm__ volatile("ecall" : "+r"(finish_a0) : : "t0", "t1", "memory");
  for (;;) ;
}

static uint64_t leaf_for(const volatile void *address)
{
  return ((((uint64_t)address & UINT64_C(0xffffffff)) >> 12) << 10)
    | PTE_V | PTE_R | PTE_U | PTE_A;
}

int main(void)
{
  bp_print_string("[BSG-INFO] translated repeated prefetch handoff setup\n");
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile(
    "csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:"
    : : : "t0", "memory");
#endif
  for (unsigned i = 0; i < LINES; ++i) {
    source_data[i * LINE_BYTES] = (unsigned char)(i + 1);
    peer_data[i * LINE_BYTES] = (unsigned char)(i + 2);
  }
  const uint64_t broad = PTE_V | PTE_R | PTE_W | PTE_X
    | PTE_U | PTE_A | PTE_D;
  root[0] = ((DRAM_BASE >> 12) << 10) | broad;
  root[2] = root[0];
  root[1] = ((((uint64_t)middle & UINT64_C(0xffffffff)) >> 12) << 10) | PTE_V;
  middle[0] = ((((uint64_t)leaves & UINT64_C(0xffffffff)) >> 12) << 10) | PTE_V;
  for (unsigned page = 0; page < 4; ++page) {
    leaves[page] = leaf_for(source_data + page * 4096);
    leaves[4 + page] = leaf_for(peer_data + page * 4096);
  }
  for (unsigned page = 0; page < 16; ++page)
    leaves[8 + page] = leaf_for(eviction + page * 4096);

  __asm__ volatile("csrw medeleg, zero\ncsrw mideleg, zero" : : : "memory");
  const uint64_t satp = (8ULL << 60)
    | (((uint64_t)root & UINT64_C(0xffffffff)) >> 12);
  __asm__ volatile("fence rw, rw\ncsrw satp, %0\nsfence.vma"
    : : "r"(satp) : "memory");
  volatile uint64_t user_pc = (uint64_t)user_entry;
  user_pc = (user_pc & UINT64_C(0xffffffff)) - DRAM_BASE;
  __asm__ volatile("csrw mtvec, %0" : : "r"((uint64_t)trap_entry) : "memory");
  __asm__ volatile("csrw mepc, %0" : : "r"(user_pc) : "memory");
  uint64_t status;
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  status &= ~(3ULL << 11);
  __asm__ volatile("csrw mstatus, %0\nmret" : : "r"(status) : "memory");
  __builtin_unreachable();
}
