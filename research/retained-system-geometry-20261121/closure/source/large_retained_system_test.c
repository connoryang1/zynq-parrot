/* Bare-metal control test for experimental full-line I/D retention.
 * This is a new ELF/dataset; passing it proves global control, checked execution and privilege,
 * not useful capacity, whole-workload acceleration, or FPGA acceptance.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"
#ifndef BP_EXPECT_I_LINES
#define BP_EXPECT_I_LINES 64
#endif
#ifndef BP_EXPECT_D_LINES
#define BP_EXPECT_D_LINES 64
#endif
#ifndef BP_EXPECT_RETAINED_SETS
#define BP_EXPECT_RETAINED_SETS 64
#endif
#if BP_EXPECT_RETAINED_SETS < 1 || (BP_EXPECT_RETAINED_SETS & (BP_EXPECT_RETAINED_SETS-1))
#error "BP_EXPECT_RETAINED_SETS must be a positive power of two"
#endif

static uint64_t stacks[2][512];
// Ten lines share one ordinary 8-way L1 set. This short integration fixture
// exercises real replacement without a large application loop. Full retained
// payload counts are established separately by exhaustive component gates.
// Put the sparse array in data so CRT BSS clearing does not dominate this gate.
static volatile uint64_t corpus[10][512] __attribute__((aligned(4096))) = {{1}};
static uint64_t expected(unsigned line, unsigned word) {
  return (UINT64_C(0x93bd82917) * (line+1)) ^ (UINT64_C(0xc8f72015) * (word+3));
}
static void checked_payload(void) {
  // Real dirty writebacks, ordinary fills and accepted store invalidations.
  // All words are checked, including addresses sharing a retained-buffer set.
  for (unsigned i=0;i<10;++i)
    for (unsigned w=0;w<8;++w) corpus[i][w]=expected(i,w);
  for (unsigned pass=0;pass<2;++pass)
    for (unsigned i=0;i<10;++i)
      for (unsigned w=0;w<8;++w)
        if (corpus[i][w]!=expected(i,w)) { bp_finish(1); for(;;); }
  for (unsigned i=0;i<10;i+=7) corpus[i][3]^=UINT64_C(0x5af8721d);
  for (unsigned i=0;i<10;++i)
    for (unsigned w=0;w<8;++w) {
      uint64_t want=expected(i,w);
      if (i%7==0 && w==3) want^=UINT64_C(0x5af8721d);
      if (corpus[i][w]!=want) { bp_finish(1); for(;;); }
    }
}
static volatile uint64_t failure, phase, illegal_reads, illegal_writes;
static volatile uint64_t context1_status, context3_status, supervisor_status;
static inline uint64_t policy_status(void) {
  uint64_t v; __asm__ volatile("csrr %0, 0x5c2":"=r"(v)); return v;
}
static inline void policy(unsigned m) {
  __asm__ volatile("csrw 0x5c2, %0"::"r"((uint64_t)m):"memory");
}
static inline void handoff(unsigned c) {
  __asm__ volatile("csrw 0x800, %0"::"r"((uint64_t)c):"memory");
}
static void __attribute__((noinline,noreturn)) fail(void) {
  bp_print_string("[BSG-FAIL] full-line I/D retention control phase/status: ");
  bp_hprint_uint64(phase); bp_hprint_uint64(policy_status());
  bp_print_string("\n"); bp_finish(1); for(;;);
}
static void __attribute__((noinline,used)) context1(void) {
  context1_status=policy_status(); policy(9); handoff(0); fail();
}
static void __attribute__((noinline,used)) context3(void) {
  context3_status=policy_status(); policy(6); handoff(0); fail();
}
static void __attribute__((naked,aligned(4),used)) trap(void) {
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "csrr t0, mcause\nli t1, 2\nbne t0, t1, 3f\n"
    "csrr t0, mepc\nla t1, user_policy_read\nbne t0, t1, 1f\n"
    "la t0, illegal_reads\nli t1, 1\nsd t1, 0(t0)\nj 2f\n"
    "1: la t1, user_policy_write\nbne t0, t1, 8f\n"
    "la t0, illegal_writes\nli t1, 1\nsd t1, 0(t0)\n"
    "2: csrr t0, mepc\naddi t0, t0, 4\ncsrw mepc, t0\nmret\n"
    "3: li t1, 9\nbeq t0, t1, 4f\nli t1, 8\nbne t0, t1, 8f\n"
    "4: csrr t0, mepc\naddi t0, t0, 4\ncsrw mepc, t0\n"
    "csrr t0, mstatus\nli t1, 0x1800\nor t0, t0, t1\ncsrw mstatus, t0\nmret\n"
    "8: la t0, failure\nli t1, 1\nsd t1, 0(t0)\nj fail\n"
    ".option pop\n");
}
static void __attribute__((naked,noinline,used)) supervisor(void) {
  __asm__ volatile(
    "li t0, 15\ncsrw 0x5c2, t0\ncsrr t0, 0x5c2\n"
    "la t1, supervisor_status\nsd t0, 0(t1)\nfence.i\necall\nret\n");
}
static void __attribute__((naked,noinline,used)) user(void) {
  __asm__ volatile(
    ".option push\n.option norvc\n"
    ".global user_policy_read\nuser_policy_read: csrr t3, 0x5c2\n"
    "li t3, 2\n.global user_policy_write\nuser_policy_write: csrw 0x5c2, t3\n"
    "ecall\nret\n.option pop\n");
}
static void __attribute__((naked,noinline)) enter(uint64_t pc,uint64_t privilege) {
  __asm__ volatile(
    "csrw mepc, a0\ncsrr t0, mstatus\nli t1, 0x1800\n"
    "not t1, t1\nand t0, t0, t1\nslli a1, a1, 11\n"
    "or t0, t0, a1\ncsrw mstatus, t0\nmret\n");
}
int main(void) {
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile("csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:":::"t0","memory");
#endif
  phase=1;
  if((policy_status() & (UINT64_C(1)<<63))==0 || (policy_status()&15)!=0) fail();
  policy(15); if((policy_status()&15)!=15) fail();
  uint64_t gp; __asm__ volatile("mv %0, gp":"=r"(gp));
  seed_reg(1,3,gp);seed_reg(1,2,(uint64_t)&stacks[0][512]);seed_npc(1,(uint64_t)context1);
  phase=2;handoff(1);
  if((context1_status&15)!=15 || (policy_status()&15)!=9) fail();
  seed_reg(3,3,gp);seed_reg(3,2,(uint64_t)&stacks[1][512]);seed_npc(3,(uint64_t)context3);
  phase=3;handoff(3);
  if((context3_status&15)!=9 || (policy_status()&15)!=6) fail();
  __asm__ volatile("csrw medeleg, zero\ncsrw mideleg, zero\ncsrw mtvec, %0"::"r"((uint64_t)trap):"memory");
  phase=4;enter((uint64_t)supervisor,1);
  if(failure || (supervisor_status&15)!=15 || (policy_status()&15)!=15) fail();
  phase=5;enter((uint64_t)user,0);
  if(failure || illegal_reads!=1 || illegal_writes!=1 || (policy_status()&15)!=15) fail();
  phase=6;
  if (((policy_status()>>16)&0xffff)!=BP_EXPECT_I_LINES
      || ((policy_status()>>32)&0xffff)!=BP_EXPECT_D_LINES
      || ((policy_status()>>48)&0xff)!=(unsigned)__builtin_ctz((unsigned)BP_EXPECT_RETAINED_SETS)
      || ((policy_status()>>56)&3)!=3) fail();
  // Same data integrity task under disabled, I-only, D-only and joint control.
  for (unsigned mode=0; mode<4; ++mode) {
    static const unsigned controls[4]={0,9,6,15};
    policy(controls[mode]); checked_payload();
  }
  phase=7;policy(0);__asm__ volatile("fence.i":::"memory");
  if((policy_status()&15)!=0) fail();
  bp_print_string("[BSG-PASS] full-line I/D retention checked payload global contexts S/M control and U denial\n");
  bp_finish(0);for(;;);
}
