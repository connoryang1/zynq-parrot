#include "Vicache_replay_buffer.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>

namespace {
constexpr uint64_t line = UINT64_C(0x80012000);
constexpr uint64_t seed = UINT64_C(0x7193000000000000);
void require(bool value, const char *message) {
  if (!value) throw std::runtime_error(message);
}

class Test {
  VerilatedContext context;
  Vicache_replay_buffer dut{&context};
  VerilatedFstC trace;
  unsigned cycles = 0;

  void step() {
    require(++cycles < 1000, "I-cache replay-buffer cycle limit");
    dut.clk_i = 0; dut.eval(); context.timeInc(5); trace.dump(context.time());
    dut.clk_i = 1; dut.eval(); context.timeInc(5); trace.dump(context.time());
  }
  void initialize() {
    for (unsigned index = 0; index < 4; ++index) {
      dut.init_index_i = index; dut.init_v_i = 1;
      for (unsigned n = 0; n < 20 && !dut.init_yumi_o; ++n) step();
      require(dut.init_yumi_o, "tag initialization timeout");
      step(); dut.init_v_i = 0; step();
    }
  }
  void write_beat(unsigned beat) {
    dut.replay_addr_i = line;
    dut.replay_fill_i = 1u << beat;
    dut.replay_word0_i = seed + beat*2;
    dut.replay_word1_i = seed + beat*2 + 1;
    dut.replay_v_i = 1;
    step();
    require(dut.replay_yumi_o, "replay-buffer write was not accepted");
    dut.replay_v_i = 0; step();
  }
  void write_line_burst() {
    dut.replay_addr_i = line;
    dut.replay_v_i = 1;
    for (unsigned beat = 0; beat < 4; ++beat) {
      dut.replay_fill_i = 1u << beat;
      dut.replay_word0_i = seed + beat*2;
      dut.replay_word1_i = seed + beat*2 + 1;
      step();
      require(dut.replay_yumi_o,
              "consecutive replay-buffer write was not accepted");
    }
    dut.replay_v_i = 0;
    // Drain the registered final beat before attempting a lookup.
    step();
  }
  uint64_t fetch(uint64_t addr, bool expect_hit) {
    dut.fetch_addr_i = addr; dut.fence_i = 0; dut.fetch_v_i = 1;
    bool accepted = false;
    for (unsigned n = 0; n < 20; ++n) {
      dut.clk_i = 0; dut.eval();
      if (dut.fetch_yumi_o) { accepted = true; step(); break; }
      step();
    }
    require(accepted, "fetch acceptance timeout");
    dut.fetch_v_i = 0;
    for (unsigned n = 0; n < 20; ++n) {
      step();
      if (dut.hit_v_o) {
        require(expect_hit, "partial or invalidated replay line hit");
        return dut.data_o;
      }
      if (dut.miss_req_v_o) {
        require(!expect_hit, "complete replay line missed");
        return 0;
      }
    }
    throw std::runtime_error("fetch produced neither replay hit nor demand miss");
  }
  void fence() {
    dut.fetch_addr_i = 0; dut.fence_i = 1; dut.fetch_v_i = 1;
    bool accepted = false;
    for (unsigned n = 0; n < 20; ++n) {
      dut.clk_i = 0; dut.eval();
      if (dut.fetch_yumi_o) { accepted = true; step(); break; }
      step();
    }
    require(accepted, "fence acceptance timeout");
    dut.fetch_v_i = 0; dut.fence_i = 0; step(); step(); step();
  }

public:
  Test() {
    context.traceEverOn(true);
    dut.trace(&trace, 99); trace.open("icache-replay-buffer.fst");
    dut.reset_i = 1; dut.init_v_i = 0; dut.replay_v_i = 0;
    dut.fetch_v_i = 0; dut.fence_i = 0;
  }
  ~Test() { dut.final(); trace.close(); }
  void run() {
    step(); step(); step(); dut.reset_i = 0; step(); initialize();

    // A partial line must remain architecturally invisible.
    write_beat(0); write_beat(1); write_beat(2);
    fetch(line, false);

    // Reset the held miss, then publish all four beats and verify every word.
    dut.reset_i = 1; step(); step(); dut.reset_i = 0; step(); initialize();
    write_line_burst();
    for (unsigned word = 0; word < 8; ++word)
      require(fetch(line + word*8, true) == seed + word,
              "replay-buffer word selection mismatch");

    // fence.i must invalidate the detached copy without touching cache tags.
    fence();
    fetch(line, false);
    std::cout << "[ICACHE-REPLAY-BUFFER] PASS: partial-line exclusion, "
                 "consecutive four-beat fill, eight-word execution data, "
                 "fence invalidation\n";
  }
};
}

int main() {
  try { Test test; test.run(); }
  catch (const std::exception &error) {
    std::cerr << "[ICACHE-REPLAY-BUFFER] FAIL: " << error.what() << '\n';
    return 1;
  }
  return 0;
}
