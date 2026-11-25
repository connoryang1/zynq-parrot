/* Foreground/background retained-line microbenchmark with code AND data
 * footprints (bare metal, M mode): off vs gated D-only, I-only and joint.
 *
 * Each foreground round executes FG_CODE_KIB of straight-line, non-compressed
 * code and scans FG_KIB of data; each background round executes BG_CODE_KIB
 * of code and scans BG_KIB of data, evicting the foreground's instruction and
 * data lines from L1 and L2. Gated policies enable lookups for the selected
 * lanes throughout and turn demand capture on only during the foreground, so
 * the store keeps the foreground's lines while the background runs.
 *   off   : 0x5c2 = 0
 *   d     : enable 2, capture +4
 *   i     : enable 1, capture +8
 *   joint : enable 3, capture +12
 *   warm  : reference lower bound (see main)
 * Code results and data sums are checked every round.
 */
#include <stdint.h>
#include "bp_utils.h"

#ifndef FG_KIB
#define FG_KIB 12
#endif
#ifndef BG_KIB
#define BG_KIB 64
#endif
#ifndef FG_CODE_KIB
#define FG_CODE_KIB 12
#endif
#ifndef BG_CODE_KIB
#define BG_CODE_KIB 48
#endif
#ifndef ROUNDS
#define ROUNDS 6
#endif
#ifndef WARMUP
#define WARMUP 2
#endif

#define STR_(x) #x
#define STR(x) STR_(x)
#define FG_WORDS (FG_KIB * 128)
#define BG_WORDS (BG_KIB * 128)
#define FG_INSNS (FG_CODE_KIB * 256)
#define BG_INSNS (BG_CODE_KIB * 256)

static volatile uint64_t fg[FG_WORDS] __attribute__((aligned(4096)));
static volatile uint64_t bg[BG_WORDS] __attribute__((aligned(4096)));

/* Straight-line 4-byte instructions: every 64-byte line holds 16 of them. */
static uint64_t __attribute__((noinline, aligned(64))) fg_code(uint64_t x) {
  __asm__ volatile(".option push\n.option norvc\n.rept " STR(FG_INSNS)
                   "\naddi %0, %0, 1\n.endr\n.option pop" : "+r"(x));
  return x;
}
static uint64_t __attribute__((noinline, aligned(64))) bg_code(uint64_t x) {
  __asm__ volatile(".option push\n.option norvc\n.rept " STR(BG_INSNS)
                   "\naddi %0, %0, 3\n.endr\n.option pop" : "+r"(x));
  return x;
}

static inline uint64_t cycles(void) {
  uint64_t v; __asm__ volatile("csrr %0, 0xcc0" : "=r"(v) : : "memory"); return v;
}
static inline void policy(uint64_t m) {
  __asm__ volatile("csrw 0x5c2, %0" : : "r"(m) : "memory");
}
static inline uint64_t policy_status(void) {
  uint64_t v; __asm__ volatile("csrr %0, 0x5c2" : "=r"(v) : : "memory"); return v;
}
static void wait_idle(void) {
  for (unsigned n = 0; n < 100000; ++n)
    if (!(policy_status() & 0x300)) return;
  bp_print_string("[BSG-FAIL] retained idle timeout\n"); bp_finish(1);
}
static uint64_t scan(volatile uint64_t *a, unsigned words) {
  uint64_t s = 0;
  for (unsigned i = 0; i < words; i += 8)
    s += a[i] + a[i+1] + a[i+2] + a[i+3] + a[i+4] + a[i+5] + a[i+6] + a[i+7];
  return s;
}
static void print_kv(char *k, uint64_t v) {
  bp_print_string(k); bp_hprint_uint64(v); bp_print_string(" ");
}

int main(void) {
  uint64_t fg_sum = 0, bg_sum = 0;
  for (unsigned i = 0; i < FG_WORDS; ++i) { fg[i] = i * 0x9e3779b97f4a7c15ULL; fg_sum += fg[i]; }
  for (unsigned i = 0; i < BG_WORDS; ++i) { bg[i] = i ^ 0xc8f72015ULL; bg_sum += bg[i]; }
  if (!(policy_status() >> 63)) { bp_print_string("[BSG-FAIL] no retained store\n"); bp_finish(1); }
  /* "warm" is a reference, not a policy: retention off and the foreground is
   * re-run immediately before its timed run, so it measures the fully warm
   * L1/L2 lower bound that any retention scheme can approach. */
  static const char *names[5] = {"off", "d", "i", "joint", "warm"};
  static const uint64_t enable[5] = {0, 2, 1, 3, 0}, capture[5] = {0, 4, 8, 12, 0};
#ifndef MODES_MASK
#define MODES_MASK 0x1f
#endif
  for (unsigned mode = 0; mode < 5; ++mode) {
    if (!((MODES_MASK >> mode) & 1)) continue;
    policy(0); wait_idle();                      /* enable change: empty store */
    policy(enable[mode]); wait_idle();
    uint64_t fgc = 0, bgc = 0;
    for (unsigned r = 0; r < ROUNDS; ++r) {
      policy(enable[mode] | capture[mode]);      /* foreground: capture on */
      if (mode == 4) { (void)fg_code(r); (void)scan(fg, FG_WORDS); }
      uint64_t t0 = cycles();
      uint64_t c = fg_code(r);
      uint64_t s = scan(fg, FG_WORDS);
      uint64_t t1 = cycles();
      policy(enable[mode]);                      /* background: capture off */
      uint64_t t2 = cycles();
      uint64_t bc = bg_code(r);
      uint64_t b = scan(bg, BG_WORDS);
      uint64_t t3 = cycles();
      if (s != fg_sum || b != bg_sum || c != r + FG_INSNS || bc != r + 3ULL * BG_INSNS) {
        bp_print_string("[BSG-FAIL] check mode/round "); bp_hprint_uint64(mode);
        bp_hprint_uint64(r); bp_print_string("\n"); bp_finish(1);
      }
      if (r >= WARMUP) { fgc += t1 - t0; bgc += t3 - t2; }
    }
    bp_print_string("FGBG mode="); bp_print_string((char *)names[mode]); bp_print_string(" ");
    print_kv("fg_cycles=", fgc); print_kv("bg_cycles=", bgc);
    print_kv("rounds=", ROUNDS - WARMUP); print_kv("fg_kib=", FG_KIB); print_kv("bg_kib=", BG_KIB);
    print_kv("fg_code_kib=", FG_CODE_KIB); print_kv("bg_code_kib=", BG_CODE_KIB);
    bp_print_string("\n");
  }
  policy(0); wait_idle();
  bp_print_string("[BSG-PASS] retained fg/bg I/D/joint benchmark\n");
  bp_finish(0);
}
