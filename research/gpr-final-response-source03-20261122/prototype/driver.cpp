// Source only; independent scalar-memory/control oracle. No generated internals.
#include "Vgpr_prefetch_miter.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
using Line=std::array<uint64_t,16>;
static uint64_t rng=0x76cbe93212ad494bULL;
static uint64_t random64(){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;}
static uint64_t word(const VlWide<32>& x,int k){return uint64_t(x[2*k])|(uint64_t(x[2*k+1])<<32);}
static void need(bool x,const char* text){if(!x)throw std::runtime_error(text);}
struct Oracle {
  uint64_t words[4][32]{};uint32_t valid[4]{};
  unsigned state=0,target=0;bool issue=0,done=0,install=0;
  unsigned slots=0;Line saved[2]{};
  bool response=0,response_line=0;unsigned response_context=0;Line response_data{};
  uint64_t cycles=0,checks=0,reads=0,writes=0,installs=0,launches=0;
  bool mismatch_expected=false;
  void verify(Vgpr_prefetch_miter& t){
    bool req=(state==1||state==2)&&!done;
    bool lw=(state==3||(state==2&&t.drain_i&&t.dirty_i))&&((slots>>install)&1);
    bool launch=state==4||(state==3&&((slots>>install)&1)&&install);
    need(t.state_o==state&&t.req_o==req&&t.req_line_o==issue&&t.req_context_o==target,"independent request/state oracle");
    need(t.response_o==response&&t.response_line_o==response_line&&t.response_context_o==response_context,"independent response metadata");
    need(t.line_write_o==lw&&t.line_index_o==install&&t.launch_o==launch,"RF/FE exact edge oracle");
    need(!t.lease_violation_o,"next read before last borrowed use");
    if(response)for(int k=0;k<16;k++){need(word(t.response_data_o,k)==response_data[k],"full1024 independent accepted-read data");checks++;}
    if(lw){for(int k=0;k<16;k++){if(word(t.line_data_o,k)!=saved[install][k])mismatch_expected=true;checks++;}}
    if(t.mismatch_o||mismatch_expected)throw std::runtime_error("full1024 controller/reference/borrow mismatch");
  }
  void tick(Vgpr_prefetch_miter& t){
    t.clk_i=0;t.eval();verify(t);need(!t.collision_o,"forbidden accepted 1R1W same-address collision");
    bool req=t.req_o,oldresponse=response;bool oldline=response_line;Line olddata=response_data;
    bool lw=t.line_write_o,li=t.line_index_o;
    bool sv=t.w_v_i!=0;unsigned port=(t.w_v_i>>1)&1;
    unsigned wc=(t.w_context_i>>(2*port))&3,wr=(t.w_reg_i>>(5*port))&31;
    uint64_t wd=uint64_t(t.w_data_i[2*port])|(uint64_t(t.w_data_i[2*port+1])<<32);
    // READ_FIRST old memory, with writes and reads independently accepted.
    Line next{};
    if(req)for(int k=0;k<16;k++)next[k]=((valid[target]>>(16*issue+k))&1)?words[target][16*issue+k]:0;
    if(sv){words[wc][wr]=wd;writes++;}
    if(t.reset_i){state=0;target=0;issue=0;done=0;install=0;slots=0;response=0;response_context=0;response_line=0;for(auto& v:valid)v=0;saved[0].fill(0);saved[1].fill(0);}
    else {
      if(sv)valid[wc]|=uint32_t(1)<<wr;
      if(oldresponse){slots|=1u<<oldline;saved[oldline]=olddata;}
      if(req){if(issue)done=1;else issue=1;reads++;}
      // State transition uses pre-edge visible valid and control values.
      switch(state){
        case 0:if(t.miss_i){state=1;target=t.target_i;issue=0;done=0;install=0;slots=0;}break;
        case 1:if(t.commit_i)state=2;else if(t.redirect_i)state=0;break;
        case 2:if(lw)install=!install;if(t.drain_i)state=t.dirty_i?3:4;break;
        case 3:if(lw){if(li)state=t.fe_yumi_i?5:4;else install=1;}break;
        case 4:if(t.fe_yumi_i)state=5;break;
        case 5:state=0;break;
      }
      response=req;
      if(req){response_context=t.req_context_o;response_line=t.req_line_o;response_data=next;}
    }
    if(lw)installs++;if(t.launch_o)launches++;
    t.clk_i=1;t.eval();cycles++;verify(t);
  }
};
static void write(Vgpr_prefetch_miter& t,unsigned port,unsigned ctx,unsigned reg,uint64_t data){
 t.w_v_i|=1u<<port;t.w_context_i=(t.w_context_i&~(3u<<(2*port)))|(ctx<<(2*port));
 t.w_reg_i=(t.w_reg_i&~(31u<<(5*port)))|(reg<<(5*port));
 t.w_data_i[2*port]=uint32_t(data);t.w_data_i[2*port+1]=uint32_t(data>>32);
}
int main(int argc,char**argv){
 Verilated::commandArgs(argc,argv);Vgpr_prefetch_miter t;Oracle o;
 bool negative=argc>1&&std::strcmp(argv[1],"--negative")==0;
 bool collision=argc>1&&std::strcmp(argv[1],"--collision")==0;
 auto step=[&](){o.tick(t);};
 try {
  t.reset_i=1;t.miss_i=0;t.commit_i=0;t.redirect_i=0;t.drain_i=0;t.dirty_i=1;t.fe_yumi_i=0;t.target_i=0;t.w_v_i=0;t.w_context_i=0;t.w_reg_i=0;t.w_data_i[0]=0;t.w_data_i[1]=0;t.w_data_i[2]=0;t.w_data_i[3]=0;
  // Initial reset followed by idle proves response-invalid/zero-metadata;
  // raw payload before first valid request is deliberately not observed.
  t.clk_i=0;t.eval();t.clk_i=1;t.eval();o.cycles++;t.clk_i=0;t.eval();o.verify(t);step();t.reset_i=0;
  for(unsigned round=0;round<48;round++){
    if((round%8)==0){t.reset_i=1;step();step();t.reset_i=0;}
    // Partial-valid and full-valid contexts; both intents, remote priority.
    unsigned limit=(round%3)==0?13:32;
    for(unsigned c=0;c<4;c++)for(unsigned r=0;r<limit;r++){
      t.w_v_i=0;write(t,0,(c+1)&3,(r+7)&31,random64());write(t,1,c,r,random64()|1);step();
    }
    t.w_v_i=0;t.dirty_i=(round%5)!=0;t.target_i=round&3;t.miss_i=1;step();t.miss_i=0;
    if(collision){t.clk_i=0;t.eval();t.w_v_i=0;write(t,1,t.req_context_o,unsigned(t.req_line_o)*16,1);step();throw std::runtime_error("collision control did not reject");}
    unsigned committed=0;
    for(unsigned phase=0;phase<150;phase++){
      t.clk_i=0;t.eval();t.w_v_i=0;t.commit_i=phase==unsigned(round%5);if(t.commit_i)committed=1;
      t.redirect_i=(round%7)==0&&phase==0&&!t.commit_i;
      t.drain_i=phase>((round%4)==0?0:35+(round%17));t.fe_yumi_i=(round%6)==0||phase>100;
      // Independent scalar writes to the held line after its accepted read:
      // payload+mask must remain the OLD response through delayed RF use.
      unsigned c=t.req_context_o;unsigned r=(phase*7+round)&31;
      if(t.req_o)c=(c+1)&3; // preserve prohibited collision contract.
      if((phase%2)==0)write(t,0,c,r,random64()|1);
      if((phase%3)==0)write(t,1,c,(r+1)&31,random64()|1);
      if((round%11)==0&&phase==9)t.reset_i=1;else t.reset_i=0;
      step();
      if(o.state==0&&phase>3)break;
    }
    t.reset_i=0;t.w_v_i=0;t.commit_i=0;t.redirect_i=0;t.drain_i=1;t.fe_yumi_i=1;
    for(unsigned guard=0;o.state!=0&&guard<32;guard++)step();
    need(o.state==0,"bounded drain/end turnover");(void)committed;
  }
  need(!negative,"mutation negative did not reject");
  need(o.reads>40&&o.installs>30&&o.launches>20,"meaningful two-line/abort/drain/FE coverage");
  std::printf("GPR_BORROW_PASS cycles=%llu checks=%llu reads=%llu writes=%llu installs=%llu launches=%llu\n",(unsigned long long)o.cycles,(unsigned long long)o.checks,(unsigned long long)o.reads,(unsigned long long)o.writes,(unsigned long long)o.installs,(unsigned long long)o.launches);
 }catch(const std::exception& e){
  if(collision&&std::strstr(e.what(),"forbidden accepted 1R1W same-address collision")){std::puts("GPR_BORROW_COLLISION_REJECTED exactselectedbank");return 0;}
  if(negative&&std::strstr(e.what(),"full1024 controller/reference/borrow mismatch")){std::printf("GPR_BORROW_NEGATIVE_REJECTED full1024 cycle=%llu\n",(unsigned long long)o.cycles);return 0;}
  std::fprintf(stderr,"GPR_BORROW_FAIL %s cycle=%llu\n",e.what(),(unsigned long long)o.cycles);return 1;
 }
 return 0;
}
