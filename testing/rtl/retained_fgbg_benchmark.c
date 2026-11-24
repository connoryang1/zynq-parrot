/* Foreground/background retained-line microbenchmark (bare metal, M mode).
 *
 * A latency-critical foreground scans a small working set; a background task
 * then scans a large polluting set that evicts the foreground from L1 and L2.
 * Three D-side policies run back to back on one model:
 *   off     : CSR 0x5c2 = 0 throughout;
 *   always  : enable + demand capture (6) throughout (the prior ordinary-d);
 *   gated   : enable + capture (6) only during the foreground, enable-only
 *             (2) during the background, which preserves the store because
 *             the lane enable does not change.
 * Reported cycles are per measured round (sum over ROUNDS-WARMUP rounds).
 * Every foreground/background word is checked through a running checksum.
 */
#include <stdint.h>
#include "bp_utils.h"

#ifndef FG_KIB
#define FG_KIB 12
#endif
#ifndef BG_KIB
#define BG_KIB 64
#endif
#ifndef ROUNDS
#define ROUNDS 6
#endif
#ifndef WARMUP
#define WARMUP 2
#endif
#ifndef FG_STORES
#define FG_STORES 0
#endif

#define FG_WORDS (FG_KIB * 128)
#define BG_WORDS (BG_KIB * 128)

static volatile uint64_t fg[FG_WORDS] __attribute__((aligned(4096)));
static volatile uint64_t bg[BG_WORDS] __attribute__((aligned(4096)));
static volatile uint64_t sink;

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
  static const char *names[3] = {"off", "always", "gated"};
  for (unsigned mode = 0; mode < 3; ++mode) {
    /* Changing an enable clears the store: start every mode empty. */
    policy(0); wait_idle();
    uint64_t base = (mode == 0) ? 0 : (mode == 1 ? 6 : 2);
    policy(base); wait_idle();
    uint64_t fgc = 0, bgc = 0;
    for (unsigned r = 0; r < ROUNDS; ++r) {
      if (mode == 2) policy(6);
      uint64_t t0 = cycles();
      uint64_t s = scan(fg, FG_WORDS);
#if FG_STORES
      fg[(r * 64) % FG_WORDS] = fg[(r * 64) % FG_WORDS];
#endif
      uint64_t t1 = cycles();
      if (mode == 2) policy(2);
      uint64_t t2 = cycles();
      uint64_t b = scan(bg, BG_WORDS);
      uint64_t t3 = cycles();
      if (s != fg_sum || b != bg_sum) {
        bp_print_string("[BSG-FAIL] checksum mode/round "); bp_hprint_uint64(mode);
        bp_hprint_uint64(r); bp_print_string("\n"); bp_finish(1);
      }
      if (r >= WARMUP) { fgc += t1 - t0; bgc += t3 - t2; }
    }
    bp_print_string("FGBG mode="); bp_print_string((char *)names[mode]); bp_print_string(" ");
    print_kv("fg_cycles=", fgc); print_kv("bg_cycles=", bgc);
    print_kv("rounds=", ROUNDS - WARMUP); print_kv("fg_kib=", FG_KIB); print_kv("bg_kib=", BG_KIB);
    bp_print_string("\n");
  }
  policy(0); wait_idle();
  bp_print_string("[BSG-PASS] retained fg/bg benchmark\n");
  bp_finish(0);
}
