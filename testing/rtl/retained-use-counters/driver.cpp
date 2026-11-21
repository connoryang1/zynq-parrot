#include "VRetainedUse.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdio>
#include <cstdlib>

static vluint64_t time_ps=0;
static void require(bool valid,const char *message) {
  if (!valid) {std::fprintf(stderr,"FAIL: %s\n",message);std::exit(1);}
}
int main(int argc,char **argv) {
  Verilated::commandArgs(argc,argv);Verilated::traceEverOn(true);
  VRetainedUse dut;VerilatedFstC trace;dut.trace(&trace,3);trace.open("unit.fst");
  auto eval=[&](){dut.eval();trace.dump(time_ps++);};
  auto cycle=[&](){dut.clk_i=1;eval();dut.clk_i=2;eval();};
  auto zero=[&](){require(dut.hits_o==0&&dut.published_o==0&&dut.write_beats_o==0,"external reset zero");};
  dut.clk_i=2;dut.reset_i=1;dut.bp_reset_i=1;
  dut.hit_i=0;dut.published_i=0;dut.write_beat_i=0;eval();zero();
  dut.reset_i=0;dut.hit_i=3;dut.published_i=3;dut.write_beat_i=3;
  for (int n=0;n<4;n++)cycle();zero(); // BP reset suppresses, does not create events.
  dut.hit_i=0;dut.published_i=0;dut.write_beat_i=0;dut.bp_reset_i=0;cycle();zero();
  dut.hit_i=3;dut.published_i=3;dut.clk_i=1;eval();
  require(dut.hits_o==1&&dut.published_o==1,"I positive edge only; D untouched");
  dut.clk_i=2;eval();
  require(dut.hits_o==0x00010001&&dut.published_o==0x00010001,"D negative edge and I/D packing");
  dut.hit_i=0;dut.published_i=0;dut.write_beat_i=3;
  for (int n=0;n<8;n++)cycle();
  require(dut.write_beats_o==0x00080008,"one full64B restore has eight64b beats per lane");
  dut.bp_reset_i=1;dut.hit_i=3;dut.published_i=3;
  for (int n=0;n<20;n++)cycle();
  require(dut.hits_o==0x00010001&&dut.published_o==0x00010001&&dut.write_beats_o==0x00080008,
          "CPU/tag reset retains counts and gates increments");
  dut.bp_reset_i=0;
  for (int n=0;n<65540;n++)cycle();
  require(dut.hits_o==0xffffffff&&dut.published_o==0xffffffff&&dut.write_beats_o==0xffffffff,"all six fields saturate without wrap");
  for (int n=0;n<8;n++)cycle();
  require(dut.hits_o==0xffffffff&&dut.published_o==0xffffffff&&dut.write_beats_o==0xffffffff,"saturated events stay saturated");
  dut.reset_i=1;eval();zero(); // Clear without a clock edge, external AXI reset only.
  dut.hit_i=0;dut.published_i=0;dut.write_beat_i=0;dut.reset_i=0;cycle();zero();
  trace.close();dut.final();
  std::puts("RETAINED_USE_UNIT_PASS first_touch_i=1/1/8 first_touch_d=1/1/8 reset=axi_only saturation=65535");
}
