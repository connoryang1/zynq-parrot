#include <stdint.h>
#include "bp_utils.h"

/* Seventeen page-spaced lines at a common page offset map to one L1D set.
 * The naked probe repeats the experiment at all 64 offsets: dirty one full
 * target line, touch sixteen conflicting lines, then reload and verify the
 * target.  Sixteen conflicts make the test independent of the initial set
 * contents and conservative with respect to the eight-way pseudo-LRU policy.
 *
 * The conflicting values are irrelevant, so BSS storage is intentional. */
static volatile uint64_t pages[17][512]
  __attribute__((aligned(4096), used));

static volatile uint64_t set62_word_mask;
static volatile uint64_t slow_reload_mask;

/* Return one bit per set whose target line did not survive dirty eviction.
 * set62_word_mask separately identifies corrupt words in the set implicated
 * by the ten-context physical failure.  No stack or C data access occurs in
 * the measured region. */
static uint64_t __attribute__((naked, noinline, aligned(64))) exercise(void)
{
  __asm__ volatile(
    "la t6, pages\n"
    "li a0, 0\n"                  /* failing-set mask */
    "li a1, 0\n"                  /* set-62 failing-word mask */
    "li a2, 0\n"                  /* set number */
    "li a3, 1\n"                  /* current set bit */
    "li t5, 0\n"                  /* reloads taking more than ten cycles */
    "1:\n"
    "mv a4, t6\n"                 /* target line */
    "li a7, 0x5a000000\n"
    "slli t0, a2, 8\n"
    "add a7, a7, t0\n"            /* set-specific expected base */
    "mv t0, a4\n"
    "mv t1, a7\n"
    "li t2, 8\n"
    "2: sd t1, 0(t0)\n"
    "addi t0, t0, 8\n"
    "addi t1, t1, 1\n"
    "addi t2, t2, -1\n"
    "bnez t2, 2b\n"
    "fence rw, rw\n"

    /* All addresses below share the target's set and have distinct tags. */
    "li t0, 4096\n"
    "add a5, a4, t0\n"
    "li a6, 16\n"
    "3: ld t1, 0(a5)\n"
    "add a5, a5, t0\n"
    "addi a6, a6, -1\n"
    "bnez a6, 3b\n"
    "fence rw, rw\n"

    /* A target that was actually displaced takes far longer than an L1 hit.
     * Keep this independent check so a passing data comparison cannot be
     * mistaken for proof that the writeback/refill path was exercised. */
    "rdcycle a5\n"
    "ld t3, 0(a4)\n"
    "xor a6, t3, t3\n"            /* serialize the ending timestamp */
    "add a5, a5, a6\n"
    "rdcycle a6\n"
    "sub a6, a6, a5\n"
    "li t0, 10\n"
    "bltu a6, t0, 6f\n"
    "or t5, t5, a3\n"
    "6:\n"

    "mv t0, a4\n"
    "mv t1, a7\n"
    "li t2, 8\n"
    "li t4, 1\n"
    "4: ld t3, 0(t0)\n"
    "beq t3, t1, 5f\n"
    "or a0, a0, a3\n"
    "li a6, 62\n"
    "bne a2, a6, 5f\n"
    "or a1, a1, t4\n"
    "5: addi t0, t0, 8\n"
    "addi t1, t1, 1\n"
    "slli t4, t4, 1\n"
    "addi t2, t2, -1\n"
    "bnez t2, 4b\n"

    "addi t6, t6, 64\n"           /* next set in every page */
    "addi a2, a2, 1\n"
    "slli a3, a3, 1\n"
    "li t0, 64\n"
    "bne a2, t0, 1b\n"
    "fence rw, rw\n"
    "la t0, set62_word_mask\n"
    "sd a1, 0(t0)\n"
    "la t0, slow_reload_mask\n"
    "sd t5, 0(t0)\n"
    "ret\n");
}

int main(void)
{
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile("csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:" : : : "t0", "memory");
#endif

  bp_print_string("DIRTY-EVICTION begin\n");
  uint64_t set_mask = exercise();
  bp_print_string("DIRTY-EVICTION set_mask=");
  bp_hprint_uint64(set_mask);
  bp_print_string(" set62_word_mask=");
  bp_hprint_uint64(set62_word_mask);
  bp_print_string(" slow_reload_mask=");
  bp_hprint_uint64(slow_reload_mask);
  bp_print_string("\n");

  if (set_mask || set62_word_mask || slow_reload_mask != UINT64_MAX) {
    bp_print_string("[BSG-FAIL] dirty eviction integrity\n");
    bp_finish(1);
  }
  bp_print_string("[BSG-PASS] dirty eviction integrity\n");
  bp_finish(0);
}
