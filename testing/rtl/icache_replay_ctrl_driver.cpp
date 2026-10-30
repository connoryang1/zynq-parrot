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

    std::vector<uint64_t> accepted;
    bool direct_tested = false;
    for (unsigned cycle = 0; cycle < 100 && accepted.size() < expected.size(); ++cycle) {
      dut.eval();
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
    }

    require(direct_tested, "prefix sequencer never produced an entry");
    require(accepted.size() == expected.size(), "prefix sequence did not drain");
    for (unsigned i = 0; i < expected.size(); ++i)
      require(accepted[i] == expected[i], "prefix table order/data mismatch");

    dut.eval();
    const uint64_t status = dut.status_o;
    require(!(status & (1ULL << 1)), "controller remained busy after final admission");
    require(((status >> 4) & 0x1ff) == 4, "configured count status mismatch");
    require(((status >> 22) & 0xffff) == 4, "accepted counter mismatch");
    require(((status >> 38) & 0xff) == 1, "trigger counter mismatch");
    require(((status >> 46) & 0xff) == 1, "dropped-trigger counter mismatch");

    pulse(dut.clear_counters_i);
    const uint64_t cleared = dut.status_o;
    require(((cleared >> 22) & 0xffffffffULL) == 0,
            "counter clear did not clear accepted/trigger/drop fields");
    require(((cleared >> 4) & 0x1ff) == 4,
            "counter clear modified configured prefix length");

    std::cout << "[ICACHE-REPLAY-CTRL] PASS: ordered table replay, backpressure, "
                 "direct priority, retrigger drop, counters\n";
    trace.close();
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "[ICACHE-REPLAY-CTRL] FAIL: " << error.what() << "\n";
    trace.close();
    return 1;
  }
}
