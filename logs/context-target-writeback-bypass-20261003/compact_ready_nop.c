/*
 * Compact Linux U-mode comparison of register, loaded, and ready-bitmap
 * context targets on the routed dependency-tail candidate.  Each case uses
 * the same 128-round-trip loop and a direct constant-target drain, avoiding
 * the large unrolled stress harness's code-layout and drain interactions.
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

#define PEER(name,setup,sequence) static __attribute__((naked,noinline,noreturn,used,aligned(8))) void name(void){__asm__ volatile( \
 ".option push\n.option norvc\n" setup "li t0,128\n1:\n" sequence \
 "addi t0,t0,-1\nbnez t0,1b\nlla t1,observed\ncsrr t3,0x800\nsd t3,0(t1)\n" \
 "lla t1,complete\nli t3,1\nsd t3,0(t1)\nfence rw,rw\ncsrw 0x800,zero\n2:j 2b\n.option pop\n");}
#define RING(name,setup,sequence) static __attribute__((noinline,aligned(8))) void name(void){__asm__ volatile( \
 ".option push\n.option norvc\n" setup "li t0,128\n1:\n" sequence \
 "addi t0,t0,-1\nbnez t0,1b\n.option pop\n":::"t0","t1","t2","t3","t4","memory");}

PEER(peer_register,"li t4,0\n","csrw 0x800,t4\n")
PEER(peer_loaded,"lla t2,peer_word\n","ld t4,0(t2)\ncsrw 0x800,t4\n")
PEER(peer_bitmap,"lla t2,peer_word\n","ld t4,0(t2)\nctz t4,t4\nnop\ncsrw 0x800,t4\n")
RING(ring_register_1,"li t4,1\n","csrw 0x800,t4\n")
RING(ring_register_2,"li t4,2\n","csrw 0x800,t4\n")
RING(ring_loaded,"lla t2,source_word\n","ld t4,0(t2)\ncsrw 0x800,t4\n")
RING(ring_bitmap,"lla t2,source_word\n","ld t4,0(t2)\nctz t4,t4\nnop\ncsrw 0x800,t4\n")

static int trial(const char *name,u64 target,void(*ring)(void),void(*peer)(void),u64 source_value,u64 peer_value){
 source_word=source_value;peer_word=peer_value;observed=~0UL;complete=0;seed_npc(target,(u64)peer);__asm__ volatile("fence rw,rw":::"memory");
 u64 begin=cycles();ring();__asm__ volatile("csrw 0x800,%0"::"r"(target):"memory");u64 end=cycles();
 put("COMPACT_READY name/target/observed/complete/source/cycles/cycles_x100_per_switch: ");put(name);put(" ");number(target);put(" ");number(observed);put(" ");number(complete);put(" ");number(context());put(" ");number(end-begin);put(" ");number((end-begin)*100/(2*TURNS+2));put("\n");
 return observed==target&&complete==1&&context()==0;
}
void _start(void){if(context()!=0)finish(2);int pass=1;
 pass&=trial("register",1,ring_register_1,peer_register,1,0);
 pass&=trial("register",2,ring_register_2,peer_register,2,0);
 pass&=trial("loaded",1,ring_loaded,peer_loaded,1,0);
 pass&=trial("loaded",2,ring_loaded,peer_loaded,2,0);
 pass&=trial("bitmap",1,ring_bitmap,peer_bitmap,2,1);
 pass&=trial("bitmap",2,ring_bitmap,peer_bitmap,4,1);
 if(!pass){put("[COMPACT-READY-NOP] FAIL\n");finish(1);}put("[COMPACT-READY-NOP] PASS\n");finish(0);}
