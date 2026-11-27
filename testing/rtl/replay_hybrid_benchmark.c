/* Address record-and-replay across a modeled context switch (bare metal, M mode).
 *
 * Same structure as retained_fgbg_kernel_benchmark: every handoff runs a
 * shared "switch" block (SW_CODE_KIB of code, a SW_KIB read-mostly scan and
 * SW_STORES state updates) standing in for the Linux futex/scheduler path; the
 * foreground then runs FG_CODE_KIB of code over FG_KIB of data, and the
 * background runs its own switch-in plus BG_CODE_KIB of code and a BG_KIB scan
 * that evicts everything from L1/L2.
 *
 * The foreground's footprint is recorded as physical line addresses (here
 * programmed once from the known layout: an oracle recording) into the
 * hardware replay tables: switch-path then foreground code into the shared
 * I-prefix table (CSRs 0x7c1/0x7c2), switch-path data then foreground data
 * into D footprint slot 0 (0x9c1/0x9c2). A single 0x9c3 write with the follow
 * bit launches the I prefix and then the D slot through the detached fill
 * lanes; nothing else changes.
 *
 *   off   : no replay.
 *   wake  : trigger at the end of the background's turn (the futex wake that
 *           makes the foreground runnable), i.e. just before its switch-in.
 *   early : trigger before the background's final BG_TAIL_KIB of scanning
 *           (a scheduler that knows the foreground is next).
 *   warm  : reference; foreground switch-in + work re-run immediately before.
 * fg latency = foreground switch-in + work, as in the kernel-path benchmark.
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
#ifndef BG_TAIL_KIB
#define BG_TAIL_KIB 16
#endif
#ifndef ROUNDS
#define ROUNDS 6
#endif
#ifndef WARMUP
#define WARMUP 2
#endif
#ifndef I_ENTRIES
#define I_ENTRIES 256
#endif
#ifndef D_ENTRIES
#define D_ENTRIES 256
#endif

#define STR_(x) #x
#define STR(x) STR_(x)
#define FG_WORDS (FG_KIB * 128)
#define SW_WORDS (SW_KIB * 128)
#define BG_WORDS (BG_KIB * 128)
#define BG_HEAD_WORDS ((BG_KIB - BG_TAIL_KIB) * 128)

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
#define CSRW(a, v) __asm__ volatile("csrw " #a ", %0" : : "r"((uint64_t)(v)) : "memory")
#define CSRR(a) ({ uint64_t _v; __asm__ volatile("csrr %0, " #a : "=r"(_v) : : "memory"); _v; })

static uint64_t scan(volatile uint64_t *a, unsigned words) {
  uint64_t s = 0;
  for (unsigned i = 0; i < words; i += 8)
    s += a[i] + a[i+1] + a[i+2] + a[i+3] + a[i+4] + a[i+5] + a[i+6] + a[i+7];
  return s;
}
static uint64_t sw_sum, fg_sum, bg_sum, bg_head_sum, bg_tail_sum;
static void check_at(int ok, unsigned mode, unsigned r, unsigned line) {
  if (ok) return;
  bp_print_string("[BSG-FAIL] check mode/round/line "); bp_hprint_uint64(mode);
  bp_hprint_uint64(r); bp_hprint_uint64(line); bp_print_string("\n"); bp_finish(1);
}
#define check(ok, mode, r) check_at((ok), (mode), (r), __LINE__)
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

/* Recording: append every 64-byte line of [p, p+bytes) to a table. */
static unsigned n_i, n_d;
static void rec_i(const void *p, unsigned bytes) {
  uintptr_t a = (uintptr_t)p & ~63UL, e = (uintptr_t)p + bytes;
  for (; a < e && n_i < I_ENTRIES; a += 64, ++n_i)
    CSRW(0x7c1, ((uint64_t)(n_i & 0xff) << 56) | a);
}
static void rec_d(const volatile void *p, unsigned bytes) {
  uintptr_t a = (uintptr_t)p & ~63UL, e = (uintptr_t)p + bytes;
  for (; a < e && n_d < D_ENTRIES; a += 64, ++n_d)
    /* slot 0; index bits 4:0 -> 44:40, 9:5 -> 52:48 */
    CSRW(0x9c1, ((uint64_t)((n_d >> 5) & 0x1f) << 48) | ((uint64_t)(n_d & 0x1f) << 40) | a);
}
#ifndef TRIG
#define TRIG 0  /* 0: I prefix then D slot (follow); 1: D only; 2: I only; 3: both concurrently */
#endif
#ifndef MODES
#define MODES 0xf
#endif
static void trigger(void) {
  if (TRIG == 0) CSRW(0x9c3, 0 | 4);           /* slot 0, follow (I prefix first) */
  else if (TRIG == 1) CSRW(0x9c3, 0);
  else if (TRIG == 2) CSRW(0x5c0, (1ULL << 63) | ((uint64_t)n_i << 8));  /* I range [0, n_i) */
  else { CSRW(0x9c3, 0); CSRW(0x5c0, (1ULL << 63) | ((uint64_t)n_i << 8)); }  /* 3: both lanes at once */
}

