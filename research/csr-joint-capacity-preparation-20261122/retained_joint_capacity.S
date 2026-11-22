/* Same analytic payloads/192-byte guarded code stride. All ABI saves precede
 * population. No store/fence/control write after population begins. Target
 * functions use only a0 and ra; no stack or pointer table is used in the body.
 */
.section .text.retained_capacity_joint,"ax",@progbits
.option push
.option norvc
.balign 64
.global retained_joint_capacity_region
.type retained_joint_capacity_region,@function
retained_joint_capacity_region:
  addi sp,sp,-112
  sd s0,0(sp)
  sd s1,8(sp)
  sd s2,16(sp)
  sd s3,24(sp)
  sd s4,32(sp)
  sd s5,40(sp)
  sd s6,48(sp)
  sd s7,56(sp)
  sd s8,64(sp)
  sd s9,72(sp)
  sd s10,80(sp)
  sd s11,88(sp)
  sd ra,96(sp)
  mv s0,a0
  mv s1,a1
  mv s2,a2
  mv s3,a3
  addi s4,a4,-1
  mv s5,a5
  fence rw,rw
.global retained_capacity_i_populate_begin
retained_capacity_i_populate_begin:
  nop
  li s6,0
.Ljoint_ipopulate:
  not t0,s4
  and t0,t0,s6
  li t1,0xaaaaaaaaaaaaaaab
  mul t1,t1,s6
  and t1,t1,s4
  or t0,t0,t1
  li t1,192
  mul t0,t0,t1
  add s7,s1,t0
  li t0,10000
.Ljoint_iready:
  csrr t1,0x7c0
  csrr t2,0x5c2
  andi t3,t2,15
  bne t3,s5,.Ljoint_control_error
  srli t3,t2,63
  beqz t3,.Ljoint_control_error
  andi t3,t2,768
  bnez t3,.Ljoint_iready_next
  andi t3,t1,1
  bnez t3,.Ljoint_isubmit
.Ljoint_iready_next:
  addi t0,t0,-1
  bnez t0,.Ljoint_iready
  li a0,1
  j .Ljoint_out
.Ljoint_isubmit:
  csrw 0x7c0,s7
  li t0,10000
  li s11,0
.Ljoint_icomplete:
  csrr t1,0x7c0
  csrr t2,0x5c2
  andi t3,t2,15
  bne t3,s5,.Ljoint_control_error
  andi t3,t2,256
  or s11,s11,t3
  andi t3,t2,768
  bnez t3,.Ljoint_icomplete_next
  andi t3,t1,1
  beqz t3,.Ljoint_icomplete_next
  bnez s11,.Ljoint_ipublished
.Ljoint_icomplete_next:
  addi t0,t0,-1
  bnez t0,.Ljoint_icomplete
  li a0,2
  j .Ljoint_out
.Ljoint_ipublished:
  addi s6,s6,1
  bltu s6,s2,.Ljoint_ipopulate
.global retained_capacity_i_populated
retained_capacity_i_populated:
  nop
.global retained_capacity_d_populate_begin
retained_capacity_d_populate_begin:
  nop
  mv s7,s0
  li s6,0
.Ljoint_dpopulate:
  li t0,10000
.Ljoint_dready:
  csrr t1,0x9c0
  csrr t2,0x5c2
  andi t3,t2,15
  bne t3,s5,.Ljoint_control_error
  srli t3,t2,63
  beqz t3,.Ljoint_control_error
  andi t3,t2,512
  bnez t3,.Ljoint_dready_next
  andi t3,t1,1
  bnez t3,.Ljoint_dsubmit
.Ljoint_dready_next:
  addi t0,t0,-1
  bnez t0,.Ljoint_dready
  li a0,3
  j .Ljoint_out
.Ljoint_dsubmit:
  csrw 0x9c0,s7
  li t0,10000
  li s11,0
