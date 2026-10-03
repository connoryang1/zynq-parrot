/* Recoverable Linux probe for load-to-context-switch spacing on the routed
 * dependency-tail candidate.  Stale target 2 and correct target 1 both enter
 * the same return stub, so every valid misselection is observable. */
#include "../../testing/mt_seed.h"
typedef unsigned long u64;
static volatile u64 target_word __attribute__((aligned(64))) = 1;
static volatile u64 observed __attribute__((aligned(64)));
static volatile u64 complete __attribute__((aligned(64)));
static inline long sys(long n,long a0,long a1,long a2){register long x10 __asm__("a0")=a0,x11 __asm__("a1")=a1,x12 __asm__("a2")=a2,x17 __asm__("a7")=n;__asm__ volatile("ecall":"+r"(x10):"r"(x11),"r"(x12),"r"(x17):"memory");return x10;}
static void put(const char*s){u64 n=0;while(s[n])++n;(void)sys(64,1,(long)s,n);}
static void number(u64 n){char b[21];unsigned i=20;b[i]=0;do{b[--i]='0'+n%10;n/=10;}while(n);put(b+i);}
static __attribute__((noreturn)) void finish(long c){(void)sys(93,c,0,0);__builtin_unreachable();}
static inline u64 context(void){u64 v;__asm__ volatile("csrr %0,0x800":"=r"(v)::"memory");return v;}
static inline u64 cycles(void){u64 v;__asm__ volatile("csrr %0,0xcc0":"=r"(v)::"memory");return v;}
static __attribute__((naked,noinline,noreturn,used,aligned(8))) void peer(void){__asm__ volatile(
  ".option push\n.option norvc\nlla t0,observed\ncsrr t1,0x800\nsd t1,0(t0)\n"
  "lla t0,complete\nli t1,1\nsd t1,0(t0)\nfence rw,rw\ncsrw 0x800,zero\n1:j 1b\n.option pop\n");}
static void prep(void){
  /* Context 0 is active and context 1 is initially resident.  Touch context 2
   * first so the two-bank replacement makes the target context 1 nonresident,
   * matching the full benchmark's mode-1 to mode-2 transition. */
  observed=~0UL;complete=0;seed_npc(2,(u64)peer);
  __asm__ volatile("fence rw,rw\nli t0,2\ncsrw 0x800,t0":::"t0","memory");
  observed=~0UL;complete=0;
  for(u64 i=1;i<BP_NUM_CONTEXTS;i++)seed_npc(i,(u64)peer);
  __asm__ volatile("fence rw,rw":::"memory");
}
static u64 result[9][4];
#define CASE(i,nops) do { prep(); u64 b=cycles(); __asm__ volatile(         \
  ".option push\n.option norvc\nli t0,2\nlla t1,target_word\n"              \
  "ld t0,0(t1)\n" nops "csrw 0x800,t0\n.option pop\n"                       \
  : : : "t0","t1","memory"); u64 e=cycles(); result[i][0]=observed;       \
  result[i][1]=complete; result[i][2]=context(); result[i][3]=e-b; } while(0)
static int report(unsigned i){put("LOAD_SWITCH nops/observed/complete/source/cycles: ");number(i);for(unsigned j=0;j<4;j++){put(" ");number(result[i][j]);}put("\n");return result[i][0]==1&&result[i][1]==1&&result[i][2]==0;}
void _start(void){if(context()!=0)finish(2);int pass=1;
 CASE(8,"nop\nnop\nnop\nnop\nnop\nnop\nnop\nnop\n");pass&=report(8);
 CASE(7,"nop\nnop\nnop\nnop\nnop\nnop\nnop\n");pass&=report(7);
 CASE(6,"nop\nnop\nnop\nnop\nnop\nnop\n");pass&=report(6);
 CASE(5,"nop\nnop\nnop\nnop\nnop\n");pass&=report(5);
 CASE(4,"nop\nnop\nnop\nnop\n");pass&=report(4);
 CASE(3,"nop\nnop\nnop\n");pass&=report(3);
 CASE(2,"nop\nnop\n");pass&=report(2);
 CASE(1,"nop\n");pass&=report(1);
 CASE(0,"");pass&=report(0);
 if(!pass){put("[LOAD-TARGET-SPACING] FAIL\n");finish(1);}put("[LOAD-TARGET-SPACING] PASS\n");finish(0);}
