/* Linux-hosted persistent context-group ready-selector benchmark. */
#include "../../testing/mt_seed.h"

typedef unsigned long u64;

#define SAMPLES 128
#define TURNS 128
#define TOTAL_TURNS (SAMPLES * TURNS)
#define MAX_SC_FAILURES (TOTAL_TURNS / 100)
#define SPECTATOR_BIT 8
#define SOURCE_BIT 1
#define SOURCE_S11 0x13579bdfUL
#define PEER_S11 0x2468ace0UL
#define STRINGIFY_INNER(value) #value
#define STRINGIFY(value) STRINGIFY_INNER(value)

static volatile u64 ready_word __attribute__((aligned(64)));
static volatile u64 observed_context[2] __attribute__((aligned(64)));
static volatile u64 peer_complete[2] __attribute__((aligned(64)));
static volatile u64 peer_pid[2] __attribute__((aligned(64)));
static volatile u64 peer_s11[2] __attribute__((aligned(64)));
static volatile u64 peer_sc_failures[2] __attribute__((aligned(64)));
static u64 source_sc_failures[2] __attribute__((aligned(64)));
static u64 samples[2][SAMPLES] __attribute__((aligned(64)));
static u64 own_pid;

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

static void put(const char *text)
{
  u64 length = 0;
  while (text[length]) ++length;
  (void)syscall3(64, 1, (long)text, length);
}

static void number(u64 value)
{
  char buffer[21];
  unsigned position = sizeof(buffer) - 1;
  buffer[position] = 0;
  do {
    buffer[--position] = '0' + value % 10;
    value /= 10;
  } while (value);
  put(buffer + position);
}

static __attribute__((noreturn)) void finish(long code)
{
  (void)syscall3(93, code, 0, 0);
  __builtin_unreachable();
}

static inline u64 cycles(void)
{
  u64 value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
  return value;
}

static inline u64 context(void)
{
  u64 value;
  __asm__ volatile("csrr %0, 0x800" : "=r"(value) : : "memory");
  return value;
}

static inline u64 source_s11(void)
{
  u64 value;
  __asm__ volatile("mv %0, s11" : "=r"(value));
  return value;
}

#define LRSC_STEP(source_bit)                                               \
    "2: lr.d.aq t4, (t2)\n"                                               \
    "beqz t4, 2b\n"                                                       \
    ".option arch, +zbb\n"                                                \
    "ctz t5, t4\n"                                                        \
    "li t6, 1\n"                                                          \
    "sll t6, t6, t5\n"                                                    \
    "not t6, t6\n"                                                        \
    "and t6, t4, t6\n"                                                    \
    "ori t6, t6, " STRINGIFY(source_bit) "\n"                             \
    "sc.d.rl t3, t6, (t2)\n"                                              \
    "beqz t3, 3f\n"                                                       \
    "addi a6, a6, 1\n"                                                    \
    "j 2b\n"                                                              \
    "3: csrw 0x800, t5\n"

#define PEER(name, peer_bit, result_index)                                  \
static __attribute__((naked, noinline, noreturn, used, aligned(8)))          \
void name(void)                                                             \
{                                                                           \
  __asm__ volatile(                                                         \
    ".option push\n.option norvc\n"                                        \
    "lla t2, ready_word\n"                                                 \
    "li t0, " STRINGIFY(TOTAL_TURNS) "\n"                                 \
    "li a6, 0\n"                                                           \
    "1:\n"                                                                \
    LRSC_STEP(peer_bit)                                                      \
    "addi t0, t0, -1\n"                                                    \
    "bnez t0, 1b\n"                                                        \
    "lla t2, peer_sc_failures\n"                                           \
    "sd a6, " STRINGIFY(8 * result_index) "(t2)\n"                        \
    "lla t2, observed_context\n"                                           \
    "csrr t3, 0x800\n"                                                     \
    "sd t3, " STRINGIFY(8 * result_index) "(t2)\n"                        \
    "lla t2, peer_s11\n"                                                   \
    "sd s11, " STRINGIFY(8 * result_index) "(t2)\n"                       \
    "li a7, 172\n"                                                         \
    "ecall\n"                                                              \
    "lla t2, peer_pid\n"                                                   \
    "sd a0, " STRINGIFY(8 * result_index) "(t2)\n"                        \
    "lla t2, peer_complete\n"                                              \
    "li t3, 1\n"                                                           \
    "sd t3, " STRINGIFY(8 * result_index) "(t2)\n"                        \
    "fence rw, rw\n"                                                       \
    "csrw 0x800, zero\n"                                                   \
    "4: j 4b\n"                                                            \
    ".option pop\n");                                                      \
}

