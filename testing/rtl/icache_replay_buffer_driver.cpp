#include "Vicache_replay_buffer.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>

namespace {
constexpr uint64_t line = UINT64_C(0x80012000);
constexpr uint64_t seed = UINT64_C(0x7193000000000000);
unsigned replay_bank(uint64_t addr) {
  const uint64_t line_addr = addr >> 6;
  return (((line_addr >> 0) ^ (line_addr >> 13)) & 1)
         | ((((line_addr >> 3) ^ (line_addr >> 6)) & 1) << 1);
}
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
  void write_line_burst(uint64_t addr = line, uint64_t word_seed = seed) {
    dut.replay_addr_i = addr;
    dut.replay_v_i = 1;
    for (unsigned beat = 0; beat < 4; ++beat) {
      dut.replay_fill_i = 1u << beat;
      dut.replay_word0_i = word_seed + beat*2;
      dut.replay_word1_i = word_seed + beat*2 + 1;
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
  bool query(uint64_t addr) {
    dut.query_addr_i = addr;
    dut.query_v_i = 1;
    dut.eval();
    const bool hit = dut.query_hit_o;
    dut.query_v_i = 0;
    dut.eval();
    return hit;
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
    dut.fetch_v_i = 0; dut.fence_i = 0; dut.query_v_i = 0;
  }
  ~Test() { dut.final(); trace.close(); }
  void run() {
    step(); step(); step(); dut.reset_i = 0; step(); initialize();

    // A partial line must remain architecturally invisible.
    write_beat(0); write_beat(1); write_beat(2);
    require(!query(line), "partial replay line reported resident");
    fetch(line, false);

    // Reset the held miss, then publish all four beats and verify every word.
    dut.reset_i = 1; step(); step(); dut.reset_i = 0; step(); initialize();
    write_line_burst();
    require(query(line), "complete replay line not reported resident");
    for (unsigned word = 0; word < 8; ++word)
      require(fetch(line + word*8, true) == seed + word,
              "replay-buffer word selection mismatch");

    // fence.i must invalidate the detached copy without touching cache tags.
    fence();
    require(!query(line), "invalidated replay line reported resident");
    fetch(line, false);

    // Fill the configured 32-entry capacity exactly. The next distinct line
    // must replace slot zero while every other completed entry remains live.
    dut.reset_i = 1; step(); step(); dut.reset_i = 0; step(); initialize();
    for (unsigned slot = 0; slot < 32; ++slot)
      write_line_burst(line + slot*64, seed + slot*16);
    for (unsigned slot = 0; slot < 32; ++slot) {
      const uint64_t addr = line + slot*64;
      require(query(addr), "32-entry replay capacity lost a completed line");
      require(fetch(addr, true) == seed + slot*16,
              "32-entry replay capacity returned incorrect data");
    }
    write_line_burst(line + 32*64, seed + 32*16);
    require(!query(line), "33rd replay line did not replace slot zero");
    require(query(line + 64), "33rd replay line replaced the wrong old slot");
    require(query(line + 32*64), "33rd replay line was not published");

    // Force nine distinct lines through one hash bank. Eight ways must remain
    // simultaneously resident, and the ninth must replace only that bank's
    // oldest entry. This catches a design that passes the evenly distributed
    // sequential-capacity test but still uses a global replacement pointer.
    dut.reset_i = 1; step(); step(); dut.reset_i = 0; step(); initialize();
    uint64_t same_bank_lines[9] = {};
    unsigned same_bank_count = 0;
    for (unsigned offset = 0; same_bank_count < 9; ++offset) {
      const uint64_t candidate = line + uint64_t(offset)*64;
      if (replay_bank(candidate) == replay_bank(line))
        same_bank_lines[same_bank_count++] = candidate;
    }
    for (unsigned way = 0; way < 8; ++way)
      write_line_burst(same_bank_lines[way], seed + way*16);
    for (unsigned way = 0; way < 8; ++way)
      require(query(same_bank_lines[way]),
              "one-bank fill lost an entry before reaching eight ways");
    write_line_burst(same_bank_lines[8], seed + 8*16);
    require(!query(same_bank_lines[0]),
            "ninth same-bank line did not replace the oldest way");
    for (unsigned way = 1; way < 8; ++way)
      require(query(same_bank_lines[way]),
              "ninth same-bank line replaced a non-oldest way");
    require(query(same_bank_lines[8]),
            "ninth same-bank line was not published");
    std::cout << "[ICACHE-REPLAY-BUFFER] PASS: partial-line exclusion, "
                 "completed-residency query, consecutive four-beat fill, "
                 "eight-word execution data, fence invalidation, "
                 "32-entry capacity, and four-bank/eight-way replacement\n";
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
