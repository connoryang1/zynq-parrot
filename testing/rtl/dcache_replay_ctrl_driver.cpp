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
    dut.trigger_follow_i = 0;
    dut.replay_yumi_i = 0;
    dut.replay_accepted_i = 0;
    dut.downstream_outstanding_i = 0;
    dut.downstream_complete_i = 0;
    dut.follow_ready_i = 1;
    dut.follow_active_i = 0;
    dut.follow_configured_i = 1;
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

    tick();
    require(((dut.status_o >> 58) & 0x3) == 1,
            "freshly drained replay did not enter the recent-age bucket");
    for (unsigned i = 0; i < 512; ++i) tick();
    require(((dut.status_o >> 58) & 0x3) == 2,
            "drain age did not enter the 512-cycle bucket");
    for (unsigned i = 0; i < 1536; ++i) tick();
    require(((dut.status_o >> 58) & 0x3) == 3,
            "drain age did not enter the 2048-cycle bucket");

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

    require(((dut.status_o >> 58) & 0x3) == 0,
            "new replay did not clear the completed-drain age");

    const uint64_t status = dut.status_o;
    require(((status >> 10) & 0xffff) == 31, "accepted-entry counter mismatch");
    require(((status >> 26) & 0xffff) == 1, "filtered-entry counter mismatch");
    require(((status >> 42) & 0xff) == 4, "accepted-trigger counter mismatch");
    require(((status >> 50) & 0xff) == 1, "dropped-trigger counter mismatch");

    dut.downstream_outstanding_i = 2;
    dut.downstream_complete_i = 1;
    dut.eval();
    require(((dut.status_o >> 60) & 0x7) == 2,
            "downstream outstanding status mismatch");
    require(((dut.status_o >> 63) & 0x1) == 1,
            "downstream complete status mismatch");

    pulse(dut.clear_counters_i);
    require(((dut.status_o >> 10) & 0xffffffffffffULL) == 0,
            "counter clear did not clear replay/trigger counters");

    // Reset away the queue-pressure case, then prove instruction-first
    // ordering. A follow command must trigger the prefix before exposing any
    // data entry, then release data only after observing the prefix active.
    // The independent lanes must overlap rather than postponing data until
    // the instruction responses drain. A queued command cannot overtake the
    // instruction launch boundary.
    dut.reset_i = 1;
    dut.downstream_outstanding_i = 0;
    dut.downstream_complete_i = 0;
    dut.follow_active_i = 0;
    dut.follow_configured_i = 1;
    dut.follow_ready_i = 0;
    tick(); tick();
    dut.reset_i = 0;
    tick();

    dut.entry_write_slot_i = 1;
    dut.entry_write_index_i = 0;
    dut.entry_write_paddr_i = 0x80020000ULL;
    pulse(dut.entry_write_v_i);
    dut.config_write_slot_i = 1;
    dut.config_write_count_i = 1;
    dut.config_write_delay_i = 0;
    dut.config_write_gap_i = 0;
    pulse(dut.config_write_v_i);

    dut.trigger_slot_i = 1;
    dut.trigger_follow_i = 1;
    pulse(dut.trigger_v_i);
    dut.trigger_follow_i = 0;
    pulse(dut.trigger_v_i);

    unsigned replay_count = 0;
    for (unsigned cycle = 0; cycle < 3; ++cycle) {
      require(!dut.replay_v_o,
              "data replay escaped before instruction trigger");
      require(!dut.follow_trigger_o,
              "instruction trigger ignored prefix-controller backpressure");
      tick();
    }

    // Model unrelated kernel data traffic at wakeup. It must not delay the
    // independent instruction trigger, but followed data must remain held
    // until the older D-UCE state drains.
    dut.downstream_outstanding_i = 2;
    dut.downstream_complete_i = 1;
    dut.follow_ready_i = 1;
    dut.eval();
    require(dut.follow_trigger_o,
            "D-UCE traffic postponed the independent instruction trigger");
    require(!dut.replay_v_o,
            "data replay overlapped instruction trigger");
    tick();
    require(!dut.follow_trigger_o, "instruction trigger lasted more than one cycle");

    dut.follow_active_i = 1;
    for (unsigned cycle = 0; cycle < 3; ++cycle) {
      require(!dut.replay_v_o,
              "followed data escaped before older D-UCE state drained");
      tick();
    }
    dut.downstream_outstanding_i = 0;
    dut.downstream_complete_i = 0;
    for (unsigned cycle = 0; cycle < 40 && replay_count < 2; ++cycle) {
      if (dut.replay_v_o) {
        require(dut.follow_active_i,
                "data replay waited for prefix drain instead of overlapping");
        dut.replay_yumi_i = 1;
        dut.replay_accepted_i = 1;
        ++replay_count;
      }
      tick();
      dut.replay_yumi_i = 0;
      dut.replay_accepted_i = 0;
    }
    require(replay_count == 2,
            "overlapped data and queued command did not both drain");
    dut.follow_active_i = 0;
    for (unsigned i = 0; i < 3; ++i) {
      require(!dut.follow_trigger_o,
              "non-follow command emitted an instruction trigger");
      tick();
    }

    // A follow command with a deliberately empty prefix still emits the one
    // architectural trigger, observes the idle boundary, and then releases
    // data. This is the disabled-instruction control used by Linux A/B runs.
    dut.reset_i = 1;
    dut.follow_active_i = 0;
    dut.follow_configured_i = 0;
    dut.follow_ready_i = 1;
    tick(); tick();
    dut.reset_i = 0;
    tick();

    dut.entry_write_slot_i = 0;
    dut.entry_write_index_i = 0;
    dut.entry_write_paddr_i = 0x80030000ULL;
    pulse(dut.entry_write_v_i);
    dut.config_write_slot_i = 0;
    dut.config_write_count_i = 1;
    dut.config_write_delay_i = 0;
    dut.config_write_gap_i = 0;
    pulse(dut.config_write_v_i);

    dut.trigger_slot_i = 0;
    dut.trigger_follow_i = 1;
    pulse(dut.trigger_v_i);
    dut.trigger_follow_i = 0;

    unsigned empty_prefix_triggers = 0;
    unsigned empty_prefix_replays = 0;
    for (unsigned cycle = 0; cycle < 40 && empty_prefix_replays == 0; ++cycle) {
      dut.eval();
      if (dut.follow_trigger_o) {
        require(empty_prefix_triggers == 0,
                "empty prefix emitted more than one instruction trigger");
        require(!dut.replay_v_o,
                "empty-prefix data overlapped its instruction trigger");
        ++empty_prefix_triggers;
      }
      if (dut.replay_v_o) {
        require(empty_prefix_triggers == 1,
                "empty-prefix data escaped before its instruction trigger");
        dut.replay_yumi_i = 1;
        dut.replay_accepted_i = 1;
        ++empty_prefix_replays;
      }
      tick();
      dut.replay_yumi_i = 0;
      dut.replay_accepted_i = 0;
    }
    require(empty_prefix_triggers == 1,
            "empty prefix did not emit exactly one instruction trigger");
    require(empty_prefix_replays == 1,
            "empty prefix deadlocked the following data replay");

    std::cout << "[DCACHE-REPLAY-CTRL] PASS: tagged command queue, delayed "
                 "32-entry replay, gap throttle, backpressure, filtering, "
                 "counters, drain-age telemetry, instruction-first launch, "
                 "early I/D overlap, empty-prefix release\n";
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "[DCACHE-REPLAY-CTRL] FAIL: " << error.what() << "\n";
    return 1;
  }
}