PEER(peer_resident, 2, 0)
PEER(peer_nonresident, 4, 1)

static __attribute__((noinline, aligned(8))) u64 ring(void)
{
  u64 failures;
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "lla t2, ready_word\n"
    "li t0, " STRINGIFY(TURNS) "\n"
    "li a6, 0\n"
    "1:\n"
    LRSC_STEP(SOURCE_BIT)
    "addi t0, t0, -1\n"
    "bnez t0, 1b\n"
    "mv %0, a6\n"
    ".option pop\n"
    : "=r"(failures)
    :
    : "t0", "t1", "t2", "t3", "t4", "t5", "t6", "a6", "memory");
  return failures;
}

static int compare(const u64 *left, const u64 *right)
{
  return (*left > *right) - (*left < *right);
}

static void report(const char *name, const u64 *values, u64 source_failures,
                   u64 target_failures)
{
  u64 sorted[SAMPLES];
  for (unsigned i = 0; i < SAMPLES; ++i) sorted[i] = values[i];
  for (unsigned i = 1; i < SAMPLES; ++i) {
    u64 value = sorted[i];
    unsigned j = i;
    while (j && compare(&sorted[j - 1], &value) > 0) {
      sorted[j] = sorted[j - 1];
      --j;
    }
    sorted[j] = value;
  }
  put("CONTEXT_GROUP mode/min/median/p95/max/cycles_x100_per_handoff/source_sc_failures/peer_sc_failures: ");
  put(name); put(" ");
  number(sorted[0]); put(" ");
  number(sorted[SAMPLES / 2]); put(" ");
  number(sorted[(95 * SAMPLES) / 100]); put(" ");
  number(sorted[SAMPLES - 1]); put(" ");
  number(sorted[SAMPLES / 2] * 100 / (2 * TURNS)); put(" ");
  number(source_failures); put(" ");
  number(target_failures); put("\n");
  put("CONTEXT_GROUP_RAW mode="); put(name);
  for (unsigned i = 0; i < SAMPLES; ++i) {
    put(" "); number(values[i]);
  }
  put("\n");
}

static int phase(unsigned index, u64 target, u64 target_bit,
                 void (*peer)(void), const char *name)
{
  put("CONTEXT_GROUP_PHASE start="); put(name); put("\n");
  ready_word = target_bit | SPECTATOR_BIT;
  observed_context[index] = ~0UL;
  peer_complete[index] = 0;
  peer_pid[index] = 0;
  peer_s11[index] = 0;
  peer_sc_failures[index] = ~0UL;
  source_sc_failures[index] = 0;
  seed_reg(target, 27, PEER_S11);
  seed_npc(target, (u64)peer);
  __asm__ volatile("fence rw, rw" : : : "memory");
  put("CONTEXT_GROUP_PHASE seeded="); put(name); put("\n");

  for (unsigned sample = 0; sample < SAMPLES; ++sample) {
    u64 begin = cycles();
    source_sc_failures[index] += ring();
    u64 end = cycles();
    samples[index][sample] = end - begin;
  }

  put("CONTEXT_GROUP_PHASE ring_complete="); put(name); put("\n");
  __asm__ volatile("csrw 0x800, %0" : : "r"(target) : "memory");
  int ok = context() == 0 && source_s11() == SOURCE_S11
      && ready_word == (target_bit | SPECTATOR_BIT)
      && observed_context[index] == target && peer_complete[index] == 1
      && peer_pid[index] == own_pid && peer_s11[index] == PEER_S11;
  report(name, samples[index], source_sc_failures[index],
         peer_sc_failures[index]);
  return ok && source_sc_failures[index] <= MAX_SC_FAILURES
      && peer_sc_failures[index] <= MAX_SC_FAILURES;
}

void _start(void)
{
  if (context() != 0) finish(2);
  own_pid = (u64)syscall3(172, 0, 0, 0);
  if ((long)own_pid <= 0) finish(2);
  __asm__ volatile("mv s11, %0" : : "r"(SOURCE_S11) : "s11", "memory");
  int resident_ok = phase(0, 1, 2, peer_resident, "resident");
  int nonresident_ok = phase(1, 2, 4, peer_nonresident, "nonresident");
  if (!resident_ok || !nonresident_ok) {
    put("[LINUX-CONTEXT-GROUP] FAIL\n");
    finish(1);
  }
  put("[LINUX-CONTEXT-GROUP] PASS\n");
  finish(0);
}
