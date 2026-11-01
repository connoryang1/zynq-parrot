#include "Vuce_icache_replay.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <deque>
#include <iostream>
#include <stdexcept>

namespace {
constexpr unsigned memory_read = 0, line_size = 6;
constexpr unsigned request_count = 16;
constexpr uint64_t base = UINT64_C(0x80010000);

void require(bool condition, const char *message) {
  if (!condition) throw std::runtime_error(message);
}

struct Request {
  unsigned type, size, way, state, due, beat = 0;
  uint64_t addr;
  bool prefetch;
};

unsigned popcount(unsigned value) {
  unsigned count = 0;
  while (value) { count += value & 1u; value >>= 1; }
  return count;
}

class BurstTest {
  VerilatedContext context;
  Vuce_icache_replay dut{&context};
  VerilatedFstC trace;
  std::deque<Request> responses;
  unsigned slots, latency, cycles = 0, enqueued = 0, issued = 0, completed = 0;
  unsigned max_valid = 0, first_enqueue_cycle = 0;
  bool active = false;

  void drive_response() {
    if (responses.empty() || responses.front().due > cycles) {
      dut.rev_v_i = 0;
      return;
    }
    const Request &request = responses.front();
    dut.rev_type_i = request.type;
    dut.rev_size_i = request.size;
    dut.rev_addr_i = request.addr;
    dut.rev_way_i = request.way;
    dut.rev_state_i = request.state;
    dut.rev_prefetch_i = request.prefetch;
    dut.rev_word0_i = request.beat * 2;
    dut.rev_word1_i = request.beat * 2 + 1;
    dut.rev_v_i = 1;
  }

  void step() {
    require(++cycles < 20000, "global burst cycle limit");
    if (!dut.reset_i && active && enqueued < request_count) {
      dut.replay_v_i = 1;
      dut.replay_addr_i = base + uint64_t(enqueued) * 0x1000;
    } else {
      dut.replay_v_i = 0;
    }
    drive_response();

    dut.clk_i = 0;
    dut.eval();
    context.timeInc(5);
    trace.dump(context.time());

    const bool replay_accept = dut.replay_v_i && dut.replay_ready_o;
    const bool response_accept = dut.rev_v_i && dut.rev_ready_o;
    if (!dut.reset_i && dut.fwd_v_o && dut.fwd_ready_i) {
      require(dut.fwd_prefetch_o, "burst emitted an ordinary memory request");
      require(dut.fwd_size_o == line_size, "burst request was not a full line");
      responses.push_back({dut.fwd_type_o, dut.fwd_size_o, dut.fwd_way_o,
                           dut.fwd_state_o, cycles + latency, 0,
                           dut.fwd_addr_o, bool(dut.fwd_prefetch_o)});
      ++issued;
    }
    if (replay_accept) {
      if (!first_enqueue_cycle) first_enqueue_cycle = cycles;
      ++enqueued;
    }
    if (response_accept) {
      require(!responses.empty(), "accepted a response without a request");
      if (++responses.front().beat == 4) {
        responses.pop_front();
        ++completed;
      }
    }
    max_valid = std::max(max_valid, popcount(dut.replay_valid_o));

    dut.clk_i = 1;
    dut.eval();
    context.timeInc(5);
    trace.dump(context.time());
  }

public:
  BurstTest(unsigned slots_i, unsigned latency_i)
      : slots(slots_i), latency(latency_i) {
    context.traceEverOn(true);
    dut.trace(&trace, 99);
    trace.open("uce-icache-replay-burst.fst");
    dut.reset_i = 1;
    dut.req_v_i = 0;
    dut.metadata_v_i = 0;
    dut.arrays_accept_i = 1;
    dut.fwd_ready_i = 1;
    dut.rev_v_i = 0;
    dut.tag_state_i = 0;
    dut.tag_value_i = 0;
  }
  ~BurstTest() { dut.final(); trace.close(); }

  void run() {
    for (unsigned i = 0; i < 4; ++i) step();
    dut.reset_i = 0;
    for (unsigned i = 0; i < 10; ++i) step();
    require(dut.replay_ready_o, "UCE initialization failed");
    active = true;
    while (completed < request_count || dut.replay_valid_o
           || !dut.credits_empty_o || !responses.empty())
      step();
    require(enqueued == request_count && issued == request_count
            && completed == request_count,
            "burst accounting mismatch");
    require(max_valid == slots, "burst did not exercise every configured slot");
    std::cout << "[UCE-ICACHE-BURST] PASS: slots=" << slots
              << " requests=" << request_count
              << " latency=" << latency
              << " cycles=" << cycles - first_enqueue_cycle + 1
              << " max_valid=" << max_valid << '\n';
  }
};
}  // namespace

int main(int argc, char **argv) {
  try {
    require(argc == 3, "usage: burst-test <configured-slots> <latency>");
    unsigned slots = std::strtoul(argv[1], nullptr, 0);
    unsigned latency = std::strtoul(argv[2], nullptr, 0);
    require(latency > 0, "response latency must be positive");
    BurstTest test(slots, latency);
    test.run();
  } catch (const std::exception &error) {
    std::cerr << "[UCE-ICACHE-BURST] FAIL: " << error.what() << '\n';
    return 1;
  }
  return 0;
}
