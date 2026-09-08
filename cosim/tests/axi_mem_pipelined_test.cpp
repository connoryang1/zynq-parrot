// Explicit-clock protocol test: requires no coroutine/timing runtime support.
#include "Vbp_nonsynth_axi_mem_pipelined.h"
#include "verilated.h"
#include <algorithm>
#include <cstdint>
#include <deque>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static void require(bool condition, const std::string &message) {
  if (!condition) throw std::runtime_error(message);
}
struct Beat { uint64_t data; unsigned id, request; bool last, first; };
struct Harness {
  Vbp_nonsynth_axi_mem_pipelined d;
  static const unsigned latency = 40;
  std::vector<uint64_t> memory = std::vector<uint64_t>(1024, UINT64_C(0x0102030401020304));
  std::deque<Beat> expected;
  std::vector<unsigned> ar_tick, first_tick, finish_tick;
  unsigned tick = 0, steps = 0, outstanding = 0, maximum = 0;
  bool stalled = false;
  uint64_t held_data = 0;
  unsigned held_id = 0, held_last = 0, held_resp = 0;
  unsigned write_addr = 0, write_len = 0, write_size = 0, write_burst = 0, write_beat = 0;

  static unsigned address(unsigned start, unsigned len, unsigned size, unsigned burst, unsigned beat) {
    unsigned span = (1u << size) * (len + 1), increment = start + beat * (1u << size);
    return burst == 0 ? start : burst == 2 ? (start / span) * span + increment % span : increment;
  }
  void step() {
    require(++steps < 10000, "protocol test timed out");
    d.clk_i = 0; d.eval();
    if (d.reset_i) {
      expected.clear(); ar_tick.clear(); first_tick.clear(); finish_tick.clear();
      tick = outstanding = maximum = 0; stalled = false;
    } else {
      ++tick;
      if (stalled) require(d.axi_rvalid_o && d.axi_rdata_o == held_data && d.axi_rid_o == held_id
                           && d.axi_rlast_o == held_last && d.axi_rresp_o == held_resp,
                           "R payload changed while stalled");
      stalled = d.axi_rvalid_o && !d.axi_rready_i;
      held_data = d.axi_rdata_o; held_id = d.axi_rid_o;
      held_last = d.axi_rlast_o; held_resp = d.axi_rresp_o;
      if (d.axi_arvalid_i && d.axi_arready_o) {
        unsigned request = ar_tick.size();
        ar_tick.push_back(tick); first_tick.push_back(0); finish_tick.push_back(0);
        for (unsigned beat = 0; beat <= d.axi_arlen_i; ++beat) {
          unsigned a = address(d.axi_araddr_i, d.axi_arlen_i, d.axi_arsize_i, d.axi_arburst_i, beat);
          expected.push_back({memory.at(a/8), d.axi_arid_i, request,
                              beat == d.axi_arlen_i, beat == 0});
        }
        maximum = std::max(maximum, ++outstanding);
      }
      if (d.axi_rvalid_o) {
        require(!expected.empty(), "unexpected read response");
        const Beat &e = expected.front();
        require(d.axi_rresp_o == 0 && d.axi_rid_o == e.id && bool(d.axi_rlast_o) == e.last
                && d.axi_rdata_o == e.data, "read data/ID/order/last mismatch");
        require(tick - ar_tick[e.request] >= latency, "response preceded its own service latency");
        if (e.first && !first_tick[e.request]) first_tick[e.request] = tick;
        if (d.axi_rready_i) {
          if (e.last) { finish_tick[e.request] = tick; --outstanding; }
          expected.pop_front();
        }
      }
      if (d.axi_awvalid_i && d.axi_awready_o) {
        write_addr = d.axi_awaddr_i; write_len = d.axi_awlen_i;
        write_size = d.axi_awsize_i; write_burst = d.axi_awburst_i; write_beat = 0;
      }
      if (d.axi_wvalid_i && d.axi_wready_o) {
        unsigned a = address(write_addr, write_len, write_size, write_burst, write_beat++);
        for (unsigned lane = 0; lane < 8; ++lane) if (d.axi_wstrb_i & (1u << lane)) {
          uint64_t mask = UINT64_C(0xff) << (8*lane);
          memory.at(a/8) = (memory.at(a/8) & ~mask) | (d.axi_wdata_i & mask);
        }
      }
    }
    d.clk_i = 1; d.eval(); d.clk_i = 0; d.eval();
  }
  Harness() {
    d.reset_i = 1; d.axi_awvalid_i = d.axi_wvalid_i = d.axi_arvalid_i = 0;
    d.axi_bready_i = 1; d.axi_rready_i = 0;
    for (unsigned i = 0; i < 3; ++i) step();
    d.reset_i = 0; step();
  }
  void set_ar(unsigned a, unsigned len, unsigned size, unsigned burst, unsigned id) {
    d.axi_araddr_i = a; d.axi_arlen_i = len; d.axi_arsize_i = size;
    d.axi_arburst_i = burst; d.axi_arid_i = id; d.axi_arvalid_i = 1; d.eval();
  }
  void finish_ar() {
    bool ready;
    do { d.eval(); ready = d.axi_arready_o; step(); } while (!ready);
    d.axi_arvalid_i = 0; d.eval();
  }
  void ar(unsigned a, unsigned len, unsigned size, unsigned burst, unsigned id) {
    set_ar(a, len, size, burst, id); finish_ar();
  }
  void aw(unsigned a, unsigned len, unsigned size, unsigned burst, unsigned id) {
    d.axi_awaddr_i = a; d.axi_awlen_i = len; d.axi_awsize_i = size;
    d.axi_awburst_i = burst; d.axi_awid_i = id; d.axi_awvalid_i = 1;
    bool ready;
    do { d.eval(); ready = d.axi_awready_o; step(); } while (!ready);
    d.axi_awvalid_i = 0; d.eval();
  }
  void w(uint64_t data, unsigned strobe, bool last) {
    d.axi_wdata_i = data; d.axi_wstrb_i = strobe; d.axi_wlast_i = last; d.axi_wvalid_i = 1;
    bool ready;
    do { d.eval(); ready = d.axi_wready_o; step(); } while (!ready);
    d.axi_wvalid_i = 0; d.eval();
  }
  void b(unsigned id) {
    while (!d.axi_bvalid_o || !d.axi_bready_i) step();
    require(d.axi_bid_o == id && !d.axi_bresp_o, "write response mismatch"); step();
  }
  void drain() { while (outstanding) step(); }
  void positive() {
    aw(0, 63, 3, 1, 2);
    for (unsigned i = 0; i < 64; ++i) w(UINT64_C(0xcafe000000000000) + i, 255, i == 63);
    b(2);
    ar(0, 1, 3, 1, 3); ar(16, 1, 3, 1, 3); ar(32, 1, 3, 1, 4); ar(48, 1, 3, 1, 3);
    require(maximum == 4, "read service did not overlap");
    set_ar(64, 1, 3, 1, 5);
    for (unsigned i = 0; i < latency + 3; ++i) step();
    require(!d.axi_arready_o && d.axi_rvalid_o && ar_tick.size() == 4,
            "queue-full/stalled-response handling failed");
    // Change RAM behind a stalled beat; its already-offered payload must hold.
    aw(0, 0, 3, 1, 6); w(UINT64_C(0x1122334455667788), 255, true); b(6);
    d.axi_rready_i = 1; finish_ar(); drain();
    require(first_tick[0] - ar_tick[0] == latency, "first AR latency mismatch");
    require(first_tick[1] == finish_tick[0] + 1,
            "second request restarted latency after first RLAST");
    require(first_tick[4] - ar_tick[4] == latency, "later independent latency mismatch");
    std::cout << "OVERLAP outstanding_max=" << maximum << " first_latency=" << first_tick[0]-ar_tick[0]
              << " second_after_first_last=" << first_tick[1]-finish_tick[0]
              << " fifth_latency=" << first_tick[4]-ar_tick[4] << '\n';
    ar(0, 0, 3, 1, 1); drain();
    aw(4, 0, 2, 1, 1); w(UINT64_C(0xaabbccdd00000000), 0xf0, true); b(1);
    ar(0, 0, 3, 1, 1); drain();
    ar(12, 3, 2, 2, 2); ar(24, 3, 3, 0, 2); ar(24, 3, 3, 2, 2); drain();
    aw(120, 3, 3, 2, 1);
    for (unsigned i = 0; i < 4; ++i) w(0x100 + i, 255, i == 3);
    b(1); ar(120, 3, 3, 2, 1); drain();
    aw(144, 3, 3, 0, 1);
    for (unsigned i = 0; i < 4; ++i) w(0x200 + i, 255, i == 3);
    b(1); ar(144, 3, 3, 0, 1); drain();
    d.axi_bready_i = 0; aw(80, 0, 3, 1, 7); w(0xabcdef, 0x0c, true);
    for (unsigned i = 0; i < 5; ++i) {
      require(d.axi_bvalid_o && d.axi_bid_o == 7 && !d.axi_bresp_o && !d.axi_awready_o,
              "B payload changed while stalled"); step();
    }
    d.axi_bready_i = 1; b(7); ar(80, 0, 3, 1, 7); drain();
    ar(512, 0, 3, 1, 0); drain(); // initialized, previously untouched memory
    // Legal bursts ending exactly at a page boundary and starting on the
    // following page remain valid, including a narrow final-word access.
    ar(0xfc0, 7, 3, 1, 0); ar(0x1000, 7, 3, 1, 0); ar(0xffc, 0, 2, 1, 0); drain();
    d.axi_rready_i = 0; ar(0, 0, 3, 1, 1);
    for (unsigned i = 0; i < 3; ++i) step();
    d.reset_i = 1; step(); step(); d.reset_i = 0; d.axi_rready_i = 1;
    for (unsigned i = 0; i < latency + 3; ++i) {
      require(!d.axi_rvalid_o, "response leaked across reset"); step();
    }
    ar(0, 0, 3, 1, 1); drain();
    std::cout << "[AXI-MEM-TEST] PASS: independent latency, queue bounds, ordering, stalls, writes, bursts, reset\n";
  }
};
int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  try {
    Harness h;
    std::string mode = argc > 1 ? argv[1] : "positive";
    if (mode == "bad_wlast") { h.aw(0, 1, 3, 1, 0); h.w(0, 255, true); }
    // Match the full-top failure: a 64-byte burst shifted by a +0x10 base.
    else if (mode == "bad_boundary") h.ar(0xfd0, 7, 3, 1, 0);
    else if (mode == "bad_alignment") h.ar(1, 0, 3, 1, 0);
    else { require(mode == "positive", "unknown test mode"); h.positive(); return 0; }
    throw std::runtime_error("invalid transaction was not rejected");
  } catch (const std::exception &e) {
    std::cerr << "AXI-MEM-TEST FAIL: " << e.what() << '\n'; return 1;
  }
}
