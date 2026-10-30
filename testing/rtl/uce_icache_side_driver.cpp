#include "Vuce_icache_replay.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
constexpr uint64_t line = UINT64_C(0x80018000);
constexpr uint64_t seed = UINT64_C(0x8ac4000000000000);
void require(bool value, const char *message) {
  if (!value) throw std::runtime_error(message);
}
struct Header { unsigned type, size, way, state; uint64_t addr; bool prefetch; };

class Test {
  VerilatedContext context;
  Vuce_icache_replay dut{&context};
  VerilatedFstC trace;
  unsigned cycles = 0;
  std::vector<unsigned> masks;
  bool replay_phase = false;

  void step() {
    require(++cycles < 1000, "UCE side-buffer cycle limit");
    dut.clk_i = 0; dut.eval(); context.timeInc(5); trace.dump(context.time());
    if (replay_phase && !dut.reset_i && dut.install_state_o != 0)
      require(!dut.req_lock_o, "side-buffer retirement locked live cache arrays");
    if (!dut.reset_i && dut.data_v_o && dut.arrays_accept_i) {
      require(dut.data_opcode_o == 3,
              "side-buffer retirement emitted a live-array data write");
      unsigned beat = masks.size() % 4;
      require(dut.data_fill_o == (1u << beat), "side-buffer fill order mismatch");
      require(dut.data_word0_o == seed + beat*2
              && dut.data_word1_o == seed + beat*2 + 1,
              "side-buffer replay data mismatch");
      masks.push_back(dut.data_fill_o);
    }
    if (replay_phase)
      require(!dut.tag_v_o && !dut.stat_v_o,
              "side-buffer retirement touched tag or replacement metadata");
    dut.clk_i = 1; dut.eval(); context.timeInc(5); trace.dump(context.time());
  }
  Header enqueue_and_issue(uint64_t addr) {
    dut.replay_addr_i = addr + 0x27; dut.replay_v_i = 1;
    for (unsigned n = 0; n < 50; ++n) {
      dut.clk_i = 0; dut.eval();
      if (dut.replay_ready_o) { step(); dut.replay_v_i = 0; break; }
      step();
    }
    for (unsigned n = 0; n < 100; ++n) {
      dut.clk_i = 0; dut.eval();
      if (dut.fwd_v_o && dut.fwd_ready_i) {
        Header h{dut.fwd_type_o, dut.fwd_size_o, dut.fwd_way_o,
                 dut.fwd_state_o, dut.fwd_addr_o, bool(dut.fwd_prefetch_o)};
        replay_phase = true;
        step();
        return h;
      }
      step();
    }
    throw std::runtime_error("detached request issue timeout");
  }
  void respond_beat(const Header &h, unsigned beat) {
      dut.rev_type_i = h.type; dut.rev_size_i = h.size; dut.rev_addr_i = h.addr;
      dut.rev_way_i = h.way; dut.rev_state_i = h.state;
      dut.rev_prefetch_i = h.prefetch;
      dut.rev_word0_i = seed + beat*2; dut.rev_word1_i = seed + beat*2 + 1;
      dut.rev_v_i = 1;
      bool accepted = false;
      for (unsigned n = 0; n < 50; ++n) {
        dut.clk_i = 0; dut.eval();
        if (dut.rev_ready_o) { accepted = true; step(); break; }
        step();
      }
      require(accepted, "detached response timeout");
      dut.rev_v_i = 0; step();
  }
  void respond(const Header &h, unsigned first = 0) {
    for (unsigned beat = first; beat < 4; ++beat) {
      respond_beat(h, beat);
    }
  }
  void invalidate() {
    replay_phase = false;
    dut.req_type_i = 7; dut.req_addr_i = 0; dut.req_v_i = 1;
    bool accepted = false;
    for (unsigned n = 0; n < 50; ++n) {
      dut.clk_i = 0; dut.eval();
      if (dut.req_yumi_o) { accepted = true; step(); break; }
      step();
    }
    require(accepted, "invalidation request timeout");
    dut.req_v_i = 0; step();
  }

public:
  Test() {
    context.traceEverOn(true);
    dut.trace(&trace, 99); trace.open("uce-icache-side.fst");
    dut.reset_i = 1; dut.replay_v_i = 0; dut.req_v_i = 0;
    dut.metadata_v_i = 0; dut.arrays_accept_i = 1; dut.fwd_ready_i = 1;
    dut.rev_v_i = 0; dut.tag_state_i = 0; dut.tag_value_i = 0;
  }
  ~Test() { dut.final(); trace.close(); }
  void run() {
    step(); step(); step(); dut.reset_i = 0;
    for (unsigned n = 0; n < 10; ++n) step();
    Header h = enqueue_and_issue(line);
    require(h.prefetch && h.size == 6 && h.addr == line,
            "full-line detached request malformed");
    respond(h);
    for (unsigned n = 0; n < 100 && dut.replay_valid_o; ++n) step();
    require(!dut.replay_valid_o && masks.size() == 4,
            "completed line did not retire as four advisory beats");

    // If fence.i arrives after a partial side-buffer publication, it must
    // cancel and drain the remaining memory beats without forwarding them.
    // The cache-local buffer independently clears its partial entry at the
    // same invalidation boundary.
    Header cancelled = enqueue_and_issue(line + 0x1000);
    respond_beat(cancelled, 0);
    require(masks.size() == 5, "cancel test did not forward its first beat");
    invalidate();
    respond(cancelled, 1);
    for (unsigned n = 0; n < 50 && dut.replay_valid_o; ++n) step();
    require(!dut.replay_valid_o && masks.size() == 5,
            "fence failed to drain cancelled side-buffer beats");
    std::cout << "[UCE-ICACHE-SIDE] PASS: four-beat detached retirement, "
                 "zero live-array lock/tag/data/stat writes, fence cancellation\n";
  }
};
}

int main() {
  try { Test test; test.run(); }
  catch (const std::exception &error) {
    std::cerr << "[UCE-ICACHE-SIDE] FAIL: " << error.what() << '\n';
    return 1;
  }
  return 0;
}
