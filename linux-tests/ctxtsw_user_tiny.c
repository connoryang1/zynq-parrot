/*
 * Tiny no-libc Linux user-mode context-switch smoke test.
 *
 * This is intentionally suitable for transfer through an interactive serial
 * shell: it has no dynamic loader, no libc, and no filesystem dependencies.
 * It still executes as an ordinary Linux U-mode ELF and uses Linux write/exit
 * syscalls for its evidence.  Context 2 remains register/stack independent.
 */

typedef unsigned long u64;
typedef long s64;

#define BP_CSR_CTXT      0x800
#define BP_CSR_CTXT_NPC  0x801
#define BP_CONTEXT_SHIFT  39
#define BP_CONTEXT_BITS   2
#define BP_REG_SHIFT      (BP_CONTEXT_SHIFT + BP_CONTEXT_BITS)
#define BP_NPC_MASK       0x7fffffffffUL
#define BP_VALUE_MASK     0x7fffffffffUL
#define BP_TARGET_MAGIC   0x4354585452475432UL
#define BP_SOURCE_S11     0x0000000013579bdfUL
#define BP_TARGET_S11_IN  0x000000002468ace0UL
#define BP_TARGET_S11_OUT 0x0000000031415926UL

#ifndef BP_TARGET_SYSCALL
#define BP_TARGET_SYSCALL 1
#endif

/* The target context writes all fields before returning.  Requiring both
 * target-owned control-flow evidence and independently seeded GPR state
 * prevents a redirect-only implementation from being mistaken for a full
 * nonresident save/restore. */
static volatile u64 target_result[4] __attribute__((used, aligned(16)));
static const char target_entered[] __attribute__((used)) =
  "[BP-LINUX-CTXTSW] target context entered\n";

static s64 sys_write(const char *buffer, u64 length)
{
  register s64 a0 __asm__("a0") = 1;
  register const char *a1 __asm__("a1") = buffer;
  register u64 a2 __asm__("a2") = length;
  register s64 a7 __asm__("a7") = 64;
  __asm__ volatile ("ecall"
                    : "+r"(a0)
                    : "r"(a1), "r"(a2), "r"(a7)
                    : "memory");
  return a0;
}

static __attribute__((noreturn)) void sys_exit(s64 status)
{
  register s64 a0 __asm__("a0") = status;
  register s64 a7 __asm__("a7") = 93;
  __asm__ volatile ("ecall" : : "r"(a0), "r"(a7) : "memory");
  __builtin_unreachable();
}

static __attribute__((noreturn)) void sys_poweroff(void)
{
  register s64 a0 __asm__("a0") = 0xfee1dead;
  register s64 a1 __asm__("a1") = 0x28121969;
  register s64 a2 __asm__("a2") = 0x4321fedc;
  register s64 a3 __asm__("a3") = 0;
  register s64 a7 __asm__("a7") = 142;
  __asm__ volatile ("ecall"
                    : "+r"(a0)
                    : "r"(a1), "r"(a2), "r"(a3), "r"(a7)
                    : "memory");

  /* A successful reboot syscall does not return. */
  sys_exit(2);
}

static void put(const char *string, u64 length)
{
  (void)sys_write(string, length);
}

#define PUT(string) put((string), sizeof(string) - 1)

static inline u64 read_context(void)
{
  u64 value;
  __asm__ volatile ("csrr %0, 0x800" : "=r"(value) : : "memory");
  return value;
}

static inline void seed_context2_npc(u64 npc)
{
  const u64 value = (2UL << BP_CONTEXT_SHIFT) | (npc & BP_NPC_MASK);
  __asm__ volatile ("csrw 0x801, %0" : : "r"(value) : "memory");
}

static inline void seed_context2_reg(u64 reg, u64 value)
{
  const u64 encoded = (value & BP_VALUE_MASK)
                      | (2UL << BP_CONTEXT_SHIFT)
                      | ((reg & 0x1fUL) << BP_REG_SHIFT);
  __asm__ volatile ("csrw 0x802, %0" : : "r"(encoded) : "memory");
}

static inline void write_s11(u64 value)
{
  __asm__ volatile ("mv s11, %0" : : "r"(value) : "s11", "memory");
}

static inline u64 read_s11(void)
{
  u64 value;
  __asm__ volatile ("mv %0, s11" : "=r"(value) : : "memory");
  return value;
}

static __attribute__((naked, noinline, noreturn, used)) void context2_return(void)
{
  __asm__ volatile (
#if BP_TARGET_SYSCALL
    "li a0, 1\n\t"
    "lla a1, target_entered\n\t"
    "li a2, 41\n\t"
    "li a7, 64\n\t"
    "ecall\n\t"
#endif
    "lla t0, target_result\n\t"
    "li t1, 0x4354585452475432\n\t"
    "sd t1, 0(t0)\n\t"
    "csrr t1, 0x800\n\t"
    "sd t1, 8(t0)\n\t"
    "sd s11, 16(t0)\n\t"
    "li s11, 0x31415926\n\t"
    "sd s11, 24(t0)\n\t"
    "fence rw, rw\n\t"
    "csrwi 0x800, 0\n\t"
    "1: j 1b\n\t"
  );
}

void _start(void)
{
  PUT("[BP-LINUX-CTXTSW] tiny user-mode smoke start\n");
  if (read_context() != 0) {
    PUT("[BP-LINUX-CTXTSW] FAIL: expected context 0\n");
    sys_exit(1);
  }

  write_s11(BP_SOURCE_S11);
  seed_context2_reg(27 /* s11 */, BP_TARGET_S11_IN);
  PUT("[BP-LINUX-CTXTSW] switching 0 -> 2 -> 0\n");
  /* First-install CSR inheritance must sample the active Linux U-mode image,
   * so seed the NPC immediately before the handoff. */
  seed_context2_npc((u64)context2_return);
  __asm__ volatile ("csrwi 0x800, 2" : : : "memory");

  if (read_context() != 0) {
    PUT("[BP-LINUX-CTXTSW] FAIL: source resumed in wrong context\n");
    sys_exit(1);
  }

  if (target_result[0] != BP_TARGET_MAGIC) {
    PUT("[BP-LINUX-CTXTSW] FAIL: target context did not execute\n");
    sys_exit(1);
  }
  if (target_result[1] != 2) {
    PUT("[BP-LINUX-CTXTSW] FAIL: target reported wrong context\n");
    sys_exit(1);
  }
  if (target_result[2] != BP_TARGET_S11_IN
      || target_result[3] != BP_TARGET_S11_OUT) {
    PUT("[BP-LINUX-CTXTSW] FAIL: target GPR backing mismatch\n");
    sys_exit(1);
  }
  if (read_s11() != BP_SOURCE_S11) {
    PUT("[BP-LINUX-CTXTSW] FAIL: source GPR was not restored\n");
    sys_exit(1);
  }
  if (read_context() != 0) {
    PUT("[BP-LINUX-CTXTSW] FAIL: bad resumed context\n");
    sys_exit(1);
  }
  PUT("[BP-LINUX-CTXTSW] PASS: tiny user-mode handoff\n");
  sys_poweroff();
}
