#include "Vcsr_snapshot_wrapper.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <stdexcept>
using Image=std::array<uint32_t,53>;
static uint64_t rng=0x286346deb7391ab5ULL;
static uint32_t random_word(){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return uint32_t(rng);}
int main(int argc,char**argv){
 Verilated::commandArgs(argc,argv);Verilated::traceEverOn(true);
 Vcsr_snapshot_wrapper t;VerilatedFstC trace;t.trace(&trace,1);trace.open("snapshot.fst");
 uint64_t tick=0,cycles=0,checks=0; bool expect_negative=argc>1&&std::strcmp(argv[1],"negative")==0;
 std::array<Image,4> oracle{};std::array<bool,4> valid{};
 auto eval=[&](){t.eval();};
 auto all_reads=[&](){for(unsigned a=0;a<4;a++){
   t.read_addr_i=a;eval();++checks;
   if(t.single_mismatch_o)throw std::runtime_error("single-context miter mismatch");
   if(t.mismatch_o){if(expect_negative)throw 77;throw std::runtime_error("actual4x1666 miter mismatch");}
   unsigned expected_valid=0;for(unsigned k=0;k<4;k++)expected_valid|=unsigned(valid[k])<<k;
   if(t.valid_vector_o!=expected_valid)throw std::runtime_error("independent validity-vector mismatch");
   if(bool(t.read_valid_o)!=valid[a])throw std::runtime_error("independent validity mismatch");
   for(unsigned w=0;w<53;w++)if(t.read_data_o[w]!=oracle[a][w])throw std::runtime_error("independent full-image mismatch");
 }};
 auto edge=[&](){
   t.clk_i=0;eval();if(cycles)all_reads();trace.dump(tick++);
   t.clk_i=1;eval();trace.dump(tick++);++cycles;
   if(t.reset_i){valid.fill(false);for(auto &x:oracle)x.fill(0);}
   else {
     if(t.save_v_i){valid[t.save_addr_i]=true;for(unsigned w=0;w<53;w++)oracle[t.save_addr_i][w]=t.save_data_i[w];}
     if(t.seed_v_i){valid[t.seed_addr_i]=true;for(unsigned w=0;w<53;w++)oracle[t.seed_addr_i][w]=t.seed_data_i[w];}
   }
   all_reads();t.clk_i=0;eval();trace.dump(tick++);
 };
 auto data=[&](unsigned bit){for(unsigned w=0;w<53;w++){t.save_data_i[w]=0;t.seed_data_i[w]=0;}
   t.save_data_i[bit/32]=1U<<(bit%32);
   for(unsigned w=0;w<53;w++)t.seed_data_i[w]=~uint32_t(t.save_data_i[w]);
   t.save_data_i[52]&=3;t.seed_data_i[52]&=3;
 };
 try{
 t.reset_i=1;t.save_v_i=0;t.seed_v_i=0;t.save_addr_i=0;t.seed_addr_i=0;t.read_addr_i=0;data(0);edge();
 // Define nonzero payload in every writer bank before resetting: no zero-RAM assumption.
 t.reset_i=0;for(unsigned a=0;a<4;a++){t.save_v_i=t.seed_v_i=1;t.save_addr_i=t.seed_addr_i=a;data(a+100);edge();}
 // Held reset dominates valid writes, then leaves every old payload masked at all addresses.
 t.reset_i=1;for(unsigned a=0;a<4;a++){t.save_addr_i=a;t.seed_addr_i=3-a;data(a+200);edge();}
 t.reset_i=0;t.save_v_i=t.seed_v_i=0;edge();
 // All ordered address pairs, independent writer intents, and seed-wins collisions.
 for(unsigned s=0;s<4;s++)for(unsigned d=0;d<4;d++)for(unsigned mask=1;mask<4;mask++){
   t.save_v_i=mask&1;t.seed_v_i=(mask>>1)&1;t.save_addr_i=s;t.seed_addr_i=d;data(300+16*s+4*d+mask);edge();}
 // Every bit of the real1666-bit image, in every context, through each writer.
 for(unsigned a=0;a<4;a++)for(unsigned bit=0;bit<1666;bit++){
   data(bit);t.save_addr_i=a;t.seed_addr_i=(a+1)%4;t.save_v_i=1;t.seed_v_i=1;edge();}
 for(unsigned n=0;n<512;n++){
   t.reset_i=(n%113)==0;t.save_v_i=random_word()&1;t.seed_v_i=random_word()&1;
   t.save_addr_i=random_word()%4;t.seed_addr_i=random_word()%4;
   for(unsigned w=0;w<53;w++){t.save_data_i[w]=random_word();t.seed_data_i[w]=random_word();}
   t.save_data_i[52]&=3;t.seed_data_i[52]&=3;edge();
 }
 if(expect_negative)throw std::runtime_error("negative mutation not detected");
 trace.close();std::printf("CSR_SNAPSHOT_FULL_IMAGE_PASS cycles=%llu all_context_checks=%llu width=1666 contexts=4 single_width=65\nCSR_SNAPSHOT_EXIT_CLEAN\n",(unsigned long long)cycles,(unsigned long long)checks);return 0;
 }catch(int e){trace.close();if(e==77&&expect_negative){std::printf("CSR_SNAPSHOT_NEGATIVE_REJECTED cycles=%llu\nCSR_SNAPSHOT_EXIT_CLEAN\n",(unsigned long long)cycles);return 0;}return 2;}
 catch(const std::exception&e){trace.close();std::fprintf(stderr,"FAIL %s cycles=%llu\n",e.what(),(unsigned long long)cycles);return 1;}
}
