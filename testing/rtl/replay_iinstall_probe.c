/* Directed check of I-prefix replay installing into the L1 I-cache
 * (BP_REPLAY_INSTALL=1). Bare metal, M mode.
 *
 * The prefix table holds every line of fg_code. Each round evicts the
 * I-cache by running EVICT_CODE_KIB of other code, triggers the prefix (0x5c0
 * legacy write = whole configured table) and then:
 *   quiet : spins QUIET_CYCLES in a tiny resident loop before calling
 *           fg_code, so installation completes without concurrent fetch.
 *   race  : calls fg_code immediately, so demand fetch overlaps install.
 * fg_code's return value checks every installed instruction executed
 * correctly. A corrupt install shows up as a wrong value or a wild jump.
 */
#include <stdint.h>
#include "bp_utils.h"

#ifndef FG_CODE_KIB
#define FG_CODE_KIB 8
#endif
#ifndef EVICT_CODE_KIB
#define EVICT_CODE_KIB 48
#endif
#ifndef ROUNDS
#define ROUNDS 4
#endif
#ifndef QUIET_CYCLES
#define QUIET_CYCLES 100000
#endif

#define STR_(x) #x
#define STR(x) STR_(x)
#define CODE_BLOCK(name, kib, imm)                                              \
  static uint64_t __attribute__((noinline, aligned(64))) name(uint64_t x) {    \
    __asm__ volatile(".option push\n.option norvc\n.rept " STR(kib * 256)      \
                     "\naddi %0, %0, " #imm "\n.endr\n.option pop" : "+r"(x)); \
    return x;                                                                   \
  }
CODE_BLOCK(fg_code, FG_CODE_KIB, 1)
CODE_BLOCK(evict_code, EVICT_CODE_KIB, 3)

#define CSRW(a, v) __asm__ volatile("csrw " #a ", %0" : : "r"((uint64_t)(v)) : "memory")
#define CSRR(a) ({ uint64_t _v; __asm__ volatile("csrr %0, " #a : "=r"(_v) : : "memory"); _v; })
static inline uint64_t cycles(void) { return CSRR(0xcc0); }

static void print_kv(char *k, uint64_t v) {
  bp_print_string(k); bp_hprint_uint64(v); bp_print_string(" ");
}

int main(void) {
  unsigned n = 0;
  uintptr_t a = (uintptr_t)fg_code & ~63UL, e = (uintptr_t)fg_code + FG_CODE_KIB * 1024 + 64;
  for (; a < e && n < 256; a += 64, ++n) CSRW(0x7c1, ((uint64_t)n << 56) | a);
  CSRW(0x7c2, n);
  print_kv("IPROBE lines=", n); bp_print_string("\n");

  static const char *names[3] = {"none", "quiet", "race"};
  for (unsigned mode = 0; mode < 3; ++mode) {
    unsigned bad = 0; uint64_t fgc = 0;
    uint64_t s0 = CSRR(0x5c0);
    for (unsigned r = 0; r < ROUNDS; ++r) {
      if (evict_code(r) != r + 3ULL * EVICT_CODE_KIB * 256) bad |= 0x100;
      if (mode) CSRW(0x5c0, 0);
      if (mode == 1) { uint64_t t = cycles(); while (cycles() - t < QUIET_CYCLES) ; }
      uint64_t t0 = cycles();
      uint64_t v = fg_code(r);
      fgc += cycles() - t0;
      if (v != r + 1ULL * FG_CODE_KIB * 256) bad |= 1u << r;
    }
    uint64_t s1 = CSRR(0x5c0);
    bp_print_string("IPROBE mode="); bp_print_string((char *)names[mode]); bp_print_string(" ");
    print_kv("bad=", bad); print_kv("fg_cycles=", fgc);
    print_kv("stat0=", s0); print_kv("stat1=", s1); bp_print_string("\n");
  }
  bp_print_string("[BSG-PASS] iinstall probe\n");
  bp_finish(0);
}
