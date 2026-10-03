typedef unsigned long u64;
static volatile u64 words[5] __attribute__((aligned(64))) = {2,2,2,2,2};
static volatile u64 outputs[5];
static inline long sys(long n,long a0,long a1,long a2){register long x10 __asm__("a0")=a0,x11 __asm__("a1")=a1,x12 __asm__("a2")=a2,x17 __asm__("a7")=n;__asm__ volatile("ecall":"+r"(x10):"r"(x11),"r"(x12),"r"(x17):"memory");return x10;}
static void put(const char*s){u64 n=0;while(s[n])++n;(void)sys(64,1,(long)s,n);}
static void number(u64 n){char b[21];unsigned i=20;b[i]=0;do{b[--i]='0'+n%10;n/=10;}while(n);put(b+i);}
static __attribute__((noreturn)) void finish(long c){(void)sys(93,c,0,0);__builtin_unreachable();}
#define CASE(index,nops) do { volatile u64 *p=&words[index], *o=&outputs[index]; u64 one=1; \
 __asm__ volatile(".option push\n.option norvc\namoswap.d.aqrl t0,%2,(%0)\n" nops "ctz t0,t0\nsd t0,0(%1)\n.option pop\n" : : "r"(p),"r"(o),"r"(one):"t0","memory"); } while(0)
void _start(void){
 CASE(0,""); CASE(1,"nop\n"); CASE(2,"nop\nnop\n"); CASE(3,"nop\nnop\nnop\n"); CASE(4,"nop\nnop\nnop\nnop\n");
 for(unsigned i=0;i<5;++i){put("AMO_CTZ nops/output/word: ");number(i);put(" ");number(outputs[i]);put(" ");number(words[i]);put("\n");}
 for(unsigned i=0;i<5;++i) if(outputs[i]!=1||words[i]!=1){put("[LINUX-AMO-PROBE] FAIL\n");finish(1);}
 put("[LINUX-AMO-PROBE] PASS\n");finish(0);
}
