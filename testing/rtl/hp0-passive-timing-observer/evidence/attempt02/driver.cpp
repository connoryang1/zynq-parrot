#include "Vhp0_observer_tb_top.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <array>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using Record=std::array<uint32_t,8>;
static void need(bool ok,const std::string &s){if(!ok)throw std::runtime_error(s);}
struct Input {
 bool ar=false,r=false,ready=true,last=false,aw=false,w=false,wl=false,b=false,freeze=false;
 uint64_t addr=0x80001000;unsigned id=3,rid=3,len=0,size=3,burst=1,resp=0;
 bool rd=false,take=true;unsigned index=0;
};
class Sim {
 std::unique_ptr<VerilatedContext> ctx;
 std::unique_ptr<Vhp0_observer_tb_top> t;
 std::unique_ptr<VerilatedFstC> fst;
 public:
 uint64_t cycle=0;unsigned cases=0;bool small=false;
 Sim(const char *path):ctx(new VerilatedContext),t(),fst(new VerilatedFstC){
  ctx->traceEverOn(true);ctx->randReset(2);t.reset(new Vhp0_observer_tb_top(ctx.get()));
  t->trace(fst.get(),99);fst->open(path);t->clk_i=0;t->reset_i=1;
 }
 ~Sim(){t->final();fst->close();}
 Vhp0_observer_tb_top &dut(){return *t;}
 void step(const Input &x=Input{}){
  t->small_i=small;t->arvalid_i=x.ar;t->arready_i=1;t->araddr_i=x.addr;t->arid_i=x.id;t->arlen_i=x.len;t->arsize_i=x.size;t->arburst_i=x.burst;
  t->rvalid_i=x.r;t->rready_i=x.ready;t->rlast_i=x.last;t->rid_i=x.rid;t->rresp_i=x.resp;
  t->awvalid_i=x.aw;t->awready_i=1;t->wvalid_i=x.w;t->wready_i=1;t->wlast_i=x.wl;t->bvalid_i=x.b;t->bready_i=1;
  t->freeze_i=x.freeze;t->rd_v_i=x.rd;t->rd_index_i=x.index;t->rd_resp_ready_i=x.take;
  t->clk_i=0;t->eval();fst->dump(ctx->time());ctx->timeInc(1);
  t->clk_i=1;t->eval();fst->dump(ctx->time());ctx->timeInc(1);
  t->clk_i=0;t->eval();fst->dump(ctx->time());ctx->timeInc(1);
  if(t->reset_i)cycle=0;else ++cycle;
 }
 void reset(bool shortened=false){small=shortened;t->reset_i=1;step();step();t->reset_i=0;need(!t->rd_resp_v_o,"reset response");}
 void until(uint64_t n){while(cycle<n)step();}
 void ar(uint64_t addr=0x80001000,unsigned len=0,unsigned id=3){Input x;x.ar=true;x.addr=addr;x.len=len;x.id=id;step(x);}
 void beat(bool last=true,unsigned rid=3,unsigned resp=0,bool ready=true){Input x;x.r=true;x.last=last;x.rid=rid;x.resp=resp;x.ready=ready;step(x);}
 void freeze(){Input x;x.freeze=true;step(x);for(int n=0;!t->frozen_o&&n<4;++n)step(x);need(t->frozen_o,"bounded freeze");}
 uint32_t word(unsigned index,bool hold=false){
  need(t->frozen_o&&t->rd_ready_o,"read only frozen/ready");Input x;x.rd=true;x.index=index;x.take=false;step(x);
  need(!t->rd_resp_v_o,"synchronous RAM cannot reply on acceptance edge");
  x.rd=false;step(x);need(t->rd_resp_v_o&&t->rd_resp_index_o==index,"ready+exact echoed index");
  uint32_t value=t->rd_resp_data_o;
  if(hold){for(int n=0;n<3;++n){x.index=index^127;x.rd=true;step(x);need(t->rd_resp_v_o&&!t->rd_ready_o&&t->rd_resp_index_o==index&&t->rd_resp_data_o==value,"held response/index stability");}}
  x.rd=false;x.take=true;step(x);need(!t->rd_resp_v_o,"response consumption");return value;
 }
 Record record(unsigned slot,bool hold=false){Record r;for(unsigned w=0;w<8;++w)r[w]=word(slot*8+w,hold&&w==0);return r;}
 void count(unsigned ar_n,unsigned ignored,unsigned records,unsigned valid,unsigned ptr){
  need(t->ar_count_o==ar_n&&t->ignored_ar_count_o==ignored&&t->record_total_o==records&&t->record_count_o==(records<16?records:16)&&t->valid_count_o==valid&&t->write_pointer_o==ptr,"coverage counters/ring index");
 }
 void done(const std::string &s){++cases;std::cout<<"CASE PASS "<<s<<"\n";}
};
static Record expected(uint32_t address,uint32_t cycle,unsigned len,unsigned seq,unsigned fo,unsigned fa,unsigned lo,unsigned la,unsigned stalls=0,unsigned flags=0,unsigned id=3,unsigned resp=0,bool valid=true,unsigned peak=1){
 uint32_t meta=id|(len<<6)|(3U<<14)|(1U<<17)|(unsigned(valid)<<19)|(15U<<20)|(resp<<24)|(1U<<28);
 return {address,cycle,fo|(fa<<16),lo|(la<<16),meta,(len+1)|(stalls<<16),flags|(peak<<16),seq};
}
static void expect_record(const Record&a,const Record&b,const std::string&why){for(unsigned n=0;n<8;++n)need(a[n]==b[n],why+" word"+std::to_string(n)+" got"+std::to_string(a[n])+" expected"+std::to_string(b[n]));}
static bool valid(const Record&r){return (r[4]>>19)&1;}
static void bad(const Record&r,unsigned flag,const std::string&s){need(!valid(r)&&(r[6]&flag)==flag,s+" explicit invalid flags");}

