/*
 * Linux U-mode nonresident switch-spacing benchmark for the fixed
 * two-bank/four-context FPGA. Run once per fresh overlay/Linux boot: Linux
 * does not reclaim the extra contexts when this process exits. No libc or FP.
 * Timing includes ring-loop/call/counter overhead and any Linux interruption;
 * it is not isolated redirect latency or Linux scheduler context-switch cost.
 */
typedef unsigned long u64;
#define REPEATS 7
#define SWITCHES 256
#define SOURCE_S11 0x13579bdfUL
#define PEER_S11 0x2468ace0UL

static volatile u64 result[3] __attribute__((used, aligned(16)));

static void put(const char *s)
{
  u64 n = 0;
  while (s[n]) ++n;
  register u64 a0 __asm__("a0") = 1;
  register const char *a1 __asm__("a1") = s;
  register u64 a2 __asm__("a2") = n;
  register u64 a7 __asm__("a7") = 64;
  __asm__ volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a7) : "memory");
}

static __attribute__((noreturn)) void finish(u64 code)
{
  register u64 a0 __asm__("a0") = code;
  register u64 a7 __asm__("a7") = 93;
  __asm__ volatile("ecall" : : "r"(a0), "r"(a7) : "memory");
  __builtin_unreachable();
}

static void number(u64 n)
{
  char buf[21];
  unsigned i = sizeof(buf) - 1;
  buf[i] = 0;
  do { buf[--i] = '0' + n % 10; n /= 10; } while (n);
  put(buf + i);
}

static inline u64 cycles(void)
{
  u64 v;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(v) : : "memory");
  return v;
}

static inline u64 context(void)
{
  u64 v;
  __asm__ volatile("csrr %0, 0x800" : "=r"(v) : : "memory");
  return v;
}

static inline u64 source_s11(void)
{
  u64 v;
  __asm__ volatile("mv %0, s11" : "=r"(v));
  return v;
}

/* The last timed return suspends before the loop terminates; one additional
 * untimed handoff drains it and records completion, context identity, and GPR.
 * The 128 completion sentinel is reached only after the four unrolled groups;
 * the disassembly, not that constant alone, establishes the switch count.
 * The naked peer never uses the inherited stack or a C calling convention.
 */
static __attribute__((naked, noinline, noreturn, used, aligned(8))) void peer(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "li t0, 4\n1:\n.rept 32\ncsrwi 0x800, 0\n.endr\n"
    "addi t0, t0, -1\nbnez t0, 1b\n"
    "lla t1, result\ncsrr t2, 0x800\nsd t2, 0(t1)\n"
    "sd s11, 8(t1)\nli t2, 128\nsd t2, 16(t1)\n"
    "fence rw, rw\ncsrwi 0x800, 0\n2: j 2b\n.option pop\n");
}

static __attribute__((noinline, aligned(8))) void nonresident_ring(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "li t0, 4\n1:\n.rept 32\ncsrwi 0x800, 2\n.endr\n"
    "addi t0, t0, -1\nbnez t0, 1b\n.option pop\n"
    : : : "t0", "memory");
}

static u64 trial(void)
{
  result[0] = result[1] = result[2] = 0;
  u64 reg = (27UL << 41) | (2UL << 39) | PEER_S11;
  u64 npc = (2UL << 39) | ((u64)peer & 0x7fffffffffUL);
  __asm__ volatile("csrw 0x802, %0\ncsrw 0x801, %1"
                   : : "r"(reg), "r"(npc) : "memory");
  u64 begin = cycles();
  nonresident_ring();
  u64 end = cycles();
  __asm__ volatile("csrwi 0x800, 2" : : : "memory");
  if (end <= begin || context() != 0 || source_s11() != SOURCE_S11
      || result[0] != 2 || result[1] != PEER_S11 || result[2] != 128) {
    put("[BP-LINUX-BENCH] FAIL: counter/context/register/completion check\n");
    finish(1);
  }
  return end - begin;
}

static void report(const char *name, const u64 *samples)
{
  u64 min = samples[0], max = min, sorted[REPEATS];
  put(name); put(" raw cycles (256 switches each):");
  for (unsigned i = 0; i < REPEATS; ++i) {
    put(" "); number(samples[i]);
    if (samples[i] < min) min = samples[i];
    if (samples[i] > max) max = samples[i];
    sorted[i] = samples[i];
  }
  for (unsigned i = 1; i < REPEATS; ++i) {
    u64 v = sorted[i]; unsigned j = i;
    while (j && sorted[j-1] > v) { sorted[j] = sorted[j-1]; --j; }
    sorted[j] = v;
  }
  put("\n"); put(name); put(" cycles/switch x100 min/median/max: ");
  number(min * 100 / SWITCHES); put("/");
  number(sorted[REPEATS/2] * 100 / SWITCHES); put("/");
  number(max * 100 / SWITCHES); put("\n");
}

void _start(void)
{
  put("[BP-LINUX-BENCH] start: 2 resident banks, 4 logical contexts\n");
  if (context() != 0) finish(1);
  __asm__ volatile("mv s11, %0" : : "r"(SOURCE_S11) : "s11", "memory");
  u64 nonresident[REPEATS];
  /* Warm each ring immediately before its sample; keep console I/O out of
   * the entire series. Interrupts remain enabled, as in an ordinary C app. */
  for (unsigned i = 0; i < REPEATS; ++i) {
    (void)trial(); nonresident[i] = trial();
  }
  report("nonresident", nonresident);
  put("[BP-LINUX-BENCH] PASS: all timed rings and register checks\n");
  finish(0);
}