int main(void) {
  for (unsigned i = 0; i < FG_WORDS; ++i) { fg[i] = i * 0x9e3779b97f4a7c15ULL; fg_sum += fg[i]; }
  for (unsigned i = 0; i < SW_WORDS; ++i) { sw[i] = i * 0x51ed27ULL; sw_sum += sw[i]; }
  for (unsigned i = 0; i < BG_WORDS; ++i) {
    bg[i] = i ^ 0xc8f72015ULL; bg_sum += bg[i];
    if (i < BG_HEAD_WORDS) bg_head_sum += bg[i]; else bg_tail_sum += bg[i];
  }
  /* Record the switch path first (it runs first after the wake), then the fg. */
  rec_i((const void *)sw_code, SW_CODE_KIB * 1024 + 64);
  rec_i((const void *)fg_code, FG_CODE_KIB * 1024 + 64);
  CSRW(0x7c2, n_i);
  rec_d(sw, sizeof(sw));
  rec_d(sw_written, sizeof(sw_written));
  rec_d(fg, sizeof(fg));
  CSRW(0x9c2, 0 | ((uint64_t)(n_d & 0x3f) << 2) | ((uint64_t)(n_d >> 6) << 32));
  bp_print_string("HYBRID tables i_lines="); bp_hprint_uint64(n_i);
  bp_print_string(" d_lines="); bp_hprint_uint64(n_d); bp_print_string("\n");

  static const char *names[4] = {"off", "wake", "early", "warm"};
  for (unsigned mode = 0; mode < 4; ++mode) {
    if (!((MODES >> mode) & 1)) continue;
    uint64_t fgc = 0, bgc = 0;
    uint64_t is0 = CSRR(0x5c0), ds0 = CSRR(0x9c3);
    for (unsigned r = 0; r < ROUNDS; ++r) {
      if (mode == 3) { switch_path(mode, r, 1); fg_work(mode, r); }
      uint64_t t0 = cycles();
      switch_path(mode, r, 2 * r);               /* foreground switch-in */
      fg_work(mode, r);
      uint64_t t1 = cycles();
      switch_path(mode, r, 2 * r + 1);           /* background switch-in */
      check(bg_code(r) == r + 3ULL * BG_CODE_KIB * 256, mode, r);
      check(scan(bg, BG_HEAD_WORDS) == bg_head_sum, mode, r);
      if (mode == 2) trigger();                  /* early: scheduler knows fg is next */
      if (scan(bg + BG_HEAD_WORDS, BG_WORDS - BG_HEAD_WORDS) != bg_tail_sum) {
        /* Diagnostic: report the first word that differs from its initial value. */
        for (unsigned i = BG_HEAD_WORDS; i < BG_WORDS; ++i)
          if (bg[i] != (i ^ 0xc8f72015ULL)) {
            bp_print_string("BGBAD idx/addr/val/time ");
            bp_hprint_uint64(i); bp_hprint_uint64((uint64_t)&bg[i]); bp_hprint_uint64(bg[i]);
            bp_hprint_uint64(cycles()); bp_print_string("\n");
            break;
          }
        check(0, mode, r);
      }
      if (mode == 1) trigger();                  /* wake: futex wake of the fg */
      uint64_t t2 = cycles();
      if (r >= WARMUP) { fgc += t1 - t0; bgc += t2 - t1; }
    }
    uint64_t is1 = CSRR(0x5c0), ds1 = CSRR(0x9c3);
    bp_print_string("HYBRID mode="); bp_print_string((char *)names[mode]); bp_print_string(" ");
    print_kv("fg_cycles=", fgc); print_kv("bg_cycles=", bgc);
    print_kv("rounds=", ROUNDS - WARMUP);
    print_kv("istat0=", is0); print_kv("istat1=", is1); print_kv("dstat0=", ds0); print_kv("dstat1=", ds1);
    bp_print_string("\n");
  }
  bp_print_string("[BSG-PASS] replay hybrid benchmark\n");
  bp_finish(0);
}