.Ljoint_dcomplete:
  csrr t1,0x9c0
  csrr t2,0x5c2
  andi t3,t2,15
  bne t3,s5,.Ljoint_control_error
  andi t3,t2,512
  or s11,s11,t3
  andi t4,t1,1
  bnez t4,.Ljoint_dpreview_idle
  ori s11,s11,512
.Ljoint_dpreview_idle:
  bnez t3,.Ljoint_dcomplete_next
  beqz t4,.Ljoint_dcomplete_next
  bnez s11,.Ljoint_dpublished
.Ljoint_dcomplete_next:
  addi t0,t0,-1
  bnez t0,.Ljoint_dcomplete
  li a0,4
  j .Ljoint_out
.Ljoint_dpublished:
  addi s7,s7,64
  addi s6,s6,1
  bltu s6,s3,.Ljoint_dpopulate
.global retained_capacity_joint_populated
retained_capacity_joint_populated:
  nop
.global retained_capacity_i_verify_begin
retained_capacity_i_verify_begin:
  nop
  li s6,0
.Ljoint_iverify:
  not t0,s4
  and t0,t0,s6
  li t1,0xaaaaaaaaaaaaaaab
  mul t1,t1,s6
  and t1,t1,s4
  or s9,t0,t1
  mv s8,s9
  li t0,1
.Ljoint_expected:
  slli s8,s8,6
  addi t1,s9,1
  slli t2,t0,1
  addi t2,t2,1
  mul t1,t1,t2
  li t2,37
  mul t2,t2,t0
  add t1,t1,t2
  andi t1,t1,2047
  xor s8,s8,t1
  addi t0,t0,1
  li t1,8
  bltu t0,t1,.Ljoint_expected
  li t0,192
  mul t0,s9,t0
  add s7,s1,t0
.global retained_capacity_joint_call
retained_capacity_joint_call:
  jalr ra,0(s7)
  bne a0,s8,.Ljoint_code_error
  addi s6,s6,1
  bltu s6,s2,.Ljoint_iverify
.global retained_capacity_i_verified
retained_capacity_i_verified:
  nop
.global retained_capacity_d_verify_begin
retained_capacity_d_verify_begin:
  nop
  mv s7,s0
  li s6,0
  li s11,0x94d049bb133111eb
.Ljoint_dline:
  addi s8,s6,1
  li t0,0xd1b54a32d192ed03
  mul s8,s8,t0
  li t0,0x9e3779b97f4a7c15
  xor s8,s8,t0
  li s9,3
  li s10,8
.Ljoint_dword:
  slli t0,s9,3
  add t1,s7,t0
  ld t2,0(t1)
  addi t3,s9,1
  mul t3,t3,s11
  xor t3,t3,s8
  bne t2,t3,.Ljoint_data_error
  addi s9,s9,1
  andi s9,s9,7
  addi s10,s10,-1
  bnez s10,.Ljoint_dword
  addi s7,s7,64
  addi s6,s6,1
  bltu s6,s3,.Ljoint_dline
.global retained_capacity_d_verified
retained_capacity_d_verified:
  nop
.global retained_capacity_joint_verified
retained_capacity_joint_verified:
  nop
  li a0,0
  j .Ljoint_out
.Ljoint_control_error:
  li a0,5
  j .Ljoint_out
.Ljoint_code_error:
  li a0,6
  j .Ljoint_out
.Ljoint_data_error:
  li a0,7
.Ljoint_out:
  ld s0,0(sp)
  ld s1,8(sp)
  ld s2,16(sp)
  ld s3,24(sp)
  ld s4,32(sp)
  ld s5,40(sp)
  ld s6,48(sp)
  ld s7,56(sp)
  ld s8,64(sp)
  ld s9,72(sp)
  ld s10,80(sp)
  ld s11,88(sp)
  ld ra,96(sp)
  addi sp,sp,112
  ret
.size retained_joint_capacity_region,.-retained_joint_capacity_region
.option pop
#include "capacity_targets.inc"
