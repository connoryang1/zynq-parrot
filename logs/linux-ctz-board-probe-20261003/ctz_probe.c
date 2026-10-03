typedef unsigned long u64;

static volatile u64 inputs[] __attribute__((aligned(64))) = {
  0, 1, 2, 4, 1UL << 9, 1UL << 31, 1UL << 32, 1UL << 63
};
static volatile u64 outputs[sizeof(inputs) / sizeof(inputs[0])];

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

static void number(u64 n)
{
  char buf[21];
  unsigned i = sizeof(buf) - 1;
  buf[i] = 0;
  do { buf[--i] = '0' + n % 10; n /= 10; } while (n);
  put(buf + i);
}

static __attribute__((noreturn)) void finish(u64 code)
{
  register u64 a0 __asm__("a0") = code;
  register u64 a7 __asm__("a7") = 93;
  __asm__ volatile("ecall" : : "r"(a0), "r"(a7) : "memory");
  __builtin_unreachable();
}

void _start(void)
{
  static const u64 expected[] = {64, 0, 1, 2, 9, 31, 32, 63};
  for (unsigned i = 0; i < sizeof(inputs) / sizeof(inputs[0]); ++i) {
    volatile u64 *in = &inputs[i];
    volatile u64 *out = &outputs[i];
    __asm__ volatile(
      ".option push\n.option norvc\n.option arch,+zbb\n"
      "ld t0, 0(%0)\n"
      "ctz t0, t0\n"
      "sd t0, 0(%1)\n"
      ".option pop\n"
      : : "r"(in), "r"(out) : "t0", "memory");
  }
  for (unsigned i = 0; i < sizeof(inputs) / sizeof(inputs[0]); ++i) {
    put("CTZ index/input/output/expected: ");
    number(i); put(" "); number(inputs[i]); put(" ");
    number(outputs[i]); put(" "); number(expected[i]); put("\n");
    if (outputs[i] != expected[i]) {
      put("[LINUX-CTZ-PROBE] FAIL\n");
      finish(1);
    }
  }
  put("[LINUX-CTZ-PROBE] PASS\n");
  finish(0);
}
