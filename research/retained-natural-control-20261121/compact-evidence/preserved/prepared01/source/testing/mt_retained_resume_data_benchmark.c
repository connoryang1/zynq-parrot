/* New checked lifecycle dataset derived from the archived F35 lookup ring.
 * Four private32KiB lookup tables, four logical actors/two resident slots.
 * CSR0x5c2 controls retention only; no advisory/address-table interface.
 * Simulation diagnostic, not Linux/FPGA application performance.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"
#include "../linux-tests/resume_workload.h"
#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "requires two resident slots and four logical actors"
#endif
#if defined(BP_RESUME_ZLIB) && BP_RESUME_ZLIB
#error "plain lookup only"
#endif

enum { actors=4, kib=32, warm_rounds=8, timed_rounds=8,
       total_rounds=16, stack_words=512, poll_limit=65536 };
/* Exactly one initialized, file-backed word is changed by offline NBF patch. */
volatile uint64_t resume_retained_control __attribute__((used,aligned(8)))=UINT64_MAX;
static struct resume_workload work[actors];
static uint64_t stacks[actors-1][stack_words];
struct request_phase { uint64_t begin,end; };
static volatile struct request_phase phases[actors][total_rounds];
static volatile uint64_t sums[actors],completed[actors],parked[actors];
struct observation { uint64_t base,bytes,runs,sum,seed; };
static struct observation observed[actors];
static uint64_t whole_begin,whole_end,warm_begin,timed_begin,timed_end;
static uint64_t status_initial,status_ready,status_checked,status_final;
static uint64_t start_polls,end_polls,control_begin,checks_done,teardown_begin;
#define CYCLE_AT(label,output) \
  __asm__ volatile(".global " #label "\n" #label ":\ncsrr %0, 0xcc0" \
                   : "=r"(output) : : "memory")
