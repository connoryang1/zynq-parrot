#include "Vmaintenance.h"
#include "verilated.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>
int main(int argc,char **argv) {
  VerilatedContext context;context.commandArgs(argc,argv);Vmaintenance dut{&context};
  constexpr unsigned opcodes[]={0,1,2,3,4,5,6,7,8,9,11,12,13};
  uint64_t endpoints=0,accepted=0,refused=0;
  for(unsigned state=0;state<23;state++)for(unsigned opcode:opcodes)
    for(unsigned install=0;install<10;install++)for(unsigned flags=0;flags<512;flags++) {
      dut.state_i=state;dut.opcode_i=opcode;dut.install_i=install;dut.flags_i=flags;dut.eval();
      bool maintenance=bool(flags&1)&&(opcode==6||opcode==7||opcode==8||opcode==11||opcode==12);
      for(unsigned variant=0;variant<16;variant++) {
        if((variant&1)&&((variant>>2)&1))continue;
        unsigned before=(dut.before_yumi_o>>variant)&1,after=(dut.after_yumi_o>>variant)&1;
        unsigned old_m=(dut.before_m_o>>variant)&1,new_m=(dut.after_m_o>>variant)&1;
        unsigned expected=(variant&1)&&maintenance&&after;
        if(before!=after||old_m!=new_m||new_m!=expected) {
          std::cerr<<"state="<<state<<" opcode="<<opcode<<" install="<<install<<" flags="<<flags
                   <<" variant="<<variant<<" yumi="<<before<<'/'<<after<<" M="<<old_m<<'/'<<new_m<<'\n';
          throw std::runtime_error("actual before/after UCE endpoint equivalence failed");
        }
        endpoints++;accepted+=new_m;refused+=bool((variant&1)&&maintenance&&!new_m);
      }
    }
  if(endpoints!=UINT64_C(18370560)||!accepted||!refused)throw std::runtime_error("incomplete exhaustive endpoints");
  dut.final();std::cout<<"[UCE-MAINTENANCE] PASS endpoints="<<endpoints<<" accepted="<<accepted
                      <<" refused="<<refused<<" final_yumi_unchanged=1 same_cycle_clear=1\n";
}