int main(int argc,char **argv){
 try{
  need(argc==2,"FST path argument");Sim s(argv[1]);
  for(unsigned latency:{1U,40U,200U}){
   s.reset();s.ar();s.until(latency);s.beat();s.freeze();s.count(1,0,1,1,1);
   expect_record(s.record(0,true),expected(0x80001000,0,0,1,latency,latency,latency,latency),"fixed latency");need(s.dut().errors_o==0,"clean fixed-latency status");s.done("latency"+std::to_string(latency));
  }
  s.reset();s.ar(0x80002000,7);s.until(40);for(unsigned n=0;n<8;++n)s.beat(n==7);s.freeze();
  expect_record(s.record(0),expected(0x80002000,0,7,1,40,40,47,47),"8beat onecycle bandwidth");s.done("eightbeats-bandwidth1");
  s.reset();s.ar(0x80003000,1);s.until(40);for(int n=0;n<3;++n)s.beat(false,3,0,false);s.beat(false);s.until(50);for(int n=0;n<2;++n)s.beat(true,3,0,false);s.beat();s.freeze();
  expect_record(s.record(0),expected(0x80003000,0,1,1,40,43,50,52,5),"offered/accepted with stalls");s.done("backpressure-offered-accepted");
  s.reset();Input x;x.ar=x.r=x.last=true;s.step(x);s.freeze();expect_record(s.record(0),expected(0x80001000,0,0,1,0,0,0,0),"zero latency");s.done("zero-latency");
  for(unsigned len:{0U,2U,15U,255U}){
   s.reset();s.ar(0x80004000,len);for(unsigned n=0;n<=len;++n)s.beat(n==len);s.freeze();expect_record(s.record(0),expected(0x80004000,0,len,1,1,1,len+1,len+1),"LEN");s.done("len"+std::to_string(len));
  }
  s.reset();s.ar();x=Input{};x.ar=x.r=x.last=true;x.addr=0x80005000;x.id=4;s.step(x);s.beat(true,4);s.freeze();s.count(2,0,2,2,2);
  expect_record(s.record(0),expected(0x80001000,0,0,1,1,1,1,1),"old completion");expect_record(s.record(1),expected(0x80005000,1,0,2,1,1,1,1,0,0,4),"samecycle new AR");s.done("completion-plus-newAR");
  s.reset();s.ar();s.ar(0x80006000,0,4);s.beat();need(s.dut().read_outstanding_o==1&&s.dut().record_count_o==0,"overlap waits full drain");s.beat(true,4);s.ar(0x80007000);s.beat();s.freeze();s.count(3,1,2,1,2);
  bad(s.record(0),1,"read overlap");expect_record(s.record(1),expected(0x80007000,4,0,3,1,1,1,1),"rearm after drain");s.done("overlap-invalid-and-sequence-gap");
  for(unsigned which=0;which<3;++which){
   s.reset();s.ar(0x80001000,which==2?1:0);s.beat(true,which==0?4:3,which==1?2:0);s.freeze();auto r=s.record(0);bad(r,1U<<(which+1),"RID/RRESP/LEN");s.done("malformed"+std::to_string(which));
  }
  // Missing last at the declared final beat is invalid even if a later last drains.
  s.reset();s.ar();s.beat(false);s.beat();s.freeze();bad(s.record(0),8,"late RLAST");s.done("late-RLAST");
  // EXOKAY is a successful AXI response, retained in metadata, not an RRESP error.
  s.reset();s.ar();s.beat(true,3,1);s.freeze();expect_record(s.record(0),expected(0x80001000,0,0,1,1,1,1,1,0,0,3,1),"EXOKAY");s.done("EXOKAY-success");
  // W-before-AW and both completion transitions are legal: separate ledgers.
  s.reset();x=Input{};x.w=x.wl=true;s.step(x);s.ar();x=Input{};x.aw=true;s.step(x);x=Input{};x.r=x.last=x.b=true;s.step(x);s.freeze();
  expect_record(s.record(0),expected(0x80001000,1,0,1,2,2,2,2,0,0x400),"write-overlap");need(s.dut().errors_o==0,"legal W-before-AW");s.done("W-before-AW-read-overlap");
  s.reset();x=Input{};x.ar=x.r=x.last=x.aw=x.w=x.wl=x.b=true;s.step(x);s.freeze();expect_record(s.record(0),expected(0x80001000,0,0,1,0,0,0,0,0,0x400),"samecycle AW-W-B");need(s.dut().errors_o==0,"samecycle write transition");s.done("samecycle-write-ledgers");
  s.reset();s.ar();x=Input{};x.w=true;s.step(x);s.beat();x=Input{};x.freeze=true;s.step(x);need(!s.dut().frozen_o,"partial W blocks freeze");x=Input{};x.aw=x.w=x.wl=x.b=true;s.step(x);s.freeze();need(s.dut().errors_o==0,"partial W legal completion");need(s.record(0)[6]&0x400,"partial W overlap flag");s.done("partial-W-drain");
  s.reset();for(unsigned n=0;n<21;++n){s.ar(0x80010000+64*n);s.beat();}s.freeze();s.count(21,0,21,16,5);
  for(unsigned seq=6;seq<=21;++seq)expect_record(s.record((seq-1)%16),expected(0x80010000+64*(seq-1),2*(seq-1),0,seq,1,1,1,1),"ring newest16");s.done("ring-wrap-last16");
  s.reset(true);s.until(253);s.ar();s.until(258);s.beat();s.freeze();auto r=s.record(0);expect_record(r,expected(0x80001000,253,0,1,5,5,5,5,0,0x80),"short cycle wrap");need(s.dut().errors_o==0,"free cycle wrap is not protocol error");s.done("short-cross-cycle-wrap-valid");
  s.reset(true);s.ar();s.until(64);s.beat();s.freeze();bad(s.record(0),0x10,"age overflow");s.done("elapsed-age-overflow");
  s.reset(true);s.ar(0x80001000,7);for(unsigned n=0;n<8;++n)s.beat(n==7);s.freeze();bad(s.record(0),0x20,"beat overflow");s.done("beat-overflow");
  s.reset(true);s.ar();for(unsigned n=0;n<8;++n)s.beat(true,3,0,false);s.beat();s.freeze();bad(s.record(0),0x40,"stall overflow");s.done("stall-overflow");
  s.reset(true);s.ar(0x100001000ULL);s.beat();s.freeze();bad(s.record(0),0x100,"address width");s.done("address-width-overflow");
  s.reset(true);s.ar(0x80001000,0,0x83);s.beat(true,0x83);s.freeze();bad(s.record(0),0x100,"ID width");s.done("ID-width-overflow");
  s.reset(true);for(unsigned n=0;n<32;++n){s.ar();s.beat();}s.freeze();r=s.record(15);bad(r,0x2000,"sequence overflow");need(s.dut().ar_count_o==31&&s.dut().errors_o&(1<<4),"sequence saturates with sticky error");s.done("sequence-overflow");
  s.reset(true);for(unsigned n=0;n<8;++n)s.ar(0x80001000+64*n,0,n);need(s.dut().errors_o&2,"read ledger overflow sticky");need(s.dut().status_o&(1<<7),"read ledger poisoned");need(s.dut().record_count_o==1&&s.dut().valid_count_o==0,"overflow window explicitly invalid");s.done("outstanding-overflow");
  s.reset();s.beat();need(s.dut().errors_o&1,"read underflow");need(s.dut().busy_o,"unknown read ledger cannot fake drained");s.done("read-underflow");
  s.reset();x=Input{};x.b=true;s.step(x);need(s.dut().errors_o&4,"write B underflow");s.done("write-underflow");
  s.reset(true);for(unsigned n=0;n<8;++n){x=Input{};x.aw=true;s.step(x);}need(s.dut().errors_o&8,"write outstanding overflow");s.done("write-overflow");
  // Capture the final response while freeze/read request both arrive. No old RAM reply.
  s.reset();s.ar(0x800abc00);x=Input{};x.r=x.last=x.freeze=x.rd=true;x.index=0;x.take=false;s.step(x);need(!s.dut().frozen_o&&!s.dut().rd_resp_v_o,"freeze+RLAST not ready");
  x.r=x.last=false;s.step(x);need(s.dut().frozen_o&&!s.dut().rd_resp_v_o,"one full extra edge before read acceptance");
  s.step(x);need(!s.dut().rd_resp_v_o,"synchronous read latency");x.rd=false;s.step(x);need(s.dut().rd_resp_v_o&&s.dut().rd_resp_data_o==0x800abc00&&s.dut().rd_resp_index_o==0,"new final record read/echo");x.take=true;s.step(x);s.done("freeze-last-write-read-guard");
  s.reset();s.ar();x=Input{};x.ar=x.r=x.last=x.freeze=true;x.addr=0x80002000;x.id=4;s.step(x);need(!s.dut().frozen_o&&s.dut().read_outstanding_o==1,"freeze completion+newAR waits ignored request");s.beat(true,4);s.freeze();s.count(2,1,1,0,1);bad(s.record(0),0x1000,"AR during freeze request");need(s.dut().errors_o&(1<<5),"after freeze request sticky");s.done("freeze-plus-newAR");
  s.reset();s.ar();s.beat();s.freeze();Record before=s.record(0);s.ar(0x80002000);s.beat();need(s.dut().ar_count_o==2&&s.dut().ignored_ar_count_o==1&&s.dut().record_total_o==1,"frozen traffic coverage");expect_record(s.record(0),before,"frozen record immutable");need(s.dut().errors_o&(1<<5),"traffic after frozen sticky");s.done("post-freeze-traffic");
  s.reset();s.freeze();s.count(0,0,0,0,0);for(unsigned n=0;n<8;++n)need(s.word(n)==0,"reset invalidates old payload without resetting RAM");s.done("reset-and-empty-read");
  need(s.dut().version_o==0x48503001,"version");std::cout<<"HP0_PASSIVE_TIMING_OBSERVER PASS cases="<<s.cases<<" records8x32 ring16 trace=1\n";return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}
}
