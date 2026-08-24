#include <stdint.h>

#define BP_GLOBAL_CYCLE_CSR 0xcc0
#define PROBE_SAMPLES 1024

static inline uint64_t read_global_cycle(void) {
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) :: "memory");
  return value;
}

static inline long linux_write(unsigned long fd, const void *buffer,
                               unsigned long length) {
  register unsigned long a0 __asm__("a0") = fd;
  register const void *a1 __asm__("a1") = buffer;
  register unsigned long a2 __asm__("a2") = length;
  register unsigned long a7 __asm__("a7") = 64;

  __asm__ volatile("ecall"
                   : "+r"(a0)
                   : "r"(a1), "r"(a2), "r"(a7)
                   : "memory");
  return (long)a0;
}

__attribute__((noreturn)) static void linux_exit(unsigned long status) {
  register unsigned long a0 __asm__("a0") = status;
  register unsigned long a7 __asm__("a7") = 93;

  __asm__ volatile("ecall" : : "r"(a0), "r"(a7) : "memory");
  for (;;) {
    __asm__ volatile("nop");
  }
}

static void write_hex64(uint64_t value) {
  static const char digits[] = "0123456789abcdef";
  char output[19];

  output[0] = '0';
  output[1] = 'x';
  for (unsigned int i = 0; i < 16; i++) {
    unsigned int shift = 60U - 4U * i;
    output[2 + i] = digits[(value >> shift) & 0xfU];
  }
  output[18] = '\n';
  linux_write(1, output, sizeof(output));
}

__attribute__((noreturn, used)) void _start(void) {
  static const char start_label[] = "[BP-LINUX-INFO] global cycle start: ";
  static const char end_label[] = "[BP-LINUX-INFO] global cycle end:   ";
  static const char delta_label[] = "[BP-LINUX-INFO] global cycle delta: ";
  static const char pass_message[] =
      "[BP-LINUX-PASS] global cycle CSR accessible and monotonic\n";
  static const char fail_message[] =
      "[BP-LINUX-FAIL] global cycle CSR did not advance monotonically\n";

  uint64_t start = read_global_cycle();
  uint64_t previous = start;
  int monotonic = 1;

  for (unsigned int i = 0; i < PROBE_SAMPLES; i++) {
    uint64_t current = read_global_cycle();
    if (current < previous)
      monotonic = 0;
    previous = current;
  }

  linux_write(1, start_label, sizeof(start_label) - 1);
  write_hex64(start);
  linux_write(1, end_label, sizeof(end_label) - 1);
  write_hex64(previous);
  linux_write(1, delta_label, sizeof(delta_label) - 1);
  write_hex64(previous - start);

  if (monotonic && previous > start) {
    linux_write(1, pass_message, sizeof(pass_message) - 1);
    linux_exit(0);
  }

  linux_write(1, fail_message, sizeof(fail_message) - 1);
  linux_exit(1);
}
