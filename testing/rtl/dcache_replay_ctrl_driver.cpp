#include "Vbp_dcache_replay_ctrl.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

static void require(bool condition, const char *message) {
  if (!condition) throw std::runtime_error(message);
}

int main(int argc, char **argv) {
  VerilatedContext context;
  context.commandArgs(argc, argv);
  Vbp_dcache_replay_ctrl dut{&context};

  auto half = [&](int clock) {
    dut.clk_i = clock;
    dut.eval();
    context.timeInc(1);
  };
  auto tick = [&]() { half(0); half(1); };
  auto pulse = [&](CData &signal) { signal = 1; tick(); signal = 0; tick(); };

  try {
    dut.reset_i = 1;
    dut.entry_write_v_i = 0;
    dut.config_write_v_i = 0;
    dut.trigger_v_i = 0;
    dut.replay_yumi_i = 0;
    dut.replay_accepted_i = 0;
    dut.downstream_outstanding_i = 0;
    dut.downstream_complete_i = 0;
    dut.clear_counters_i = 0;
    tick(); tick();
    dut.reset_i = 0;
    tick();

    std::array<uint64_t, 32> expected{};
    for (unsigned i = 0; i < expected.size(); ++i) {
      expected[i] = 0x80010000ULL + 64*i;
      dut.entry_write_slot_i = 2;
      dut.entry_write_index_i = i;
      dut.entry_write_paddr_i = expected[i];
      pulse(dut.entry_write_v_i);
    }
    dut.config_write_slot_i = 2;
    dut.config_write_count_i = expected.size();
    dut.config_write_delay_i = 12;
    dut.config_write_gap_i = 2;
    pulse(dut.config_write_v_i);

    // A single wakeup command is accepted independently of replay pressure.
    dut.trigger_slot_i = 2;
    dut.trigger_v_i = 1;
    tick();
    dut.trigger_v_i = 0;

    for (unsigned i = 0; i < 10; ++i) {
      require(!dut.replay_v_o, "replay escaped before configured delay");
      tick();
    }

    std::vector<uint64_t> consumed;
    unsigned first_valid_cycle = 0;
    for (unsigned cycle = 10; cycle < 600 && consumed.size() < expected.size(); ++cycle) {
      dut.eval();
      if (dut.replay_v_o && first_valid_cycle == 0)
        first_valid_cycle = cycle;

      // Hold the first entry to prove that downstream backpressure neither
      // loses nor advances the synchronous table stream.
      if (dut.replay_v_o && consumed.empty() && cycle < first_valid_cycle + 3) {
        const uint64_t held = dut.replay_paddr_o;
        dut.replay_yumi_i = 0;
        tick();
        require(dut.replay_v_o && dut.replay_paddr_o == held,
                "entry changed while replay was backpressured");
        continue;
      }

      if (dut.replay_v_o) {
        dut.replay_yumi_i = 1;
        // Exercise the filtered accounting path without changing ordering.
        dut.replay_accepted_i = (consumed.size() != 7);
        consumed.push_back(dut.replay_paddr_o);
      } else {
        dut.replay_yumi_i = 0;
        dut.replay_accepted_i = 0;
      }
      tick();
      dut.replay_yumi_i = 0;
    }

    require(first_valid_cycle >= 12, "configured replay delay was shortened");
    require(consumed.size() == expected.size(), "32-entry footprint did not drain");
    for (unsigned i = 0; i < expected.size(); ++i)
      require(consumed[i] == expected[i], "footprint replay order/data mismatch");

    // Fill the two-entry command queue while a long-delay command is active;
    // a fourth trigger must be dropped rather than corrupting queued tags.
    dut.config_write_slot_i = 2;
    dut.config_write_count_i = 1;
    dut.config_write_delay_i = 40;
    dut.config_write_gap_i = 0;
    pulse(dut.config_write_v_i);
    for (unsigned slot : {2U, 2U, 2U, 2U}) {
      dut.trigger_slot_i = slot;
      pulse(dut.trigger_v_i);
    }

    const uint64_t status = dut.status_o;
    require(((status >> 10) & 0xffff) == 31, "accepted-entry counter mismatch");
    require(((status >> 26) & 0xffff) == 1, "filtered-entry counter mismatch");
    require(((status >> 42) & 0xff) == 4, "accepted-trigger counter mismatch");
    require(((status >> 50) & 0xff) == 1, "dropped-trigger counter mismatch");

    dut.downstream_outstanding_i = 2;
    dut.downstream_complete_i = 1;
    dut.eval();
    require(((dut.status_o >> 60) & 0x3) == 2,
            "downstream outstanding status mismatch");
    require(((dut.status_o >> 62) & 0x3) == 1,
            "downstream complete status mismatch");

    pulse(dut.clear_counters_i);
    require(((dut.status_o >> 10) & 0xffffffffffffULL) == 0,
            "counter clear did not clear replay/trigger counters");

    std::cout << "[DCACHE-REPLAY-CTRL] PASS: tagged command queue, delayed "
                 "32-entry replay, gap throttle, backpressure, filtering, counters\n";
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "[DCACHE-REPLAY-CTRL] FAIL: " << error.what() << "\n";
    return 1;
  }
}

