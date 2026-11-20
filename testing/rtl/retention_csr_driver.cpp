#include "Vretention_csr.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>
void need(bool b,const char*s) {if(!b)throw std::runtime_error(s);}
int main() {
 VerilatedContext ctx; ctx.traceEverOn(true); Vretention_csr d{&ctx};
 VerilatedFstC t; d.trace(&t,99);t.open("retention-csr.fst");
 auto low=[&]{d.clk_i=0;d.eval();};
 auto step=[&]{low();ctx.timeInc(5);t.dump(ctx.time());d.clk_i=1;d.eval();ctx.timeInc(5);t.dump(ctx.time());};
 try {
 d.reset_i=1;step();step();d.reset_i=0;d.csr_addr_i=0x5c1;step();
 need(d.read_data_o==UINT64_C(0x8000000000000000),"reset capability/readback");
 // Current/reading bank deliberately differs from the retiring command bank.
 d.current_thread_i=d.read_thread_i=0;d.retire_thread_i=1;
 d.write_i=d.instret_i=1;d.payload_i=2;low();
 need(d.command_o&&d.mode_o==2,"retiring bank command not routed");step();
 d.write_i=0;low();need((d.read_data_o&3)==2,"other bank lacks global status");
 d.current_thread_i=d.read_thread_i=1;low();need((d.read_data_o&3)==2,"bank switch reset global policy");
 // No architectural retirement and context-switch packets cannot command it.
 d.write_i=1;d.instret_i=0;low();need(!d.command_o,"unretired command emitted");
 d.instret_i=1;d.ctxtsw_i=1;low();need(!d.command_o,"context-switch command emitted");
 d.ctxtsw_i=d.write_i=0;
 // Restore privilege through the real per-context CSR image, not hierarchy force.
 for(unsigned priv: {3u,1u,0u}) {
   d.retire_thread_i=d.current_thread_i=d.read_thread_i=1;
   d.restore_priv_i=priv;d.restore_i=1;step();d.restore_i=0;step();
   for(unsigned wr=0;wr<2;++wr) {
     d.decode_write_i=wr;low();need(bool(d.illegal_o)==(priv==0),"5c1 decoder S/U privilege");
   }
   d.payload_i=priv==1?1:0;d.write_i=d.instret_i=1;low();
   need(bool(d.command_o)==(priv!=0),"5c1 retirement privilege gate");step();d.write_i=0;
 }
 d.final();t.close();
 std::cout<<"[RETENTION-CSR] PASS: shared status, retirement bank, instret/context gates, S/M allow and U read/write denial\n";
 }catch(const std::exception&e){d.final();t.close();std::cerr<<"[RETENTION-CSR] FAIL: "<<e.what()<<'\n';return 1;}
}
