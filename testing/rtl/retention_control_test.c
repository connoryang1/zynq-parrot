/* Bare-metal control test for experimental global instruction retention.
 * This is a new ELF/dataset; passing it proves policy routing and privilege,
 * not useful capacity, whole-workload acceleration, or FPGA acceptance.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

static uint64_t stacks[2][512];
static volatile uint64_t failure, phase, illegal_reads, illegal_writes;
static volatile uint64_t context1_status, context3_status, supervisor_status;
static inline uint64_t policy_status(void) {
  uint64_t v; __asm__ volatile("csrr %0, 0x5c1":"=r"(v)); return v;
}
static inline void policy(unsigned m) {
  __asm__ volatile("csrw 0x5c1, %0"::"r"((uint64_t)m):"memory");
}
static inline void handoff(unsigned c) {
  __asm__ volatile("csrw 0x800, %0"::"r"((uint64_t)c):"memory");
}
static void __attribute__((noinline,noreturn)) fail(void) {
  bp_print_string("[BSG-FAIL] runtime instruction retention control phase/status: ");
  bp_hprint_uint64(phase); bp_hprint_uint64(policy_status());
  bp_print_string("\n"); bp_finish(1); for(;;);
}
static void __attribute__((noinline,used)) context1(void) {
  context1_status=policy_status(); policy(1); handoff(0); fail();
}
static void __attribute__((noinline,used)) context3(void) {
  context3_status=policy_status(); policy(2); handoff(0); fail();
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
    "li t0, 1\ncsrw 0x5c1, t0\ncsrr t0, 0x5c1\n"
    "la t1, supervisor_status\nsd t0, 0(t1)\nfence.i\necall\nret\n");
}
static void __attribute__((naked,noinline,used)) user(void) {
  __asm__ volatile(
    ".option push\n.option norvc\n"
    ".global user_policy_read\nuser_policy_read: csrr t3, 0x5c1\n"
    "li t3, 2\n.global user_policy_write\nuser_policy_write: csrw 0x5c1, t3\n"
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
  if((policy_status() & (UINT64_C(1)<<63))==0 || (policy_status()&3)!=0) fail();
  policy(2); if((policy_status()&3)!=2) fail();
  uint64_t gp; __asm__ volatile("mv %0, gp":"=r"(gp));
  seed_reg(1,3,gp);seed_reg(1,2,(uint64_t)&stacks[0][512]);seed_npc(1,(uint64_t)context1);
  phase=2;handoff(1);
  if((context1_status&3)!=2 || (policy_status()&3)!=1) fail();
  seed_reg(3,3,gp);seed_reg(3,2,(uint64_t)&stacks[1][512]);seed_npc(3,(uint64_t)context3);
  phase=3;handoff(3);
  if((context3_status&3)!=1 || (policy_status()&3)!=2) fail();
  __asm__ volatile("csrw medeleg, zero\ncsrw mideleg, zero\ncsrw mtvec, %0"::"r"((uint64_t)trap):"memory");
  phase=4;enter((uint64_t)supervisor,1);
  if(failure || (supervisor_status&3)!=1 || (policy_status()&3)!=1) fail();
  phase=5;enter((uint64_t)user,0);
  if(failure || illegal_reads!=1 || illegal_writes!=1 || (policy_status()&3)!=1) fail();
  phase=6;policy(0);__asm__ volatile("fence.i":::"memory");
  if((policy_status()&3)!=0) fail();
  bp_print_string("[BSG-PASS] runtime instruction retention global contexts S/M policy and U denial\n");
  bp_finish(0);for(;;);
}
