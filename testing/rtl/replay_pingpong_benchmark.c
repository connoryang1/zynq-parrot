/* Two programs taking turns, each evicting the other (bare metal, M mode).
 *
 * Program A and program B are symmetric. Each turn runs:
 *   1. a shared switch path (SW_CODE_KIB code, SW_KIB data): the OS switch;
 *   2. the program's hot work (HOT_CODE_KIB code over HOT_KIB data); the
 *      time from switch-in to the end of hot work is the switch-in latency;
 *   3. the program's streaming work (STREAM_CODE_KIB code, STREAM_KIB data),
 *      which is not worth remembering and evicts the other program.
 * Each program's address list holds the switch path plus its own hot code
 * and data: code lines in its half of the 256-entry code table, data lines in
 * its own data slot (A: slot 0, B: slot 1).
 *
 *   off   : no replay.
 *   wake  : at the end of its turn a program triggers the other's list (the
 *           point where the OS knows who runs next).
 *   early : trigger before the last TAIL_KIB of streaming work.
 *   warm  : reference; the program's switch-in and hot work run once, untimed,
 *           immediately before the measured switch-in.
 * Reports per-turn switch-in latency and total cycles for both programs.
 */
#include <stdint.h>
#include "bp_utils.h"

#ifndef SW_CODE_KIB
#define SW_CODE_KIB 4
#endif
#ifndef SW_KIB
#define SW_KIB 2
#endif
#ifndef HOT_CODE_KIB
#define HOT_CODE_KIB 3
#endif
#ifndef HOT_KIB
#define HOT_KIB 12
#endif
#ifndef STREAM_CODE_KIB
#define STREAM_CODE_KIB 24
#endif
#ifndef STREAM_KIB
#define STREAM_KIB 48
#endif
#ifndef TAIL_KIB
#define TAIL_KIB 16
#endif
#ifndef ROUNDS
#define ROUNDS 4
#endif
#ifndef WARMUP
#define WARMUP 1
#endif
#ifndef MODES
#define MODES 0x7
#endif
#ifndef TAIL_SPIN
#define TAIL_SPIN 0  /* diagnostic: >0 replaces the tail scan by an idle wait of this many cycles */
#endif

#define STR_(x) #x
#define STR(x) STR_(x)
#define W(kib) ((kib) * 128)

static volatile uint64_t sw[W(SW_KIB)] __attribute__((aligned(4096)));
static volatile uint64_t hot[2][W(HOT_KIB)] __attribute__((aligned(4096)));
static volatile uint64_t stream[2][W(STREAM_KIB)] __attribute__((aligned(4096)));

