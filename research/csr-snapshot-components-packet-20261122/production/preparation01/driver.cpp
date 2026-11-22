#include "Vcsr_snapshot_production_wrapper.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <stdexcept>
using Image=std::array<uint32_t,53>;
static uint64_t rng=0x9f130ccfa2376d45ULL;
static uint32_t rnd(){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return uint32_t(rng);}
int main(int argc,char**argv){
 Verilated::commandArgs(argc,argv);Verilated::traceEverOn(true);
 Vcsr_snapshot_production_wrapper t;VerilatedFstC trace;t.trace(&trace,1);trace.open("snapshot.fst");
 bool negative=argc>1&&!std::strcmp(argv[1],"negative");uint64_t ticks=0,cycles=0,checks=0,combinations=0;
 std::array<Image,4> images{};std::array<bool,4> valid{};
 auto eval=[&](){t.eval();};
 auto reads=[&](){for(unsigned a=0;a<4;a++){
  t.read_context_i=a;eval();++checks;
  bool match=t.current_bank_i==t.retire_bank_i;
  bool sv=match&&t.instret_i&&t.ctxtsw_i;
  bool cv=match&&t.csrw_i&&!t.ctxtsw_i&&t.addr801_i&&((t.legacy_access_i>>t.current_bank_i)&1);
  bool dv=cv&&(t.rebind_i||!valid[t.seed_context_i]);
  if(t.exclusive_violation_o|| (sv&&dv))throw std::runtime_error("raw production exclusivity violated");
  if(t.mismatch_o){if(negative)throw 77;throw std::runtime_error("full component miter mismatch");}
  if(t.qualification_mismatch_o||bool(t.save_intent_o)!=sv||bool(t.seed_intent_o)!=dv)throw std::runtime_error("independent raw qualification mismatch");
  if(t.reservation_owner_o!=t.reservation_bank_i)throw std::runtime_error("reservation observation mismatch");
  unsigned vv=0;for(unsigned k=0;k<4;k++)vv|=unsigned(valid[k])<<k;
  if(t.valid_vector_o!=vv||bool(t.read_valid_o)!=valid[a])throw std::runtime_error("independent validity mismatch");
  for(unsigned w=0;w<53;w++)if(t.read_data_o[w]!=images[a][w])throw std::runtime_error("independent payload/owner mismatch");
 }};
 auto edge=[&](){
  t.clk_i=0;eval();if(cycles)reads();trace.dump(ticks++);
  bool match=t.current_bank_i==t.retire_bank_i;
  bool sv=match&&t.instret_i&&t.ctxtsw_i;
  bool dv=match&&t.csrw_i&&!t.ctxtsw_i&&t.addr801_i&&((t.legacy_access_i>>t.current_bank_i)&1)&&(t.rebind_i||!valid[t.seed_context_i]);
  t.clk_i=1;eval();trace.dump(ticks++);++cycles;
  if(t.reset_i){valid.fill(false);for(auto&x:images)x.fill(0);}
  else if(sv||dv){unsigned a=dv?t.seed_context_i:t.save_context_i;valid[a]=true;for(unsigned w=0;w<53;w++)images[a][w]=t.save_bank_i?t.bank1_data_i[w]:t.bank0_data_i[w];}
  reads();t.clk_i=0;eval();trace.dump(ticks++);
 };
 auto pattern=[&](unsigned bit){for(unsigned w=0;w<53;w++){t.bank0_data_i[w]=0;t.bank1_data_i[w]=~uint32_t(0);}
  t.bank0_data_i[bit/32]=1U<<(bit%32);t.bank1_data_i[bit/32]=~uint32_t(t.bank0_data_i[bit/32]);t.bank1_data_i[52]&=3;t.bank0_data_i[52]&=3;};
 try{
 t.reset_i=1;t.clk_i=0;t.instret_i=0;t.csrw_i=0;t.ctxtsw_i=0;t.addr801_i=0;t.rebind_i=0;t.legacy_access_i=0;t.current_bank_i=0;t.retire_bank_i=0;t.save_bank_i=0;t.reservation_bank_i=0;t.save_context_i=0;t.seed_context_i=0;t.read_context_i=0;pattern(0);edge();
 t.reset_i=0;t.instret_i=1;t.ctxtsw_i=1;
 for(unsigned a=0;a<4;a++){t.save_context_i=a;pattern(100+a);edge();}
 t.reset_i=1;t.csrw_i=1;t.addr801_i=1;t.rebind_i=1;t.legacy_access_i=3;
 for(unsigned i=0;i<4;i++){t.ctxtsw_i=i&1;t.seed_context_i=i;edge();}
 t.reset_i=0;t.instret_i=0;t.csrw_i=0;edge();
 // Cold first seed without rebind, rejected existing-context reseed, then
 // explicit rebind: each has a distinct data pattern and both data owners.
 t.instret_i=0;t.csrw_i=1;t.ctxtsw_i=0;t.addr801_i=1;t.legacy_access_i=1;t.current_bank_i=t.retire_bank_i=0;
 for(unsigned a=0;a<4;a++){
  t.seed_context_i=a;t.save_bank_i=a&1;t.rebind_i=0;pattern(400+a);edge();
  pattern(500+a);edge();t.rebind_i=1;pattern(600+a);edge();
 }
 // All128 raw Boolean patterns incl independent legacy permissions x16 bank
 // owner selections x4 target contexts; validity is independently qualified.
 for(unsigned raw=0;raw<128;raw++)for(unsigned bank=0;bank<16;bank++)for(unsigned a=0;a<4;a++){
  t.instret_i=raw&1;t.csrw_i=(raw>>1)&1;t.ctxtsw_i=(raw>>2)&1;t.addr801_i=(raw>>3)&1;t.rebind_i=(raw>>4)&1;t.legacy_access_i=(raw>>5)&3;
  t.current_bank_i=bank&1;t.retire_bank_i=(bank>>1)&1;t.save_bank_i=(bank>>2)&1;t.reservation_bank_i=(bank>>3)&1;
  t.save_context_i=a;t.seed_context_i=3-a;pattern((raw+17*bank+a)%1666);edge();++combinations;
 }
 // Every real image bit/context through both exclusive writer intents and
 // both common-data owner banks, with reservation deliberately independent.
 t.current_bank_i=t.retire_bank_i=1;t.reservation_bank_i=0;t.instret_i=1;t.csrw_i=1;t.addr801_i=1;t.rebind_i=1;t.legacy_access_i=2;
 for(unsigned a=0;a<4;a++)for(unsigned bit=0;bit<1666;bit++)for(unsigned writer=0;writer<2;writer++){
  t.save_context_i=t.seed_context_i=a;t.save_bank_i=(a+bit+writer)&1;t.ctxtsw_i=!writer;pattern(bit);edge();}
 for(unsigned i=0;i<512;i++){
  t.reset_i=i%113==0;t.instret_i=rnd()&1;t.csrw_i=rnd()&1;t.ctxtsw_i=rnd()&1;t.addr801_i=rnd()&1;t.rebind_i=rnd()&1;t.legacy_access_i=rnd()&3;
  t.current_bank_i=rnd()&1;t.retire_bank_i=rnd()&1;t.save_bank_i=rnd()&1;t.reservation_bank_i=rnd()&1;t.save_context_i=rnd()&3;t.seed_context_i=rnd()&3;
  for(unsigned w=0;w<53;w++){t.bank0_data_i[w]=rnd();t.bank1_data_i[w]=rnd();}t.bank0_data_i[52]&=3;t.bank1_data_i[52]&=3;edge();
 }
 if(negative)throw std::runtime_error("suppressed-write negative not detected");
 trace.close();std::printf("CSR_PRODUCTION_FULL_IMAGE_PASS cycles=%llu checks=%llu raw_combinations=%llu width=1666 contexts=4\nCSR_PRODUCTION_EXIT_CLEAN\n",(unsigned long long)cycles,(unsigned long long)checks,(unsigned long long)combinations);return 0;
 }catch(int e){trace.close();if(negative&&e==77){std::printf("CSR_PRODUCTION_NEGATIVE_REJECTED cycles=%llu\nCSR_PRODUCTION_EXIT_CLEAN\n",(unsigned long long)cycles);return 0;}return 2;}
 catch(const std::exception&e){trace.close();std::fprintf(stderr,"FAIL %s cycles=%llu\n",e.what(),(unsigned long long)cycles);return 1;}
}
