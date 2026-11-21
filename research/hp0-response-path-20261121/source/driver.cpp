#include "Vhp0_response_path.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdint>
#include <cstdio>
#include <deque>
#include <stdexcept>
#include <tuple>

using Packet = std::tuple<uint64_t, unsigned, unsigned, unsigned>;
struct Expected { Packet value; uint64_t cycle; };
static void check(bool v, const char *message) { if (!v) throw std::runtime_error(message); }
struct Sim {
  VerilatedContext context;
  Vhp0_response_path dut{&context};
  VerilatedFstC trace;
  uint64_t cycle = 0, time = 0, rin = 0, rout = 0, bin = 0, bout = 0;
  std::deque<Expected> rq, bq;
  bool held_r = false, held_b = false, exact = false;
  Packet previous_r{}, previous_b{};
  Sim() {
    context.traceEverOn(true); dut.trace(&trace, 20); trace.open("hp0-response-path.fst");
    dut.aclk = 0; dut.aresetn = 0; quiet();
    for (int n = 0; n < 3; ++n) step();
    dut.aresetn = 1; dut.eval();
  }
  ~Sim() { dut.final(); trace.close(); }
  void quiet() { dut.hp0_axi_rvalid = dut.hp0_axi_bvalid = 0; dut.consume_rready = dut.consume_bready = 1; }
  Packet input_r() { return {dut.hp0_axi_rdata,dut.hp0_axi_rid,dut.hp0_axi_rresp,dut.hp0_axi_rlast}; }
  Packet output_r() { return {dut.rdata_o,dut.rid_o,dut.rresp_o,dut.rlast_o}; }
  Packet input_b() { return {0,dut.hp0_axi_bid,dut.hp0_axi_bresp,0}; }
  Packet output_b() { return {0,dut.bid_o,dut.bresp_o,0}; }
  void drive(unsigned r, unsigned b) {
    dut.hp0_axi_rdata = UINT64_C(0x8f0921a5b7c30000) ^ (UINT64_C(0x139a571) * r);
    dut.hp0_axi_rid = r % 64; dut.hp0_axi_rresp = (r / 7) % 4; dut.hp0_axi_rlast = r % 8 == 7;
    dut.hp0_axi_bid = (b + 37) % 64; dut.hp0_axi_bresp = (b / 5) % 4;
  }
  std::pair<bool,bool> step() {
    dut.aclk = 0; dut.eval(); trace.dump(++time);
    bool ri = dut.hp0_axi_rvalid && dut.hp0_axi_rready;
    bool ro = dut.rvalid_o && dut.consume_rready;
    bool bi = dut.hp0_axi_bvalid && dut.hp0_axi_bready;
    bool bo = dut.bvalid_o && dut.consume_bready;
    if (dut.aresetn) {
      if (held_r) check(dut.rvalid_o && output_r() == previous_r,"R changed under consumer backpressure");
      if (held_b) check(dut.bvalid_o && output_b() == previous_b,"B changed under consumer backpressure");
      if (ri) { rq.push_back({input_r(),cycle}); ++rin; }
      if (bi) { bq.push_back({input_b(),cycle}); ++bin; }
      if (ro) {
        check(!rq.empty(),"unowned R response"); auto row = rq.front(); rq.pop_front(); ++rout;
        check(output_r() == row.value,"R ID/data/response/LAST corruption or reordering");
        check(cycle-row.cycle >= DELAY,"R earlier than static minimum");
        if (exact) check(cycle-row.cycle == DELAY,"freely draining R shift differs from N");
      }
      if (bo) {
        check(!bq.empty(),"unowned B response"); auto row = bq.front(); bq.pop_front(); ++bout;
        check(output_b() == row.value,"B ID/response corruption or reordering");
        check(cycle-row.cycle >= DELAY,"B earlier than static minimum");
        if (exact) check(cycle-row.cycle == DELAY,"freely draining B shift differs from N");
      }
      held_r = dut.rvalid_o && !dut.consume_rready; previous_r = output_r();
      held_b = dut.bvalid_o && !dut.consume_bready; previous_b = output_b();
    }
    dut.aclk = 1; dut.eval(); trace.dump(++time); ++cycle;
    dut.aclk = 0; dut.eval(); trace.dump(++time);
    return {ri,bi};
  }
  void drain() {
    quiet(); dut.eval(); unsigned bound = 10000;
    while (!rq.empty() || !bq.empty()) { check(bound-- != 0,"bounded drain timeout"); step(); }
    for (int n = 0; n < 2; ++n) { check(!dut.rvalid_o && !dut.bvalid_o,"duplicate response after drain"); step(); }
  }
  void native_identity() {
    if (DELAY) return;
    for (unsigned n = 0; n < 128; ++n) {
      drive(n,n+3); dut.hp0_axi_rvalid = n & 1; dut.hp0_axi_bvalid = (n >> 1) & 1;
      dut.consume_rready = (n >> 2) & 1; dut.consume_bready = (n >> 3) & 1;
      dut.eval();
      check(dut.hp0_axi_rready == dut.consume_rready && dut.hp0_axi_bready == dut.consume_bready,"native ready not direct");
      check(dut.rvalid_o == dut.hp0_axi_rvalid && dut.bvalid_o == dut.hp0_axi_bvalid,"native valid not direct");
      check(output_r() == input_r() && output_b() == input_b(),"native opaque fields not direct");
    }
    quiet(); dut.eval(); std::puts("HP0_NATIVE_UNCLOCKED_128_PASS");
  }
  void burst() {
    exact = true;
    for (unsigned n = 0; n < 64; ++n) {
      drive(n,n); dut.hp0_axi_rvalid = dut.hp0_axi_bvalid = 1;
      auto accepted = step(); check(accepted.first && accepted.second,"unsaturated burst backpressured");
    }
    drain(); exact = false;
    std::printf("HP0_EXACT_BEAT_SHIFT_PASS N=%u R=64 B=64 IDs=64\n",DELAY);
  }
  void mixed() {
    unsigned r = 0, b = 0, bound = 12000;
    while (r < 1024 || b < 1024 || !rq.empty() || !bq.empty()) {
      check(bound-- != 0,"mixed stream timeout"); drive(r,b);
      dut.hp0_axi_rvalid = r < 1024; dut.hp0_axi_bvalid = b < 1024;
      dut.consume_rready = cycle % 5 != 0; dut.consume_bready = cycle % 7 != 0;
      auto accepted = step(); r += accepted.first; b += accepted.second;
    }
    drain(); std::puts("HP0_MIXED_IDS_BACKPRESSURE_PASS R=1024 B=1024");
  }
  void full() {
    if (!DELAY) return;
    dut.consume_rready = dut.consume_bready = 0;
    for (unsigned n = 0; n < 512; ++n) {
      drive(n,n); dut.hp0_axi_rvalid = dut.hp0_axi_bvalid = 1;
      auto accepted = step(); check(accepted.first && accepted.second,"queue filled before 512");
    }
    drive(512,512);
    for (unsigned n = 0; n < 13; ++n) {
      auto accepted = step(); check(!accepted.first && !accepted.second,"full queue accepted without space");
    }
    dut.consume_rready = dut.consume_bready = 1;
    auto accepted = step(); check(accepted.first && accepted.second,"same-edge pop did not free input space");
    drain(); std::puts("HP0_FULL_512_HELD_READY_PASS");
  }
};

int main(int argc, char **argv) {
  Verilated::commandArgs(argc,argv);
  try {
    Sim s; s.native_identity(); s.burst(); s.mixed(); s.full();
    check(s.rin == s.rout && s.bin == s.bout,"accepted/delivered conservation failed");
    std::printf("HP0_RESPONSE_PATH_PASS N=%u R=%llu B=%llu\n",DELAY,
                (unsigned long long)s.rout,(unsigned long long)s.bout);
  } catch (const std::exception& error) {
    std::fprintf(stderr,"HP0_RESPONSE_PATH_FAIL %s\n",error.what()); return 1;
  }
  std::puts("HP0_RESPONSE_PATH_EXIT_CLEAN"); return 0;
}
