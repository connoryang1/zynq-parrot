/*
 * Fresh-boot diagnostic for the compact ready-bitmap failure.  Repeat only
 * the nonresident context-2 path so that a first-trial failure implicates the
 * ld -> ctz -> csrw sequence, while a later failure implicates reseed/reuse.
 */
#include "../../testing/mt_seed.h"
typedef unsigned long u64;
#define TURNS 128
static volatile u64 source_word __attribute__((aligned(64)));
static volatile u64 peer_word __attribute__((aligned(64)));
static volatile u64 observed __attribute__((aligned(64)));
static volatile u64 complete __attribute__((aligned(64)));
static inline long sys(long n,long a0,long a1,long a2){register long x10 __asm__("a0")=a0,x11 __asm__("a1")=a1,x12 __asm__("a2")=a2,x17 __asm__("a7")=n;__asm__ volatile("ecall":"+r"(x10):"r"(x11),"r"(x12),"r"(x17):"memory");return x10;}
static void put(const char*s){u64 n=0;while(s[n])++n;(void)sys(64,1,(long)s,n);}
static void number(u64 n){char b[21];unsigned i=20;b[i]=0;do{b[--i]='0'+n%10;n/=10;}while(n);put(b+i);}
static __attribute__((noreturn)) void finish(long c){(void)sys(93,c,0,0);__builtin_unreachable();}
static inline u64 context(void){u64 v;__asm__ volatile("csrr %0,0x800":"=r"(v)::"memory");return v;}
static inline u64 cycles(void){u64 v;__asm__ volatile("csrr %0,0xcc0":"=r"(v)::"memory");return v;}

static __attribute__((naked,noinline,noreturn,used,aligned(8))) void peer_bitmap(void){__asm__ volatile(
 ".option push\n.option norvc\nlla t2,peer_word\nli t0,128\n1:\n"
 "ld t4,0(t2)\nctz t4,t4\ncsrw 0x800,t4\n"
 "addi t0,t0,-1\nbnez t0,1b\nlla t1,observed\ncsrr t3,0x800\nsd t3,0(t1)\n"
 "lla t1,complete\nli t3,1\nsd t3,0(t1)\nfence rw,rw\ncsrw 0x800,zero\n2:j 2b\n.option pop\n");}
static __attribute__((noinline,aligned(8))) void ring_bitmap(void){__asm__ volatile(
 ".option push\n.option norvc\nlla t2,source_word\nli t0,128\n1:\n"
 "ld t4,0(t2)\nctz t4,t4\ncsrw 0x800,t4\n"
 "addi t0,t0,-1\nbnez t0,1b\n.option pop\n":::"t0","t1","t2","t3","t4","memory");}

static int trial(unsigned iteration){
 source_word=4;peer_word=1;observed=~0UL;complete=0;seed_npc(2,(u64)peer_bitmap);__asm__ volatile("fence rw,rw":::"memory");
 u64 begin=cycles();ring_bitmap();__asm__ volatile("li t0,2\ncsrw 0x800,t0":::"t0","memory");u64 end=cycles();
 put("BITMAP2_REPEAT iteration/observed/complete/source/cycles: ");number(iteration);put(" ");number(observed);put(" ");number(complete);put(" ");number(context());put(" ");number(end-begin);put("\n");
 return observed==2&&complete==1&&context()==0;
}
void _start(void){
 if(context()!=0)finish(2);
 for(unsigned i=0;i<8;i++) if(!trial(i)){put("[BITMAP2-REPEAT] FAIL\n");finish(1);}
 put("[BITMAP2-REPEAT] PASS\n");finish(0);
}