#define CODE_BLOCK(name, kib, imm)                                              \
  static uint64_t __attribute__((noinline, aligned(64))) name(uint64_t x) {    \
    __asm__ volatile(".option push\n.option norvc\n.rept " STR(kib * 256)      \
                     "\naddi %0, %0, " #imm "\n.endr\n.option pop" : "+r"(x)); \
    return x;                                                                   \
  }
CODE_BLOCK(sw_code, SW_CODE_KIB, 5)
CODE_BLOCK(hot_code_a, HOT_CODE_KIB, 1)
CODE_BLOCK(hot_code_b, HOT_CODE_KIB, 2)
CODE_BLOCK(stream_code_a, STREAM_CODE_KIB, 3)
CODE_BLOCK(stream_code_b, STREAM_CODE_KIB, 4)
typedef uint64_t (*code_fn)(uint64_t);
static const code_fn hot_code[2] = {hot_code_a, hot_code_b};
static const code_fn stream_code[2] = {stream_code_a, stream_code_b};
static const uint64_t hot_imm[2] = {1, 2}, stream_imm[2] = {3, 4};

#define CSRW(a, v) __asm__ volatile("csrw " #a ", %0" : : "r"((uint64_t)(v)) : "memory")
#define CSRR(a) ({ uint64_t _v; __asm__ volatile("csrr %0, " #a : "=r"(_v) : : "memory"); _v; })
static inline uint64_t cycles(void) { return CSRR(0xcc0); }

static uint64_t scan(volatile uint64_t *a, unsigned words) {
  uint64_t s = 0;
  for (unsigned i = 0; i < words; i += 8)
    s += a[i] + a[i+1] + a[i+2] + a[i+3] + a[i+4] + a[i+5] + a[i+6] + a[i+7];
  return s;
}
static uint64_t sw_sum, hot_sum[2], head_sum[2], tail_sum[2];
static void check(int ok, unsigned code) {
  if (ok) return;
  bp_print_string("[BSG-FAIL] check "); bp_hprint_uint64(code); bp_print_string("\n");
  bp_finish(1);
}
static void print_kv(char *k, uint64_t v) {
  bp_print_string(k); bp_hprint_uint64(v); bp_print_string(" ");
}

/* Address lists. */
static unsigned i_start[2], i_count[2], d_count[2];
static unsigned n_i;
static void rec_i(const void *p, unsigned bytes) {
  uintptr_t a = (uintptr_t)p & ~63UL, e = (uintptr_t)p + bytes;
  for (; a < e && n_i < 256; a += 64, ++n_i)
    CSRW(0x7c1, ((uint64_t)n_i << 56) | a);
}
static void rec_d(unsigned slot, const volatile void *p, unsigned bytes) {
  uintptr_t a = (uintptr_t)p & ~63UL, e = (uintptr_t)p + bytes;
  for (; a < e && d_count[slot] < 256; a += 64, ++d_count[slot]) {
    unsigned n = d_count[slot];
    CSRW(0x9c1, ((uint64_t)slot << 45) | ((uint64_t)((n >> 5) & 0x1f) << 48)
                | ((uint64_t)(n & 0x1f) << 40) | a);
  }
}
static void replay(unsigned p) {
  CSRW(0x9c3, p);                                              /* data slot p */
  CSRW(0x5c0, (1ULL << 63) | ((uint64_t)i_count[p] << 8) | i_start[p]);  /* code */
}

#define STREAM_HEAD_WORDS W(STREAM_KIB - TAIL_KIB)

int main(void) {
  for (unsigned i = 0; i < W(SW_KIB); ++i) { sw[i] = i * 0x51ed27ULL; sw_sum += sw[i]; }
  for (unsigned p = 0; p < 2; ++p) {
    for (unsigned i = 0; i < W(HOT_KIB); ++i) {
      hot[p][i] = (i + p) * 0x9e3779b97f4a7c15ULL; hot_sum[p] += hot[p][i];
    }
    for (unsigned i = 0; i < W(STREAM_KIB); ++i) {
      stream[p][i] = i ^ (0xc8f72015ULL + p);
      if (i < STREAM_HEAD_WORDS) head_sum[p] += stream[p][i]; else tail_sum[p] += stream[p][i];
    }
  }
  for (unsigned p = 0; p < 2; ++p) {
    i_start[p] = n_i;
    rec_i((const void *)sw_code, SW_CODE_KIB * 1024 + 64);
    rec_i((const void *)hot_code[p], HOT_CODE_KIB * 1024 + 64);
    i_count[p] = n_i - i_start[p];
    rec_d(p, sw, sizeof(sw));
    rec_d(p, hot[p], sizeof(hot[p]));
    CSRW(0x9c2, p | ((uint64_t)(d_count[p] & 0x3f) << 2) | ((uint64_t)(d_count[p] >> 6) << 32));
  }
  CSRW(0x7c2, n_i);
  print_kv("PINGPONG lists i_a=", i_count[0]); print_kv("i_b=", i_count[1]);
  print_kv("d_a=", d_count[0]); print_kv("d_b=", d_count[1]); bp_print_string("\n");

  static const char *names[4] = {"off", "wake", "early", "warm"};
  for (unsigned mode = 0; mode < 4; ++mode) {
    if (!((MODES >> mode) & 1)) continue;
    uint64_t lat[2] = {0, 0}, total = 0, ph_sw = 0, ph_code = 0, ph_data = 0;
    uint64_t is0 = CSRR(0x5c0), ds0 = CSRR(0x9c3);
    for (unsigned r = 0; r < ROUNDS; ++r) {
      uint64_t r0 = cycles();
      for (unsigned p = 0; p < 2; ++p) {
        if (mode == 3) {
          check(sw_code(r) == r + 5ULL * SW_CODE_KIB * 256, 1);
          check(scan(sw, W(SW_KIB)) == sw_sum, 2);
          check(hot_code[p](r) == r + hot_imm[p] * HOT_CODE_KIB * 256, 3);
          check(scan(hot[p], W(HOT_KIB)) == hot_sum[p], 4);
        }
        uint64_t t0 = cycles();
        check(sw_code(r) == r + 5ULL * SW_CODE_KIB * 256, 1);
        check(scan(sw, W(SW_KIB)) == sw_sum, 2);
        uint64_t ta = cycles();
        check(hot_code[p](r) == r + hot_imm[p] * HOT_CODE_KIB * 256, 3);
        uint64_t tb = cycles();
        check(scan(hot[p], W(HOT_KIB)) == hot_sum[p], 4);
        uint64_t t1 = cycles();
        if (r >= WARMUP) { ph_sw += ta - t0; ph_code += tb - ta; ph_data += t1 - tb; }
        check(stream_code[p](r) == r + stream_imm[p] * STREAM_CODE_KIB * 256, 5);
        check(scan(stream[p], STREAM_HEAD_WORDS) == head_sum[p], 6);
        if (mode == 2) replay(p ^ 1);
        if (TAIL_SPIN) { uint64_t s0 = cycles(); while (cycles() - s0 < TAIL_SPIN) ; }
        else check(scan(stream[p] + STREAM_HEAD_WORDS, W(STREAM_KIB) - STREAM_HEAD_WORDS) == tail_sum[p], 7);
        if (mode == 1) replay(p ^ 1);
        if (r >= WARMUP) lat[p] += t1 - t0;
      }
      if (r >= WARMUP) total += cycles() - r0;
    }
    uint64_t is1 = CSRR(0x5c0), ds1 = CSRR(0x9c3);
    bp_print_string("PINGPONG mode="); bp_print_string((char *)names[mode]); bp_print_string(" ");
    print_kv("lat_a=", lat[0]); print_kv("lat_b=", lat[1]); print_kv("total=", total);
    print_kv("rounds=", ROUNDS - WARMUP);
    print_kv("ph_sw=", ph_sw); print_kv("ph_code=", ph_code); print_kv("ph_data=", ph_data);
    print_kv("istat0=", is0); print_kv("istat1=", is1); print_kv("dstat0=", ds0); print_kv("dstat1=", ds1);
    bp_print_string("\n");
  }
  bp_print_string("[BSG-PASS] replay pingpong benchmark\n");
  bp_finish(0);
}
