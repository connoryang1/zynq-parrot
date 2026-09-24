#include <stdint.h>
#include "bp_utils.h"
#include "bp_prefetch.h"

volatile uint64_t protocol_case __attribute__((section(".data"))) = 1;
static volatile uint64_t pages[12][512] __attribute__((aligned(4096),used)) = {
 [0][128]=1,[1][128]=2,[2][128]=3,[3][128]=4,[4][128]=5,[5][128]=6,
 [6][128]=7,[7][128]=8,[8][128]=9,[9][128]=10,[10][128]=11,[11][136]=0xbb
};

/* Eight clean lines fill every way of set 16. No stack/data traffic besides
 * these target loads occurs in the naked leaf functions. */
#define PRIME_CLEAN \
 "la a1, pages\naddi a1, a1, 1024\nmv a2, a1\nli a3, 8\nli a5, 4096\n" \
 "1: ld t0, 0(a2)\nadd a2, a2, a5\naddi a3, a3, -1\nbnez a3, 1b\n" \
 "fence rw, rw\n"

/* Recheck all original first words against their index-derived value.
 * The caller sets a3=count, a4=expected base, a0=existing failure mask. */
#define VERIFY_FIRST_WORDS \
 "mv a2, a1\nli a6, 1\n" \
 "4: ld t0, 0(a2)\nbeq t0, a4, 5f\nor a0, a0, a6\n5:\n" \
 "add a2, a2, a5\naddi a4, a4, 1\nslli a6, a6, 1\n" \
 "addi a3, a3, -1\nbnez a3, 4b\nfence rw, rw\nret\n"

/* A hint observes a clean victim, then stores dirty every possible victim
 * before the delayed response. All eight stored values must survive. */
static uint64_t __attribute__((naked,noinline,aligned(64))) clean_then_dirty(void)
{
 __asm__ volatile(PRIME_CLEAN
  ".global clean_then_dirty_hint\nclean_then_dirty_hint:\n"
  BP_PREFETCH_R_ASM("a2")
  "mv a7, a2\nmv a2, a1\nli a3, 8\nli a4, 0x5a01\n"
  ".global clean_then_dirty_store\nclean_then_dirty_store:\n"
  "2: sd a4, 0(a2)\nadd a2, a2, a5\naddi a4, a4, 1\n"
  "addi a3, a3, -1\nbnez a3, 2b\nfence rw, rw\n"
  "ld t0, 0(a7)\nli t1, 9\nli a0, 0\nbeq t0, t1, 3f\n"
  "ori a0, a0, 256\n3: li a3, 8\nli a4, 0x5a01\n"
  VERIFY_FIRST_WORDS);
}

/* Two detached reads target the same full cache set, immediately followed
 * by a conflicting ordinary miss. Every first word must remain coherent,
 * whether hints install, are dropped, or evict another clean line. */
static uint64_t __attribute__((naked,noinline,aligned(64))) same_set_conflict(void)
{
 __asm__ volatile(PRIME_CLEAN
  ".global same_set_first_hint\nsame_set_first_hint:\n"
  BP_PREFETCH_R_ASM("a2")
  "add a2, a2, a5\n"
  ".global same_set_second_hint\nsame_set_second_hint:\n"
  BP_PREFETCH_R_ASM("a2")
  "add a2, a2, a5\n"
  ".global same_set_ordinary_load\nsame_set_ordinary_load:\n"
  "ld t0, 0(a2)\nli t1, 11\nli a0, 0\nbeq t0, t1, 3f\n"
  "ori a0, a0, 2047\n3: fence rw, rw\nli a3, 11\nli a4, 1\n"
  VERIFY_FIRST_WORDS);
}

/* Let a detached request enter the memory pipeline before an independent
 * ordinary miss. A response ahead of the ordinary response must drain even
 * when the ordinary request owns the demand FSM; neither load may hang. */
static uint64_t __attribute__((naked,noinline,aligned(64))) response_before_demand(void)
{
 __asm__ volatile(
  "la a1, pages\nli a5, 32768\nadd a1, a1, a5\naddi a1, a1, 1024\n"
  "li a5, 12352\nadd a2, a1, a5\n"
  ".global response_first_hint\nresponse_first_hint:\n"
  BP_PREFETCH_R_ASM("a1")
  ".rept 8\nnop\n.endr\n"
  ".global response_later_demand\nresponse_later_demand:\n"
  "ld t0, 0(a2)\nli t1, 0xbb\nli a0, 0\nbeq t0, t1, 1f\n"
  "ori a0, a0, 1\n1: fence rw, rw\nld t0, 0(a1)\nli t1, 9\n"
  "beq t0, t1, 2f\nori a0, a0, 2\n2: fence rw, rw\nret\n");
}

int main(void)
{
#ifndef BP_FPGA_PROGRAM
 __asm__ volatile("csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
  "la t0, 1f\ncsrw dpc, t0\ndret\n1:" : : : "t0", "memory");
#endif
 uint64_t which=protocol_case;
 bp_print_string("PREFETCH-PROTOCOL case=");bp_hprint_uint64(which);
 bp_print_string(" begin\n");
 uint64_t mask=which==1?clean_then_dirty():which==2?same_set_conflict():
   which==3?response_before_demand():UINT64_MAX;
 bp_print_string("PREFETCH-PROTOCOL mismatch_mask=");bp_hprint_uint64(mask);
 bp_print_string("\n");
 if(mask){bp_print_string("[BSG-FAIL] detached prefetch protocol\n");bp_finish(1);}
 bp_print_string("[BSG-PASS] detached prefetch protocol\n");bp_finish(0);
}
