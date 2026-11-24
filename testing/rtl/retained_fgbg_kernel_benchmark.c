/* Foreground/background retention with a modeled kernel switch path
 * (bare metal, M mode).
 *
 * Every handoff runs a shared "switch" block standing in for the Linux
 * futex/scheduler path: SW_CODE_KIB of straight-line code, a SW_KIB
 * read-mostly data scan, and SW_STORES stores to a small written area
 * (run-queue/task state). The foreground then runs FG_CODE_KIB of code and
 * scans FG_KIB of data; the background runs its own switch-in, then
 * BG_CODE_KIB of code and a BG_KIB scan, evicting everything from L1/L2.
 *
 *   off          : retention disabled.
 *   joint-user   : I+D lookups on; capture only during the foreground's own
 *                  work (what userspace prctl gating achieves under Linux).
 *   joint-kernel : capture from the foreground's switch-in through its work
 *                  (what kernel-managed gating at context switch achieves).
 *   warm         : reference ceiling; foreground switch-in + work re-run
 *                  immediately before the timed run, retention off.
 * fg latency = foreground switch-in + work (the wake-to-done analogue).
 */
#include <stdint.h>
#include "bp_utils.h"

#ifndef FG_KIB
#define FG_KIB 8
#endif
#ifndef FG_CODE_KIB
#define FG_CODE_KIB 8
#endif
#ifndef SW_KIB
#define SW_KIB 4
#endif
#ifndef SW_CODE_KIB
#define SW_CODE_KIB 8
#endif
#ifndef SW_STORES
#define SW_STORES 16
#endif
#ifndef BG_KIB
#define BG_KIB 64
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
#define SW_WORDS (SW_KIB * 128)
#define BG_WORDS (BG_KIB * 128)

static volatile uint64_t fg[FG_WORDS] __attribute__((aligned(4096)));
static volatile uint64_t sw[SW_WORDS] __attribute__((aligned(4096)));
static volatile uint64_t sw_written[SW_STORES * 8] __attribute__((aligned(4096)));
static volatile uint64_t bg[BG_WORDS] __attribute__((aligned(4096)));

#define CODE_BLOCK(name, kib, imm)                                              \
  static uint64_t __attribute__((noinline, aligned(64))) name(uint64_t x) {    \
    __asm__ volatile(".option push\n.option norvc\n.rept " STR(kib * 256)      \
                     "\naddi %0, %0, " #imm "\n.endr\n.option pop" : "+r"(x)); \
    return x;                                                                   \
  }
CODE_BLOCK(fg_code, FG_CODE_KIB, 1)
CODE_BLOCK(sw_code, SW_CODE_KIB, 5)
CODE_BLOCK(bg_code, BG_CODE_KIB, 3)

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
static uint64_t sw_sum, fg_sum, bg_sum;
static void check(int ok, unsigned mode, unsigned r) {
  if (ok) return;
  bp_print_string("[BSG-FAIL] check mode/round "); bp_hprint_uint64(mode);
  bp_hprint_uint64(r); bp_print_string("\n"); bp_finish(1);
}
/* The modeled kernel path: code, read-mostly data, a few state updates. */
static void switch_path(unsigned mode, unsigned r, uint64_t tag) {
  check(sw_code(r) == r + 5ULL * SW_CODE_KIB * 256, mode, r);
  check(scan(sw, SW_WORDS) == sw_sum, mode, r);
  for (unsigned i = 0; i < SW_STORES; ++i) sw_written[i * 8] = tag + i;
}
static void fg_work(unsigned mode, unsigned r) {
  check(fg_code(r) == r + 1ULL * FG_CODE_KIB * 256, mode, r);
  check(scan(fg, FG_WORDS) == fg_sum, mode, r);
}
static void print_kv(char *k, uint64_t v) {
  bp_print_string(k); bp_hprint_uint64(v); bp_print_string(" ");
}

int main(void) {
  for (unsigned i = 0; i < FG_WORDS; ++i) { fg[i] = i * 0x9e3779b97f4a7c15ULL; fg_sum += fg[i]; }
  for (unsigned i = 0; i < SW_WORDS; ++i) { sw[i] = i * 0x51ed27ULL; sw_sum += sw[i]; }
  for (unsigned i = 0; i < BG_WORDS; ++i) { bg[i] = i ^ 0xc8f72015ULL; bg_sum += bg[i]; }
  if (!(policy_status() >> 63)) { bp_print_string("[BSG-FAIL] no retained store\n"); bp_finish(1); }
  static const char *names[4] = {"off", "joint-user", "joint-kernel", "warm"};
  static const uint64_t enable[4] = {0, 3, 3, 0};
  for (unsigned mode = 0; mode < 4; ++mode) {
    policy(0); wait_idle();
    policy(enable[mode]); wait_idle();
    uint64_t fgc = 0, bgc = 0;
    for (unsigned r = 0; r < ROUNDS; ++r) {
      if (mode == 3) { switch_path(mode, r, 1); fg_work(mode, r); }
      if (mode == 2) policy(enable[mode] | 12);  /* kernel-managed: capture at switch-in */
      uint64_t t0 = cycles();
      switch_path(mode, r, 2 * r);               /* foreground switch-in */
      if (mode == 1) policy(enable[mode] | 12);  /* user-managed: capture after wake */
      fg_work(mode, r);
      if (mode == 1 || mode == 2) policy(enable[mode]);
      uint64_t t1 = cycles();
      switch_path(mode, r, 2 * r + 1);           /* background switch-in */
      check(bg_code(r) == r + 3ULL * BG_CODE_KIB * 256, mode, r);
      check(scan(bg, BG_WORDS) == bg_sum, mode, r);
      uint64_t t2 = cycles();
      if (r >= WARMUP) { fgc += t1 - t0; bgc += t2 - t1; }
    }
    bp_print_string("FGBG mode="); bp_print_string((char *)names[mode]); bp_print_string(" ");
    print_kv("fg_cycles=", fgc); print_kv("bg_cycles=", bgc);
    print_kv("rounds=", ROUNDS - WARMUP); print_kv("fg_kib=", FG_KIB); print_kv("fg_code_kib=", FG_CODE_KIB);
    print_kv("sw_kib=", SW_KIB); print_kv("sw_code_kib=", SW_CODE_KIB);
    bp_print_string("\n");
  }
  policy(0); wait_idle();
  bp_print_string("[BSG-PASS] retained fg/bg kernel-path benchmark\n");
  bp_finish(0);
}
