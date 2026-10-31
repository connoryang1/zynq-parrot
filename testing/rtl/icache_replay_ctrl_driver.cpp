#include "Vbp_icache_replay_ctrl.h"
#include "verilated.h"
#include "verilated_fst_c.h"
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
  context.traceEverOn(true);
  Vbp_icache_replay_ctrl dut{&context};
  VerilatedFstC trace;
  dut.trace(&trace, 99);
  trace.open("icache-replay-ctrl.fst");

  auto half = [&](int clock) {
    dut.clk_i = clock;
    dut.eval();
    trace.dump(context.time());
    context.timeInc(1);
  };
  auto tick = [&]() { half(0); half(1); };
  auto pulse = [&](CData &signal) { signal = 1; tick(); signal = 0; tick(); };

  try {
    dut.reset_i = 1;
    dut.direct_v_i = 0;
    dut.entry_write_v_i = 0;
    dut.count_write_v_i = 0;
    dut.clear_counters_i = 0;
    dut.trigger_v_i = 0;
    dut.resident_i = 0;
    dut.replay_ready_i = 1;
    tick(); tick();
    dut.reset_i = 0;
    tick();

    const std::array<uint64_t, 4> expected{
      0x80001000, 0x80002000, 0x80003000, 0x80004000
    };
    for (unsigned i = 0; i < expected.size(); ++i) {
      dut.entry_write_index_i = i;
      dut.entry_write_paddr_i = expected[i];
      pulse(dut.entry_write_v_i);
    }
    dut.count_i = expected.size();
    pulse(dut.count_write_v_i);

    // Launch once, then deliberately retrigger while the synchronous table
    // read is active. The second trigger must be counted and ignored.
    dut.replay_ready_i = 0;
    dut.trigger_v_i = 1;
    tick();
    dut.trigger_v_i = 0;
    tick();
    pulse(dut.trigger_v_i);

    const std::array<uint64_t, 2> expected_accepted{
      expected[0], expected[2]
    };
    std::vector<uint64_t> queried;
    std::vector<uint64_t> accepted;
    bool direct_tested = false;
    for (unsigned cycle = 0; cycle < 120; ++cycle) {
      dut.eval();
      dut.resident_i = dut.resident_query_v_o
        && (dut.resident_query_paddr_o == expected[1]
            || dut.resident_query_paddr_o == expected[3]);
      dut.eval();
      if (dut.resident_query_v_o)
        queried.push_back(dut.resident_query_paddr_o);

      if (dut.replay_v_o && !direct_tested) {
        dut.replay_ready_i = 0;
        tick(); tick();
        require(dut.replay_v_o, "prefix entry was not held under backpressure");

        dut.replay_ready_i = 1;
        dut.direct_paddr_i = 0x8000f000;
        dut.direct_v_i = 1;
        dut.eval();
        require(dut.direct_ready_o && dut.replay_v_o
                && dut.replay_paddr_o == 0x8000f000,
                "direct ingress did not take priority");
        tick();
        dut.direct_v_i = 0;
        dut.eval();
        require(dut.replay_v_o && dut.replay_paddr_o == expected[0],
                "direct ingress consumed the held prefix entry");
        direct_tested = true;
      }

      dut.eval();
      if (dut.replay_v_o && dut.replay_ready_i && !dut.direct_v_i)
        accepted.push_back(dut.replay_paddr_o);
      tick();
      if (!(dut.status_o & (1ULL << 1)) && queried.size() == expected.size() - 1)
        break;
    }

    require(direct_tested, "prefix sequencer never produced an entry");
    // Entry zero is queried while the deliberate retrigger pulse is being
    // driven above; resident_i is intentionally low then. Observe the three
    // subsequent queries explicitly here.
    require(queried.size() == expected.size() - 1,
            "resident query sequence did not drain");
    for (unsigned i = 0; i < queried.size(); ++i)
      require(queried[i] == expected[i + 1], "resident query order/data mismatch");
    require(accepted.size() == expected_accepted.size(),
            "resident entries were not suppressed from replay");
    for (unsigned i = 0; i < expected_accepted.size(); ++i)
      require(accepted[i] == expected_accepted[i], "prefix table order/data mismatch");

    dut.eval();
    const uint64_t status = dut.status_o;
    require(!(status & (1ULL << 1)), "controller remained busy after final admission");
    require(((status >> 4) & 0x1ff) == 4, "configured count status mismatch");
    require(((status >> 22) & 0xffff) == 2, "accepted counter mismatch");
    require(((status >> 38) & 0xff) == 1, "trigger counter mismatch");
    require(((status >> 46) & 0xff) == 1, "dropped-trigger counter mismatch");
    require(((status >> 55) & 0x1ff) == 2, "resident-drop counter mismatch");

    pulse(dut.clear_counters_i);
    const uint64_t cleared = dut.status_o;
    require(((cleared >> 22) & 0xffffffffULL) == 0,
            "counter clear did not clear accepted/trigger/drop fields");
    require(((cleared >> 55) & 0x1ff) == 0,
            "counter clear did not clear resident-drop field");
    require(((cleared >> 4) & 0x1ff) == 4,
            "counter clear modified configured prefix length");

    std::cout << "[ICACHE-REPLAY-CTRL] PASS: ordered table replay, resident "
                 "suppression, backpressure, direct priority, retrigger drop, counters\n";
    trace.close();
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "[ICACHE-REPLAY-CTRL] FAIL: " << error.what() << "\n";
    trace.close();
    return 1;
  }
}
