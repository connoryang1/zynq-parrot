#include "../../testing/mt_seed.h"
typedef unsigned long u64;
#define LINES 4096
#define LINE_BYTES 64
#define PEER_DONE 0x50415353UL

unsigned char source_data[LINES * LINE_BYTES] __attribute__((aligned(4096)));
unsigned char peer_data[LINES * LINE_BYTES] __attribute__((aligned(4096)));
volatile u64 expected_address[2] __attribute__((aligned(64)));
volatile u64 observed_address[2] __attribute__((aligned(64)));
volatile u64 mismatch_iteration[2] __attribute__((aligned(64)));
volatile u64 peer_done;
volatile u64 probe_iterations;
volatile u64 translation_sink;

static void put(const char *s) {
  u64 n=0; while(s[n]) ++n;
  register u64 a0 __asm__("a0")=1;
  register const char *a1 __asm__("a1")=s;
  register u64 a2 __asm__("a2")=n;
  register u64 a7 __asm__("a7")=64;
  __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a7):"memory");
}
static void number(u64 n) {
  char b[22]; unsigned i=21; b[i]=0;
  do { b[--i]='0'+n%10; n/=10; } while(n); put(b+i);
}
static __attribute__((noreturn)) void finish(u64 code) {
  register u64 a0 __asm__("a0")=code, a7 __asm__("a7")=93;
  __asm__ volatile("ecall"::"r"(a0),"r"(a7):"memory"); __builtin_unreachable();
}

/* Both contexts calculate a distinct line address, publish it, issue the hint,
 * switch, and verify t0 immediately on return before dereferencing it. */
#define WORKER_BODY(id, target, base, after_return, mismatch, done) \
  ".option push\n.option norvc\n" \
  "lla a0, " base "\nlla a2, probe_iterations\nld a2, 0(a2)\n" \
  "lla a4, expected_address\nlla a5, observed_address\n" \
  "lla a6, mismatch_iteration\naddi a4, a4, " #id "*8\n" \
  "addi a5, a5, " #id "*8\naddi a6, a6, " #id "*8\n" \
  "1: addi t3, a2, -1\nslli t0, t3, 6\nadd t0, a0, t0\n" \
  "sd t0, 0(a4)\nori zero, t0, 1\ncsrw 0x800, " #target "\n" after_return \
  "ld t1, 0(a4)\nbeq t0, t1, 2f\nsd t0, 0(a5)\nsd a2, 0(a6)\n" mismatch \
  "2: ld t2, 0(t0)\naddi a2, a2, -1\nbnez a2, 1b\n" done \
  ".option pop\n"

static __attribute__((naked,noinline,noreturn,used,aligned(8))) void peer(void) {
  __asm__ volatile(WORKER_BODY(1, 0, "peer_data", "",
    "fence rw,rw\ncsrwi 0x800,0\n3:j 3b\n",
    "lla t0, peer_done\nli t1, 0x50415353\nsd t1, 0(t0)\n"
    "fence rw,rw\ncsrwi 0x800,0\n3:j 3b\n"));
}
static __attribute__((naked,noinline,used,aligned(8))) void source(void) {
  __asm__ volatile(WORKER_BODY(0, 1, "source_data",
    "lla t4, mismatch_iteration\nld t4, 8(t4)\nbeqz t4, 8f\nret\n8:\n",
    "ret\n", "ret\n"));
}

void _start(void) {
  put("[PREFETCH-SWITCH-REG] start\n");
  for (u64 i=0;i<LINES;i++) { source_data[i*LINE_BYTES]=(unsigned char)i; peer_data[i*LINE_BYTES]=(unsigned char)(i+1); }
  static const u64 phases[] = {256};
  int ok=1;
  for (unsigned phase=0; phase<sizeof(phases)/sizeof(phases[0]); ++phase) {
    probe_iterations=phases[phase]; peer_done=0;
    mismatch_iteration[0]=mismatch_iteration[1]=0;
    observed_address[0]=observed_address[1]=0;
    /* Prime only one line per 4 KiB page. Seven of every eight cache lines
     * remain untouched, while all eight source/peer translations are recent. */
    for (u64 offset=0; offset<probe_iterations*LINE_BYTES; offset+=4096)
      translation_sink += source_data[offset] + peer_data[offset];
    put("[PREFETCH-SWITCH-REG] phase begin "); number(probe_iterations); put("\n");
    seed_npc(1,(u64)peer);
    source();
    if (!mismatch_iteration[0] && !mismatch_iteration[1])
      __asm__ volatile("csrwi 0x800,1":::"memory");
    ok=peer_done==PEER_DONE && !mismatch_iteration[0] && !mismatch_iteration[1];
    if (!ok) break;
    put("[PREFETCH-SWITCH-REG] phase pass "); number(probe_iterations); put("\n");
  }
  put("[PREFETCH-SWITCH-REG] source_iter/expected/observed peer_iter/expected/observed done: ");
  number(mismatch_iteration[0]); put(" "); number(expected_address[0]); put(" "); number(observed_address[0]); put(" ");
  number(mismatch_iteration[1]); put(" "); number(expected_address[1]); put(" "); number(observed_address[1]); put(" "); number(peer_done); put("\n");
  put(ok ? "[PREFETCH-SWITCH-REG] PASS\n" : "[PREFETCH-SWITCH-REG] FAIL\n");
  finish(ok?0:1);
}
