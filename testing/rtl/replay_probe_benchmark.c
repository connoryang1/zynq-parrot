/* Address-replay probe (bare metal, M mode, no translation).
 *
 * The foreground's FG_KIB buffer is evicted by a BG_KIB background scan, then
 * read once per line. Modes:
 *   cold    : demand misses only.
 *   late    : prefetch.r every foreground line, then scan immediately
 *             (replay triggered at switch-in).
 *   early   : prefetch.r every line, run GAP iterations of unrelated ALU work
 *             (standing in for the kernel switch path), then scan
 *             (pre-wake trigger).
 *   warm    : no eviction (reference floor).
 * Reports the cycles for the hint loop and for the scan separately.
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
#define ROUNDS 4
#endif
#ifndef GAP
#define GAP 20000
#endif

static volatile uint8_t fg[FG_KIB * 1024] __attribute__((aligned(4096)));
static volatile uint8_t bg[BG_KIB * 1024] __attribute__((aligned(4096)));

static inline uint64_t cycles(void) {
  uint64_t v; __asm__ volatile("csrr %0, 0xcc0" : "=r"(v) : : "memory"); return v;
}
static uint64_t scan(volatile uint8_t *a, unsigned bytes) {
  uint64_t s = 0;
  for (unsigned i = 0; i < bytes; i += 64) s += a[i];
  return s;
}
static void hint(volatile uint8_t *a, unsigned bytes) {
  for (unsigned i = 0; i < bytes; i += 64)
    __asm__ volatile("ori zero, %0, 1" : : "r"(a + i) : "memory");
}
static void print_kv(char *k, uint64_t v) {
  bp_print_string(k); bp_hprint_uint64(v); bp_print_string(" ");
}

int main(void) {
  uint64_t expect = 0;
  for (unsigned i = 0; i < sizeof(fg); i += 64) { fg[i] = (uint8_t)(i / 64); expect += (uint8_t)(i / 64); }
  for (unsigned i = 0; i < sizeof(bg); i += 64) bg[i] = (uint8_t)i;
  static char *names[4] = {"cold", "late", "early", "warm"};
  for (unsigned mode = 0; mode < 4; ++mode) {
    uint64_t hc = 0, sc = 0;
    for (unsigned r = 0; r < ROUNDS + 1; ++r) {
      if (mode != 3) (void)scan(bg, sizeof(bg));
      else (void)scan(fg, sizeof(fg));
      uint64_t t0 = cycles();
      if (mode == 1 || mode == 2) hint(fg, sizeof(fg));
      uint64_t t1 = cycles();
      if (mode == 2) { uint64_t x = r; for (unsigned g = 0; g < GAP / 4; ++g) __asm__ volatile("addi %0, %0, 1" : "+r"(x)); }
      uint64_t t2 = cycles();
      uint64_t s = scan(fg, sizeof(fg));
      uint64_t t3 = cycles();
      if (s != expect) { bp_print_string("[BSG-FAIL] checksum\n"); bp_finish(1); }
      if (r) { hc += t1 - t0; sc += t3 - t2; }
    }
    bp_print_string("REPLAY mode="); bp_print_string(names[mode]); bp_print_string(" ");
    print_kv("hint_cycles=", hc); print_kv("scan_cycles=", sc); print_kv("rounds=", ROUNDS);
    print_kv("lines=", FG_KIB * 16);
    bp_print_string("\n");
  }
  bp_print_string("[BSG-PASS] replay probe\n");
  bp_finish(0);
}
