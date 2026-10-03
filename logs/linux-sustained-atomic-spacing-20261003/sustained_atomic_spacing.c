/*
 * Linux U-mode sustained AMOSWAP -> CTZ -> context-switch spacing probe.
 * Contexts 0 and 2 exchange a shared ready bitmap for 128 round trips.  The
 * final drain uses a direct constant target so it cannot alias the protocol
 * under test.  Cases run from eight bubbles downward to retain a last-good
 * boundary if a shorter sequence stalls the core.
 */
#include "../../testing/mt_seed.h"

typedef unsigned long u64;
#define TURNS 128

static volatile u64 ready_word __attribute__((used, aligned(64))) = 4;
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

#define PEER(name, nops)                                                     \
static __attribute__((naked, noinline, noreturn, used, aligned(8)))          \
void name(void)                                                              \
{                                                                            \
  __asm__ volatile(                                                          \
    ".option push\n.option norvc\n"                                         \
    "lla t2, ready_word\n"                                                  \
    "li t0, 128\n"                                                         \
    "1:\n"                                                                 \
    "li t3, 4\n"                                                           \
    "amoswap.d.aqrl t4, t3, (t2)\n"                                        \
    "fence rw, rw\n"                                                       \
    "ctz t4, t4\n" nops                                                    \
    "csrw 0x800, t4\n"                                                     \
    "addi t0, t0, -1\n"                                                    \
    "bnez t0, 1b\n"                                                        \
    "lla t1, observed_context\n"                                            \
    "csrr t3, 0x800\n"                                                     \
    "sd t3, 0(t1)\n"                                                       \
    "lla t1, peer_complete\n"                                               \
    "li t3, 1\n"                                                           \
    "sd t3, 0(t1)\n"                                                       \
    "fence rw, rw\n"                                                       \
    "csrw 0x800, zero\n"                                                   \
    "2: j 2b\n"                                                            \
    ".option pop\n");                                                       \
}

#define RING(name, nops)                                                     \
static __attribute__((noinline, aligned(8))) void name(void)                 \
{                                                                            \
  __asm__ volatile(                                                          \
    ".option push\n.option norvc\n"                                         \
    "lla t2, ready_word\n"                                                  \
    "li t0, 128\n"                                                         \
    "1:\n"                                                                 \
    "li t3, 1\n"                                                           \
    "amoswap.d.aqrl t4, t3, (t2)\n"                                        \
    "fence rw, rw\n"                                                       \
    "ctz t4, t4\n" nops                                                    \
    "csrw 0x800, t4\n"                                                     \
    "addi t0, t0, -1\n"                                                    \
    "bnez t0, 1b\n"                                                        \
    ".option pop\n" : : : "t0", "t1", "t2", "t3", "t4", "memory");    \
}

PEER(peer0, "")
PEER(peer1, "nop\n")
PEER(peer2, "nop\nnop\n")
PEER(peer3, "nop\nnop\nnop\n")
PEER(peer4, "nop\nnop\nnop\nnop\n")
PEER(peer5, "nop\nnop\nnop\nnop\nnop\n")
PEER(peer6, "nop\nnop\nnop\nnop\nnop\nnop\n")
PEER(peer7, "nop\nnop\nnop\nnop\nnop\nnop\nnop\n")
PEER(peer8, "nop\nnop\nnop\nnop\nnop\nnop\nnop\nnop\n")

RING(ring0, "")
RING(ring1, "nop\n")
RING(ring2, "nop\nnop\n")
RING(ring3, "nop\nnop\nnop\n")
RING(ring4, "nop\nnop\nnop\nnop\n")
RING(ring5, "nop\nnop\nnop\nnop\nnop\n")
RING(ring6, "nop\nnop\nnop\nnop\nnop\nnop\n")
RING(ring7, "nop\nnop\nnop\nnop\nnop\nnop\nnop\n")
RING(ring8, "nop\nnop\nnop\nnop\nnop\nnop\nnop\nnop\n")

static int trial(unsigned spacing, void (*ring)(void), void (*peer)(void))
{
  ready_word = 4;
  observed_context = ~0UL;
  peer_complete = 0;
  seed_npc(2, (u64)peer);
  __asm__ volatile("fence rw, rw" : : : "memory");
  u64 begin = cycles();
  ring();
  __asm__ volatile("li t0, 2\ncsrw 0x800, t0" : : : "t0", "memory");
  u64 end = cycles();
  put("SUSTAINED_AMO_CTZ nops/observed/complete/word/source/cycles: ");
  number(spacing); put(" "); number(observed_context); put(" ");
  number(peer_complete); put(" "); number(ready_word); put(" ");
  number(context()); put(" "); number(end - begin); put("\n");
  return observed_context == 2 && peer_complete == 1 && context() == 0;
}

void _start(void)
{
  if (context() != 0) finish(2);
  int pass = 1;
  pass &= trial(8, ring8, peer8);
  pass &= trial(7, ring7, peer7);
  pass &= trial(6, ring6, peer6);
  pass &= trial(5, ring5, peer5);
  pass &= trial(4, ring4, peer4);
  pass &= trial(3, ring3, peer3);
  pass &= trial(2, ring2, peer2);
  pass &= trial(1, ring1, peer1);
  pass &= trial(0, ring0, peer0);
  if (!pass) {
    put("[SUSTAINED-ATOMIC-SPACING] FAIL\n");
    finish(1);
  }
  put("[SUSTAINED-ATOMIC-SPACING] PASS\n");
  finish(0);
}
