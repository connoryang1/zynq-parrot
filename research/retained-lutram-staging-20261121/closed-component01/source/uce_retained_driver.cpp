// Real UCE+retained BRAM transactions. This is functional evidence, not timing.
#include "Vuce_retained.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
void require(bool v,const char* message){if(!v)throw std::runtime_error(message);}
uint64_t payload(uint64_t line,unsigned word){return UINT64_C(0xa55a000000000000)^(line<<8)^word;}
struct Header{unsigned type,size,way,state;uint64_t addr;bool prefetch;};
struct Accepted{bool req,rev,preview;};
class Test {
 VerilatedContext context;
 Vuce_retained dut{&context};
 VerilatedFstC trace;
 unsigned cycles_count=0,mask=0,critical=0,last=0,data_writes=0;
 bool checking=false;
 bool zero_write=false;
 uint64_t expected_addr=0;
 std::vector<Header> reads,writes;
 std::vector<uint64_t> write_words;
 Accepted step(){
  require(++cycles_count<1000000,"global directed cycle bound");
  dut.clk_i=0;dut.eval();context.timeInc(5);trace.dump(context.time());
  Accepted a{bool(dut.req_yumi_o),bool(dut.rev_ready_o),bool(dut.preview_ready_o)};
  if(!dut.reset_i){
   require(!dut.data_v_o||dut.data_opcode_o!=3,"full retained path leaked legacy narrow data packet");
   if(dut.fwd_v_o&&dut.fwd_ready_i){
    Header h{dut.fwd_type_o,dut.fwd_size_o,dut.fwd_way_o,dut.fwd_state_o,dut.fwd_addr_o,bool(dut.fwd_prefetch_o)};
    require(h.size==6,"request is not actual64B transport");
    if(h.type==0)reads.push_back(h);
    else {
     require(h.type==1,"unexpected forward type");
     if(write_words.size()%8==0)writes.push_back(h);
     require(dut.fwd_word_o==(zero_write?0:UINT64_C(0xfedc000000000000)+(write_words.size()%8)),"ordinary write payload corrupted");
     write_words.push_back(dut.fwd_word_o);
    }
   }
   if(dut.data_v_o&&dut.arrays_accept_i&&dut.data_opcode_o==0)++data_writes;
   if(checking&&dut.data_v_o&&dut.arrays_accept_i&&dut.data_opcode_o==0){
    unsigned fill=dut.data_fill_o,index=0;
    require(fill&&!(fill&(fill-1)),"non-one-hot ordinary fill");
    while((1u<<index)!=fill)++index;
    require(!(mask&fill),"duplicate refill beat");
    unsigned word=index*dut.fill_words_o;
    if(dut.data_word_o!=payload(expected_addr&~UINT64_C(63),word)){
     std::cerr<<"data mismatch cycle="<<cycles_count<<" addr="<<std::hex<<expected_addr<<" beat="<<index
       <<" got="<<dut.data_word_o<<" expected="<<payload(expected_addr&~UINT64_C(63),word)<<" packet_addr="<<dut.data_addr_o<<std::dec<<'\n';
     throw std::runtime_error("full-line word corrupted");
    }
    if(dut.fill_words_o==2)require(dut.data_word1_o==payload(expected_addr&~UINT64_C(63),word+1),"second instruction refill word corrupted");
    mask|=fill;
    if(dut.critical_o){++critical;require(index==(((expected_addr>>3)&7)/dut.fill_words_o),"wrong critical word");}
    if(dut.last_o)++last;
   }
  }
  dut.clk_i=1;dut.eval();context.timeInc(5);trace.dump(context.time());return a;
 }
 void cycles(unsigned n){while(n--)step();}
 void idle(){for(unsigned n=0;n<20000;n++){step();if(dut.idle_o&&dut.credits_empty_o)return;}throw std::runtime_error("retained ownership did not drain");}
 void request(uint64_t addr,bool dirty=false,unsigned type=0){
  checking=type==0;expected_addr=addr;mask=critical=last=0;
  dut.req_type_i=type;dut.req_addr_i=addr;dut.req_v_i=1;
  dut.metadata_way_i=3;dut.metadata_dirty_i=dirty;
  bool accepted=false;for(unsigned n=0;n<2000;n++)if(step().req){accepted=true;break;}
  require(accepted,"ordinary request refused indefinitely");dut.req_v_i=0;
  dut.metadata_v_i=1;step();dut.metadata_v_i=0;step();
 }
 Header read(unsigned target){
  for(unsigned n=0;n<2000;n++){if(reads.size()>=target){require(reads.size()==target,"extra read request");return reads.back();}step();}
  throw std::runtime_error("memory read request absent");
 }
 void response(const Header& h,unsigned start=0,unsigned count=8){
  require(!(start%dut.bus_words_o)&&!(count%dut.bus_words_o),"partial response not physical-beat aligned");
  for(unsigned b=start;b<start+count;b+=dut.bus_words_o){
   dut.rev_type_i=h.type;dut.rev_size_i=h.size;dut.rev_addr_i=h.addr;
   dut.rev_way_i=h.way;dut.rev_state_i=h.state;dut.rev_prefetch_i=h.prefetch;
   // This endpoint streams the whole64B transaction from its aligned base;
   // the header retains the separately signalled requested critical offset.
   unsigned logical=b&7;
   dut.rev_word_i=payload(h.addr&~UINT64_C(63),logical);
   dut.rev_word1_i=payload(h.addr&~UINT64_C(63),(logical+1)&7);dut.rev_v_i=1;
   bool accepted=false;for(unsigned n=0;n<2000;n++)if(step().rev){accepted=true;break;}
   if(!accepted){std::cerr<<"reverse stall cycle="<<cycles_count<<" beat="<<b<<" prefetch="<<h.prefetch
     <<" addr="<<std::hex<<h.addr<<std::dec<<" arrays="<<unsigned(dut.arrays_accept_i)<<" data_v="<<unsigned(dut.data_v_o)<<'\n';
     throw std::runtime_error("reverse packet stalled indefinitely");}
   dut.rev_v_i=0;step();
  }
 }
 void completed(){
  unsigned all=(1u<<(8/dut.fill_words_o))-1;
  for(unsigned n=0;n<2000&&mask!=all;n++)step();
  require(mask==all&&critical==1&&last==1,"incomplete ordinary full-line completion");checking=false;
 }
 void demand_memory(uint64_t addr){unsigned n=reads.size();request(addr);Header h=read(n+1);response(h);completed();idle();}
 void demand_hit(uint64_t addr,bool stall=false){
  unsigned n=reads.size(),hits=dut.hits_o;
  if(stall)dut.arrays_accept_i=0;
  request(addr);
  if(stall){cycles(50);require(mask==0,"array backpressure ignored");dut.arrays_accept_i=1;}
  completed();idle();require(reads.size()==n,"retained hit issued external read");require(dut.hits_o==hits+1,"backend hit missing");
 }
 Header preview(uint64_t addr){
  checking=false;unsigned n=reads.size();dut.preview_addr_i=addr;dut.preview_v_i=1;
  bool accepted=false;for(unsigned k=0;k<2000;k++)if(step().preview){accepted=true;break;}
  require(accepted,"physical preview not accepted");dut.preview_v_i=0;
  Header h=read(n+1);require(h.prefetch&&h.addr==(addr&~UINT64_C(63)),"preview request ownership/alignment wrong");return h;
 }
 void mutate(uint64_t addr){dut.mutation_addr_i=addr;dut.mutation_i=1;step();dut.mutation_i=0;}
 void clear(){dut.clear_i=1;step();dut.clear_i=0;idle();}
 void write_ack(const Header& wb){
  dut.rev_type_i=1;dut.rev_size_i=6;dut.rev_addr_i=wb.addr;dut.rev_way_i=wb.way;dut.rev_state_i=wb.state;
  dut.rev_prefetch_i=0;dut.rev_v_i=1;
  bool ack=false;for(unsigned n=0;n<2000;n++)if(step().rev){ack=true;break;}
  require(ack,"writeback ack stalled");dut.rev_v_i=0;dut.metadata_dirty_i=0;
 }
 void capacity_test(){
  clear();unsigned capacity=dut.capacity_o,published=dut.published_o;
  for(unsigned i=0;i<capacity;i++)demand_memory(UINT64_C(0x81000000)+64*i);
  require(dut.published_o==published+capacity,"not every configured line captured");
  for(unsigned i=0;i<capacity;i++)demand_hit(UINT64_C(0x81000000)+64*i+8*(i&7));
 }
 void refuse_new_fetch(uint64_t addr){
  dut.req_type_i=0;dut.req_addr_i=addr;dut.req_v_i=1;
  for(unsigned n=0;n<3;n++)require(!step().req,"new I fetch stole accepted UCE refill ownership");
  dut.req_v_i=0;
 }
 void cancel_owned_prefetch(bool clear_command){
  uint64_t addr=clear_command?UINT64_C(0x80400000):UINT64_C(0x80401000);
  unsigned pub=dut.published_o,written=data_writes;
  Header h=preview(addr);response(h);
  for(unsigned n=0;n<2000&&!dut.prefetch_insert_owned_o;n++)step();
  require(dut.prefetch_insert_owned_o&&dut.prefetch_state_o==8,"cancel test missed actual retained owned-publish boundary");
  std::cout<<"phase="<<(clear_command?"clear":"disable")<<"-actual-prefetch-insert-owned-at-publish\n";
  if(clear_command)dut.clear_i=1;else dut.enable_i=0;
  step();dut.clear_i=0;idle();
  require(dut.published_o==pub&&data_writes==written,"cancelled owned prefetch insert published or wrote L1");
  dut.enable_i=1;demand_memory(addr);
 }
 void instruction_cases(){
  constexpr uint64_t a=UINT64_C(0x80010000),b=UINT64_C(0x80024000),c=UINT64_C(0x80038000);
  unsigned pub=dut.published_o,before=reads.size();
  // Real I-shaped invalidation must clear retained tags as well as cancel
  // old packets, without relying on the cache-local alternative adapter.
  std::cout<<"phase=I-fence\n";
  request(a,false,7);idle();demand_memory(a);require(reads.size()==before+1,"I fence did not invalidate retained line");
  demand_hit(a+24,true);
  // An FE abort while waiting for retained data does not abandon the UCE's
  // accepted lookup or let a new fetch reuse the old response.
  std::cout<<"phase=I-abort-wait\n";
  before=reads.size();request(a+8);dut.capture_cancel_i=1;step();dut.capture_cancel_i=0;
  refuse_new_fetch(b);completed();idle();require(reads.size()==before,"aborted retained hit unnecessarily read memory");
  // The same ownership rule holds while refill SRAM writes are stalled.
  std::cout<<"phase=I-abort-fill\n";
  dut.arrays_accept_i=0;request(a+40);
  for(unsigned n=0;n<2000&&!dut.data_v_o;n++)step();
  require(dut.data_v_o,"retained I refill never reached SRAM boundary");
  dut.capture_cancel_i=1;step();dut.capture_cancel_i=0;refuse_new_fetch(b);
  dut.arrays_accept_i=1;completed();idle();
  std::cout<<"phase=I-abort-normal\n";
  pub=dut.published_o;before=reads.size();request(b);Header h=read(before+1);
  response(h,0,4);dut.capture_cancel_i=1;step();dut.capture_cancel_i=0;response(h,4,4);completed();idle();
  require(dut.published_o==pub,"aborted I ordinary refill captured");demand_memory(b);
  std::cout<<"phase=I-abort-queued-final\n";
  pub=dut.published_o;before=reads.size();request(UINT64_C(0x80054000));h=read(before+1);response(h);completed();
  dut.capture_cancel_i=1;step();dut.capture_cancel_i=0;idle();
  require(dut.published_o==pub,"queued final I capture survived abort cancellation");
  std::cout<<"phase=I-fence-partial-replay\n";
  pub=dut.published_o;Header pending=preview(c);response(pending,0,2);cycles(40);
  require(dut.published_o==pub,"partial I replay published before full64B");
  request(c,false,7);response(pending,2,6);idle();
  require(dut.published_o==pub,"I fence allowed old replay packet to publish");
  std::cout<<"phase=I-replay-hit\n";
  h=preview(c);response(h);idle();demand_hit(c+40);
  dut.enable_i=0;dut.demand_capture_i=0;pub=dut.published_o;unsigned writes_before=data_writes;
  h=preview(UINT64_C(0x8004c000));response(h);idle();
  require(dut.published_o==pub&&data_writes==writes_before,"off I replay installed/captured instead of dropping");
  dut.enable_i=1;dut.demand_capture_i=1;capacity_test();
  std::cout<<"[UCE-RETAINED-I] PASS: writeback0 fill_words="<<dut.fill_words_o<<" full64B lines="<<dut.capacity_o
    <<" full8word restore/no memory read, fence/abort/off guards; no timing claim\n";
 }
public:
 Test(){context.traceEverOn(true);dut.trace(&trace,8);trace.open("uce-retained.fst");}
 ~Test(){trace.close();}
 void short_response(bool functional_guard){
  if(functional_guard)context.assertOn(false);
  dut.arrays_accept_i=1;dut.fwd_ready_i=1;dut.reset_i=1;cycles(4);dut.reset_i=0;idle();
  dut.enable_i=1;Header h=preview(UINT64_C(0x80010000));h.size=4;
  response(h,0,2);cycles(40);
  if(functional_guard){
   idle();require(dut.published_o==0&&data_writes==0,"short packet became retained/architectural full line");
   demand_memory(UINT64_C(0x80010000));
   std::cout<<"[UCE-SHORT-DRAIN] PASS: assertions disabled;16B reply drained/no full publication; following demand miss completes\n";return;
  }
  throw std::runtime_error("short response did not trip full64B ownership assertion");
 }
 void run(){
  dut.arrays_accept_i=1;dut.fwd_ready_i=1;dut.reset_i=1;cycles(4);dut.reset_i=0;idle();
  constexpr uint64_t a=UINT64_C(0x80010000),b=UINT64_C(0x80024000),c=UINT64_C(0x80038000);
  std::cout<<"phase=disabled-normal\n";
  demand_memory(a+24);require(dut.lookups_o==0&&dut.published_o==0,"disabled arm used retained storage");
  dut.enable_i=1;dut.demand_capture_i=1;demand_memory(a+24);require(dut.published_o==1,"complete normal refill not captured");
  demand_hit(a+24,true);
  cancel_owned_prefetch(true);cancel_owned_prefetch(false);
  if(dut.instruction_o){instruction_cases();return;}
  mutate(a);demand_memory(a+8);demand_hit(a+8);
  // Full physical preview captures only after the normal-resident scan.
  dut.demand_capture_i=0;
  unsigned published=dut.published_o;Header h=preview(b+7);response(h);idle();
  require(dut.published_o==published+1,"full preview not published");demand_hit(b+48);
  dut.resident_i=1;dut.resident_addr_i=c;published=dut.published_o;
  h=preview(c);response(h);idle();require(dut.published_o==published,"normal/dirty resident preview incorrectly captured");
  dut.resident_i=0;demand_memory(c);require(dut.published_o==published,"prefetch-only control captured normal demand");
  dut.demand_capture_i=1;
  // A store cancels a partially returned packet; every remaining beat drains.
  constexpr uint64_t d=UINT64_C(0x8004c000);published=dut.published_o;
  h=preview(d);response(h,0,3);cycles(40);require(dut.published_o==published,"partial D preview published before full64B");
  mutate(d);response(h,3,5);idle();
  require(dut.published_o==published,"store-cancelled partial preview published");demand_memory(d);
  // Off still uses actual64B transport, but cannot fall into legacy installer.
  dut.enable_i=0;dut.demand_capture_i=0;published=dut.published_o;unsigned writes_before=data_writes;
  h=preview(UINT64_C(0x80060000));response(h);idle();
  require(dut.published_o==published&&data_writes==writes_before,"disabled full preview published/installed");dut.enable_i=1;dut.demand_capture_i=1;
  // Clear while a hit lookup owns backend work forces a miss and returns.
  unsigned before=reads.size();request(d);dut.clear_i=1;step();dut.clear_i=0;
  h=read(before+1);response(h);completed();idle();demand_memory(d);
  // A retained hit with a dirty L1 victim still writes all dirty words back.
  before=reads.size();request(d+16,true);completed();
  for(unsigned n=0;n<2000&&write_words.size()<8;n++)step();
  require(reads.size()==before&&write_words.size()==8&&writes.size()==1,"dirty victim writeback/read accounting wrong");
  Header wb=writes.back();require(wb.addr==((UINT64_C(0x800001)<<8)|(d&192)),"dirty victim address lost");
  write_ack(wb);idle();
  // Stale-L2 reply after a dirty normal victim has LEFT L1: a later resident
  // scan cannot see it. The real writeback handshake must cancel this slot.
  constexpr uint64_t target=UINT64_C(0x80070080);
  uint64_t victim=(UINT64_C(0x800001)<<8)|(target&192);
  Header stale=preview(victim);before=reads.size();request(target,true);
  h=read(before+1);response(h);completed();
  for(unsigned n=0;n<2000&&write_words.size()<16;n++)step();
  require(write_words.size()==16&&writes.size()==2,"second dirty writeback incomplete");
  write_ack(writes.back());cycles(100);published=dut.published_o;
  response(stale);idle();require(dut.published_o==published,"stale preview survived dirty victim departure/writeback");
  demand_memory(victim);
  // A queued full preview cannot hijack an ordinary nonblocking write while
  // falsely retiring that write's FIFO entry. Both packet owners must drain.
  dut.fwd_ready_i=0;zero_write=true;request(UINT64_C(0x82000000),false,4);
  dut.preview_addr_i=UINT64_C(0x82001000);dut.preview_v_i=1;
  bool admitted=false;for(unsigned n=0;n<2000;n++)if(step().preview){admitted=true;break;}
  require(admitted,"queued preview not admitted beside UC write");dut.preview_v_i=0;cycles(4);
  before=reads.size();unsigned old_words=write_words.size();dut.fwd_ready_i=1;
  h=read(before+1);require(write_words.size()==old_words+8,"preview stole ordinary write ownership");
  write_ack(writes.back());response(h);idle();zero_write=false;
  // Exercise every configured payload slot with eight distinct words. This
  // UCE unit supplies L1-miss requests; it does not claim unique live-L1 gain.
  capacity_test();
  std::cout<<"[UCE-RETAINED] PASS: full64B lines="<<dut.capacity_o
    <<" normal+preview captures, resident/store/clear guards, backpressure, dirty writeback; no timing claim\n";
 }
};
}
int main(int argc,char**argv){try{Test test;if(argc>1)test.short_response(!std::strcmp(argv[1],"--short-response-drain"));else test.run();return 0;}catch(const std::exception& e){std::cerr<<"[UCE-RETAINED] FAIL: "<<e.what()<<'\n';return 1;}}
