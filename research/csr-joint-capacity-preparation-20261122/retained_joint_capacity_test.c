/* One advisory-backed full I+D capacity correctness case; no timing claim. */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include "bp_utils.h"
#ifndef CAP_MAX_LINES
#error "Same maintained generator capacity bounds required"
#endif
#define JOINT_MAGIC UINT64_C(0xc641000000000000)
#define HOT __attribute__((section(".text.retained_capacity_hot"),noinline,noclone))
volatile uint64_t retained_joint_capacity_config __attribute__((used,aligned(8)))=JOINT_MAGIC;
extern unsigned char retained_capacity_data_base[],retained_capacity_code_base[];
extern uint64_t retained_joint_capacity_region(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
static inline uint64_t status(void)
{uint64_t raw;__asm__ volatile("csrr %0,0x5c2":"=r"(raw)::"memory");return raw;}
static inline void control(unsigned mask)
{__asm__ volatile("csrw 0x5c2,%0"::"r"((uint64_t)mask):"memory");}
static HOT __attribute__((noreturn)) void fail(unsigned phase,uint64_t detail)
{
  printf("[BSG-FAIL] retained JOINT capacity phase=%u detail=0x%016" PRIx64 "\n",phase,detail);
  bp_finish(1);__builtin_unreachable();
}
static HOT void wait_all(unsigned mask,unsigned phase)
{
  for(unsigned n=0;n<10000;n++) {
    uint64_t raw=status(),i,d;
    __asm__ volatile("csrr %0,0x7c0\ncsrr %1,0x9c0":"=r"(i),"=r"(d)::"memory");
    if(!(raw>>63)||(raw&15)!=mask)fail(phase,raw);
    if(!(raw&0x300)&&(i&1)&&(d&1))return;
  }
  fail(phase,status());
}
int HOT main(void)
{
  __asm__ volatile("csrci mstatus,8":::"memory");
  uint64_t raw=status();
  if(retained_joint_capacity_config!=JOINT_MAGIC||!(raw>>63)||((raw>>56)&3)!=3||(raw&15))fail(1,raw);
  unsigned log_sets=(raw>>48)&255;
  if(log_sets>15)fail(2,raw);
  unsigned sets=1U<<log_sets,i_lines=(raw>>16)&65535U,d_lines=(raw>>32)&65535U;
  if(!i_lines||!d_lines||i_lines>CAP_MAX_LINES||d_lines>CAP_MAX_LINES||sets>CAP_MAX_SETS
      ||((i_lines+sets-1U)/sets)*sets>CAP_CODE_FUNCTIONS)fail(3,raw);
  control(3);wait_all(3,4); /* Both lookups, both demand-copy bits zero. */
  uint64_t result=retained_joint_capacity_region((uintptr_t)retained_capacity_data_base,
      (uintptr_t)retained_capacity_code_base,i_lines,d_lines,sets,3);
  if(result)fail(10,result);
  wait_all(3,5);control(0);wait_all(0,6);
  printf("RETAINED_JOINT_CAPACITY_CONFIG version=1 i_lines=%u d_lines=%u sets=%u line_bytes=64"
      " data_base=0x%016" PRIxPTR " code_base=0x%016" PRIxPTR " code_stride=192 control=3 copy=0\n",
      i_lines,d_lines,sets,(uintptr_t)retained_capacity_data_base,(uintptr_t)retained_capacity_code_base);
  bp_print_string("[BSG-PASS] retained JOINT capacity checked both full64B payloads completed\n");
  bp_finish(0);return 0;
}