static uint64_t seed_for(unsigned actor) {
  return UINT64_C(0x95cba137)+actor*UINT64_C(0x9e3779b9);
}
static void __attribute__((noreturn,noinline)) fail(char *why) {
  bp_print_string("[BSG-FAIL] retained lifecycle: ");
  bp_print_string(why);bp_print_string("\n");bp_finish(1);for(;;);
}
static inline uint64_t status(void) {
  uint64_t v;__asm__ volatile("csrr %0,0x5c2":"=r"(v)::"memory");return v;
}
static inline void control(uint64_t mode) {
  __asm__ volatile("csrw 0x5c2,%0"::"r"(mode):"memory");
}
static int geometry(uint64_t v) {
  const uint64_t mask=(UINT64_C(1)<<63)|(UINT64_C(3)<<56)
    |(UINT64_C(0xff)<<48)|(UINT64_C(0xffffffff)<<16)|UINT64_C(0xf0f);
  return !(v&~mask) && (v>>63)==1 && ((v>>56)&3)==3
    && ((v>>48)&255)==8 && ((v>>32)&65535)==1280
    && ((v>>16)&65535)==1280;
}
static uint64_t wait_idle(uint64_t mode,uint64_t *polls) {
  for(uint64_t n=1;n<=poll_limit;++n) {
    uint64_t v=status();
    if(!geometry(v)||(v&15)!=mode) fail("capability/control/geometry changed");
    if(!(v&UINT64_C(0x300))) {*polls=n;return v;}
  }
  fail("bounded retained idle poll");
}
static void __attribute__((noinline,noclone)) request(unsigned actor,unsigned epoch) {
  uint64_t begin,end,current;
  __asm__ volatile("csrr %0,0x800":"=r"(current));
  if(current!=actor)fail("logical actor mismatch");
  CYCLE_AT(retained_resume_request_begin,begin);
  uint64_t value=resume_workload_run(&work[actor]);
  CYCLE_AT(retained_resume_request_end,end);
  phases[actor][epoch].begin=begin;phases[actor][epoch].end=end;
  sums[actor]+=value;completed[actor]=epoch+1;
}
static void __attribute__((noinline,noreturn,used)) peer(uint64_t actor) {
  if(actor<1||actor>3)fail("peer argument");
  for(unsigned epoch=0;epoch<total_rounds;++epoch) {
    request((unsigned)actor,epoch);
    /* Last handoff parks the peer; main never resumes it after this point. */
    if(epoch+1==total_rounds)parked[actor]=1;
    if(actor==1)__asm__ volatile("fence rw,rw\ncsrwi 0x800,2":::"memory");
    else if(actor==2)__asm__ volatile("fence rw,rw\ncsrwi 0x800,3":::"memory");
    else __asm__ volatile("fence rw,rw\ncsrwi 0x800,0":::"memory");
  }
  fail("parked peer resumed");
}
static void lap(unsigned epoch) {
  request(0,epoch);__asm__ volatile("fence rw,rw\ncsrwi 0x800,1":::"memory");
}
static void field(char *name,uint64_t value) {bp_print_string(name);bp_hprint_uint64(value);}
int main(void) {
  CYCLE_AT(retained_resume_whole_begin,whole_begin);
  uint64_t mode=resume_retained_control;
  if(mode!=0&&mode!=9&&mode!=6&&mode!=15)fail("invalid mode word");
  status_initial=status();
  if(!geometry(status_initial)||(status_initial&15))fail("initial capability/control/geometry");
  CYCLE_AT(retained_resume_control_begin,control_begin);
  control(mode);status_ready=wait_idle(mode,&start_polls);
  for(unsigned a=0;a<actors;++a)
    if(resume_workload_init(&work[a],"lookup",kib,seed_for(a)))fail("private corpus allocation");
  for(unsigned a=1;a<actors;++a) {
    seed_reg(a,10,a);seed_thread(a,&stacks[a-1][stack_words],(uint64_t)peer);
  }
  CYCLE_AT(retained_resume_warm_begin,warm_begin);
  for(unsigned epoch=0;epoch<warm_rounds;++epoch)lap(epoch);
  CYCLE_AT(retained_resume_timed_begin,timed_begin);
  for(unsigned epoch=warm_rounds;epoch<total_rounds;++epoch)lap(epoch);
  CYCLE_AT(retained_resume_timed_end,timed_end);
  for(unsigned a=0;a<actors;++a) {
    if(work[a].kind!=resume_lookup||work[a].bytes!=kib*1024
       ||work[a].count!=kib*64||work[a].records!=kib*32
       ||work[a].seed!=seed_for(a)||work[a].runs!=total_rounds
       ||completed[a]!=total_rounds||!resume_workload_check_total(&work[a],sums[a]))
      fail("independent16-request checks/metadata");
    if(a&&parked[a]!=1)fail("peer not parked");
    for(unsigned epoch=0;epoch<total_rounds;++epoch) {
      uint64_t begin=phases[a][epoch].begin,end=phases[a][epoch].end;
      if(begin>=end)fail("nonmonotonic request phase");
      if(epoch>=warm_rounds&&(begin<timed_begin||end>timed_end))fail("request outside timed ring");
      if(a&&phases[a-1][epoch].end>=begin)fail("actor ring order");
      if(!a&&epoch&&phases[3][epoch-1].end>=begin)fail("epoch ring order");
    }
    observed[a].base=(uintptr_t)work[a].data;observed[a].bytes=work[a].bytes;
    observed[a].runs=work[a].runs;observed[a].sum=sums[a];observed[a].seed=work[a].seed;
  }
  CYCLE_AT(retained_resume_checks_done,checks_done);
  status_checked=status();
  if(!geometry(status_checked)||(status_checked&15)!=mode)fail("final active policy");
  for(unsigned a=0;a<actors;++a)resume_workload_free(&work[a]);
  for(unsigned a=0;a<actors;++a)
    if(work[a].data||work[a].bytes||work[a].runs)fail("free/zero failed");
  CYCLE_AT(retained_resume_teardown_begin,teardown_begin);
  control(0);status_final=wait_idle(0,&end_polls);
  CYCLE_AT(retained_resume_whole_end,whole_end);
  if(!(whole_begin<warm_begin&&warm_begin<timed_begin&&timed_begin<timed_end
       &&timed_end<whole_end))fail("whole/ring chronology");
  /* All successful-path UART is after complete work, checks, park, free, off/poll. */
  bp_print_string("RETAINED_RESUME_PROTOCOL whole-v1\n");
  bp_print_string("RETAINED_RESUME_CONFIG lookup actors=4 resident=2 kib=32 warm=8 timed=8");field(" mode=",mode);bp_print_string("\n");
  for(unsigned a=0;a<actors;++a) {
    bp_print_string("RETAINED_RESUME_REGION actor=");bp_cprint('0'+a);
    field(" base=",observed[a].base);field(" bytes=",observed[a].bytes);
    field(" runs=",observed[a].runs);field(" sum=",observed[a].sum);bp_print_string("\n");
    if(a) {bp_print_string("RETAINED_RESUME_STACK actor=");bp_cprint('0'+a);
      field(" base=",(uintptr_t)stacks[a-1]);field(" bytes=",sizeof(stacks[0]));bp_print_string("\n");}
  }
  bp_print_string("RETAINED_RESUME_STATUS");field(" initial=",status_initial);
  field(" ready=",status_ready);field(" checked=",status_checked);field(" final=",status_final);
  field(" start_polls=",start_polls);field(" end_polls=",end_polls);bp_print_string("\n");
  bp_print_string("RETAINED_RESUME_PHASES");field(" whole_begin=",whole_begin);field(" whole_end=",whole_end);
  field(" whole_cycles=",whole_end-whole_begin);field(" warm_begin=",warm_begin);
  field(" timed_begin=",timed_begin);field(" timed_end=",timed_end);
  field(" ring_cycles=",timed_end-timed_begin);field(" control_begin=",control_begin);
  field(" checks_done=",checks_done);field(" teardown_begin=",teardown_begin);bp_print_string("\n");
  bp_print_string("[BSG-PASS] checked retained lifecycle lookup whole\n");
  bp_finish(0);for(;;);
}
