#include "Vdcache_mutation.h"
#include "verilated.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>
namespace {
void require(bool v,const char* message){if(!v)throw std::runtime_error(message);}
class Test {
 VerilatedContext context;Vdcache_mutation dut{&context};
 unsigned mutations=0,maintenance=0,results=0,requests=0;uint64_t result=0;
 void step(){
  dut.clk_i=0;dut.eval();context.timeInc(5);
  if(dut.result_v_o){results++;result=dut.result_data_o;}
  if(dut.request_o)requests++;
  dut.clk_i=1;dut.eval();context.timeInc(5);
  if(!dut.reset_i&&dut.mutation_o){mutations++;require(dut.mutation_addr_o==UINT64_C(0x80000000),"accepted mutation physical address lost");}
  if(!dut.reset_i&&dut.maintenance_o)maintenance++;
 }
 void cycles(unsigned n){while(n--)step();}
 void engine(unsigned cmd,uint64_t addr,unsigned word=0){
  dut.engine_i=cmd;dut.engine_addr_i=addr;dut.engine_word_i=word;dut.engine_data_i=7+word;
  for(unsigned n=0;n<100;n++){dut.clk_i=0;dut.eval();if(dut.engine_yumi_o){step();dut.engine_i=0;step();return;}step();}
  throw std::runtime_error("cache engine fixture failed to initialize");
 }
 void op(unsigned opcode,unsigned expected_mutations,bool uc=false){
  unsigned before=mutations;dut.opcode_i=opcode;dut.addr_i=UINT64_C(0x80000000);dut.uncached_i=uc;
  dut.v_i=1;step();dut.v_i=0;cycles(7);
  require(mutations==before+expected_mutations,"actual store/AMO/SC accepted-mutation mismatch");
 }
public:
 void run(){
  dut.reset_i=1;cycles(4);dut.reset_i=0;cycles(3);
  for(unsigned s=0;s<4;s++){engine(1,UINT64_C(0x80000000)+64*s);engine(4,UINT64_C(0x80000000)+64*s);}
  for(unsigned w=0;w<8;w++)engine(3,UINT64_C(0x80000000)+8*w,w);
  engine(2,UINT64_C(0x80000000));
  op(3,0);require(results&&result==7&&requests==0,"real L1 fixture load did not hit");
  op(14,0);require(result==1,"SC without reservation did not fail");
  op(11,1); // SD
  for(unsigned opcode=16;opcode<=33;opcode++)op(opcode,1); // All word/dword AMOs
  op(13,0);op(14,1);require(result==0,"LR/successful SC path failed");
  op(14,0);require(result==1,"second SC incorrectly retained reservation");
  op(11,1,true); // Accepted uncached store aliases same physical DRAM line.
  unsigned before=maintenance;op(61,0);require(maintenance==before+1,"accepted maintenance not registered");
  dut.engine_complete_i=1;step();dut.engine_complete_i=0;cycles(3);
  std::cout<<"[DCACHE-MUTATION] PASS: real load/store/all18AMO/LR-successfulSC/failedSC/UC/maintenance event paths\n";
 }
};
}
int main(){try{Test t;t.run();return 0;}catch(const std::exception&e){std::cerr<<"[DCACHE-MUTATION] FAIL: "<<e.what()<<'\n';return 1;}}
