/*
 * Recoverable Linux U-mode probe for AMOSWAP -> CTZ -> context-switch
 * dependency spacing.  Every possible target is seeded with the same naked
 * return stub so a stale target observation produces evidence instead of a
 * wedged core.  Run once per fresh overlay boot because Linux does not reclaim
 * the extra context state when this process exits.
 */
#include "../../testing/mt_seed.h"

typedef unsigned long u64;

static volatile u64 ready_word __attribute__((used, aligned(64)));
static volatile u64 observed_context __attribute__((used, aligned(64)));
static volatile u64 peer_complete __attribute__((used, aligned(64)));

static inline long syscall3(long n, long a0, long a1, long a2)
{
  register long x10 __asm__("a0") = a0;
  register long x11 __asm__("a1") = a1;
  register long x12 __asm__("a2") = a2;
  register long x17 __asm__("a7") = n;
  __asm__ volatile("ecall" : "+r"(x10)
                   : "r"(x11), "r"(x12), "r"(x17) : "memory");
  return x10;
}

static void put(const char *s)
{
  u64 n = 0;
  while (s[n]) ++n;
  (void)syscall3(64, 1, (long)s, n);
}

static void number(u64 n)
{
  char b[21];
  unsigned i = 20;
  b[i] = 0;
  do { b[--i] = '0' + n % 10; n /= 10; } while (n);
  put(b + i);
}

static __attribute__((noreturn)) void finish(long code)
{
  (void)syscall3(93, code, 0, 0);
  __builtin_unreachable();
}

static inline u64 context(void)
{
  u64 value;
  __asm__ volatile("csrr %0, 0x800" : "=r"(value) : : "memory");
  return value;
}

static inline u64 cycles(void)
{
  u64 value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
  return value;
}

static __attribute__((naked, noinline, noreturn, used, aligned(8)))
void peer_return(void)
{
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "lla t0, observed_context\n"
    "csrr t1, 0x800\n"
    "sd t1, 0(t0)\n"
    "lla t0, peer_complete\n"
    "li t1, 1\n"
    "sd t1, 0(t0)\n"
    "fence rw, rw\n"
    "csrw 0x800, zero\n"
    "1: j 1b\n"
    ".option pop\n");
}

static void prepare_case(void)
{
  ready_word = 4;          /* CTZ must select logical context 2. */
  observed_context = ~0UL;
  peer_complete = 0;
  for (u64 tid = 1; tid < BP_NUM_CONTEXTS; ++tid)
    seed_npc(tid, (u64)peer_return);
  __asm__ volatile("fence rw, rw" : : : "memory");
}

#define RUN_CASE(index, nops) do {                                           \
  prepare_case();                                                            \
  u64 begin = cycles();                                                      \
  __asm__ volatile(                                                          \
    ".option push\n.option norvc\n"                                         \
    "li t0, 1\n"             /* Value visible before the AMO result. */      \
    "li t1, 1\n"             /* Bitmap published for the returning source. */\
    "lla t2, ready_word\n"                                                   \
    "amoswap.d.aqrl t0, t1, (t2)\n"                                         \
    "ctz t0, t0\n" nops                                                     \
    "csrw 0x800, t0\n"                                                      \
    ".option pop\n" : : : "t0", "t1", "t2", "memory");                    \
  u64 end = cycles();                                                        \
  results[index][0] = observed_context;                                      \
  results[index][1] = peer_complete;                                         \
  results[index][2] = ready_word;                                            \
  results[index][3] = context();                                             \
  results[index][4] = end - begin;                                           \
} while (0)

static u64 results[9][5];

static int report_case(unsigned i)
{
  put("AMO_CTZ_SWITCH nops/observed/complete/word/source/cycles: ");
  number(i);
  for (unsigned j = 0; j < 5; ++j) { put(" "); number(results[i][j]); }
  put("\n");
  return results[i][1] == 1 && results[i][2] == 1 && results[i][3] == 0;
}

void _start(void)
{
  if (context() != 0) finish(2);

  /* Descend from certainly safe spacing so a lower-spacing stall still
   * leaves a precise last-good boundary in the serial transcript. */
  RUN_CASE(8, "nop\nnop\nnop\nnop\nnop\nnop\nnop\nnop\n");
  int pass = report_case(8);
  RUN_CASE(7, "nop\nnop\nnop\nnop\nnop\nnop\nnop\n");
  pass &= report_case(7);
  RUN_CASE(6, "nop\nnop\nnop\nnop\nnop\nnop\n");
  pass &= report_case(6);
  RUN_CASE(5, "nop\nnop\nnop\nnop\nnop\n");
  pass &= report_case(5);
  RUN_CASE(4, "nop\nnop\nnop\nnop\n");
  pass &= report_case(4);
  RUN_CASE(3, "nop\nnop\nnop\n");
  pass &= report_case(3);
  RUN_CASE(2, "nop\nnop\n");
  pass &= report_case(2);
  RUN_CASE(1, "nop\n");
  pass &= report_case(1);
  RUN_CASE(0, "");
  pass &= report_case(0);
  if (!pass) {
    put("[AMO-CTZ-SPACING] FAIL\n");
    finish(1);
  }
  put("[AMO-CTZ-SPACING] PASS\n");
  finish(0);
}
