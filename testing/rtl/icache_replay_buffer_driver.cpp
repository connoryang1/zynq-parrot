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
  return (((line_addr >> 0) ^ (line_addr >> 3) ^ (line_addr >> 13)
           ^ (line_addr >> 18) ^ (line_addr >> 24)) & 1)
         | ((((line_addr >> 2) ^ (line_addr >> 4) ^ (line_addr >> 9)
              ^ (line_addr >> 11) ^ (line_addr >> 24)) & 1) << 1)
         | ((((line_addr >> 1) ^ (line_addr >> 9)
              ^ (line_addr >> 24)) & 1) << 2)
         | ((((line_addr >> 3) ^ (line_addr >> 5) ^ (line_addr >> 8)
              ^ (line_addr >> 9) ^ (line_addr >> 18)) & 1) << 3);
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

    // Fill exactly two ways in each of the sixteen hash banks. A third line in
    // one nonzero bank must replace only that bank's oldest entry. Selecting
    // addresses by bank keeps this capacity/replacement contract independent
    // of any accidental distribution of consecutive physical lines.
    dut.reset_i = 1; step(); step(); dut.reset_i = 0; step(); initialize();
    uint64_t bank_lines[16][3] = {};
    unsigned bank_counts[16] = {};
    unsigned total_found = 0;
    for (unsigned offset = 0; offset < 4096 && total_found < 48; ++offset) {
      const uint64_t candidate = line + uint64_t(offset)*64;
      const unsigned bank = replay_bank(candidate);
      if (bank_counts[bank] < 3) {
        bank_lines[bank][bank_counts[bank]++] = candidate;
        ++total_found;
      }
    }
    require(total_found == 48,
            "bank hash search did not find three lines in every bank");
    for (unsigned bank = 0; bank < 16; ++bank)
      for (unsigned way = 0; way < 2; ++way)
        write_line_burst(bank_lines[bank][way], seed + (bank*2 + way)*16);
    for (unsigned bank = 0; bank < 16; ++bank)
      for (unsigned way = 0; way < 2; ++way) {
        require(query(bank_lines[bank][way]),
                "32-entry banked capacity lost a completed line");
        require(fetch(bank_lines[bank][way], true)
                  == seed + (bank*2 + way)*16,
                "32-entry banked capacity returned incorrect data");
      }
    constexpr unsigned replacement_bank = 11;
    write_line_burst(bank_lines[replacement_bank][2], seed + 32*16);
    require(!query(bank_lines[replacement_bank][0]),
            "third same-bank line did not replace the oldest way");
    for (unsigned bank = 0; bank < 16; ++bank)
      for (unsigned way = bank == replacement_bank ? 1 : 0; way < 2; ++way)
        require(query(bank_lines[bank][way]),
                "third same-bank line replaced another bank or newer way");
    require(query(bank_lines[replacement_bank][2]),
            "third same-bank line was not published");
    require(fetch(bank_lines[replacement_bank][2], true) == seed + 32*16,
            "third same-bank line returned incorrect data");
    std::cout << "[ICACHE-REPLAY-BUFFER] PASS: partial-line exclusion, "
                 "completed-residency query, consecutive four-beat fill, "
                 "eight-word execution data, fence invalidation, "
                 "32-entry capacity, and sixteen-bank/two-way replacement\n";
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
