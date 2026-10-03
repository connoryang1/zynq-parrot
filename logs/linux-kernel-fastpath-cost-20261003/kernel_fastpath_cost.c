typedef unsigned long u64;
typedef long s64;
#define SAMPLES 512
#define WARMUPS 64
#define PATHS 5
#define SYS_FUTEX 98
#define SYS_SCHED_YIELD 124
#define SYS_GETTID 178
#define FUTEX_WAIT_PRIVATE 128
#define FUTEX_WAKE_PRIVATE 129

struct sample { u64 cycles, instructions; };
static struct sample samples[PATHS][SAMPLES];
static volatile int futex_word = 1;
static const char *const names[PATHS] = {
  "empty", "gettid", "futex_wake_no_waiter", "futex_wait_mismatch", "sched_yield_no_peer"
};

static inline u64 cycles(void)
{
  u64 value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
  return value;
}

static inline u64 instructions(void)
{
  u64 value;
  __asm__ volatile("csrr %0, 0xc02" : "=r"(value) : : "memory");
  return value;
}

static inline s64 raw_syscall6(s64 number, s64 a0, s64 a1, s64 a2,
                               s64 a3, s64 a4, s64 a5)
{
  register s64 x10 __asm__("a0") = a0;
  register s64 x11 __asm__("a1") = a1;
  register s64 x12 __asm__("a2") = a2;
  register s64 x13 __asm__("a3") = a3;
  register s64 x14 __asm__("a4") = a4;
  register s64 x15 __asm__("a5") = a5;
  register s64 x17 __asm__("a7") = number;
  __asm__ volatile("ecall" : "+r"(x10)
                   : "r"(x11), "r"(x12), "r"(x13), "r"(x14), "r"(x15), "r"(x17)
                   : "memory");
  return x10;
}

static void put(const char *s)
{
  u64 n = 0;
  while (s[n]) ++n;
  (void)raw_syscall6(64, 1, (s64)s, n, 0, 0, 0);
}

static void number(u64 n)
{
  char buf[21]; unsigned i = sizeof(buf)-1; buf[i] = 0;
  do { buf[--i] = '0' + n%10; n /= 10; } while (n);
  put(buf+i);
}

static __attribute__((noreturn)) void finish(s64 code)
{
  (void)raw_syscall6(93, code, 0, 0, 0, 0, 0);
  __builtin_unreachable();
}

static s64 execute(unsigned path)
{
  switch (path) {
    case 0: __asm__ volatile("" : : : "memory"); return 0;
    case 1: return raw_syscall6(SYS_GETTID, 0, 0, 0, 0, 0, 0);
    case 2: return raw_syscall6(SYS_FUTEX, (s64)&futex_word,
                                FUTEX_WAKE_PRIVATE, 1, 0, 0, 0);
    case 3: return raw_syscall6(SYS_FUTEX, (s64)&futex_word,
                                FUTEX_WAIT_PRIVATE, 0, 0, 0, 0);
    case 4: return raw_syscall6(SYS_SCHED_YIELD, 0, 0, 0, 0, 0, 0);
    default: finish(2);
  }
}

static int valid(unsigned path, s64 result)
{
  if (path == 0 || path == 2 || path == 4) return result == 0;
  if (path == 1) return result > 0;
  return result == -11; /* -EAGAIN */
}

static void measure(unsigned path, struct sample *out)
{
  u64 c0=cycles(), i0=instructions();
  s64 result=execute(path);
  u64 i1=instructions(), c1=cycles();
  if (!valid(path,result)) { put("[LINUX-KERNEL-FASTPATH-COST] FAIL result\n"); finish(2); }
  out->cycles=c1-c0; out->instructions=i1-i0;
}

static void report(unsigned path, int instruction_metric)
{
  u64 sorted[SAMPLES];
  for (unsigned i=0; i<SAMPLES; ++i)
    sorted[i]=instruction_metric ? samples[path][i].instructions : samples[path][i].cycles;
  for (unsigned i=1; i<SAMPLES; ++i) {
    u64 value=sorted[i]; unsigned j=i;
    while (j && sorted[j-1] > value) { sorted[j]=sorted[j-1]; --j; }
    sorted[j]=value;
  }
  put("RESULT path="); put(names[path]); put(" metric=");
  put(instruction_metric ? "instructions" : "cycles");
  put(" samples=512 min="); number(sorted[0]);
  put(" p25="); number(sorted[SAMPLES/4]);
  put(" median_x2="); number(sorted[SAMPLES/2-1]+sorted[SAMPLES/2]);
  put(" p75="); number(sorted[3*SAMPLES/4]);
  put(" p95="); number(sorted[95*SAMPLES/100]);
  put(" p99="); number(sorted[99*SAMPLES/100]);
  put(" max="); number(sorted[SAMPLES-1]); put("\n");
}

void _start(void)
{
  for (unsigned iteration=0; iteration<WARMUPS+SAMPLES; ++iteration)
    for (unsigned offset=0; offset<PATHS; ++offset) {
      unsigned path=(iteration+offset)%PATHS; struct sample current;
      measure(path,&current);
      if (iteration>=WARMUPS) samples[path][iteration-WARMUPS]=current;
    }
  put("LINUX_KERNEL_FASTPATH_COST samples=512 warmups=64\n");
  for (unsigned path=0; path<PATHS; ++path) { report(path,0); report(path,1); }
  put("[LINUX-KERNEL-FASTPATH-COST] PASS\n"); finish(0);
}
