#include "Vuce_icache_replay.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
constexpr unsigned miss_load = 0, cache_inval = 7, memory_read = 0;
constexpr uint64_t seed = UINT64_C(0x91a2000000000000);
struct Header { unsigned type, size, way, state; uint64_t addr; bool prefetch; };
struct Handshake { bool request, replay, response; };
void require(bool condition, const char *message) {
  if (!condition) throw std::runtime_error(message);
}

class Test {
  VerilatedContext context;
  Vuce_icache_replay dut{&context};
  VerilatedFstC trace;
  unsigned cycles = 0, data_writes = 0, publishes = 0;
  std::vector<Header> sent;

  Handshake step() {
    require(++cycles < 4000, "global I-cache replay cycle limit");
    dut.clk_i = 0; dut.eval(); context.timeInc(5); trace.dump(context.time());
    Handshake accepted{bool(dut.req_yumi_o), bool(dut.replay_ready_o),
                       bool(dut.rev_ready_o)};
    if (!dut.reset_i && dut.fwd_v_o && dut.fwd_ready_i)
      sent.push_back({dut.fwd_type_o, dut.fwd_size_o, dut.fwd_way_o,
                      dut.fwd_state_o, dut.fwd_addr_o, bool(dut.fwd_prefetch_o)});
    if (!dut.reset_i && dut.data_v_o && dut.arrays_accept_i
        && dut.data_opcode_o == 0) {
      unsigned beat = 0, mask = dut.data_fill_o;
      require(mask && !(mask & (mask-1)), "installer emitted invalid fill mask");
      while ((1u << beat) != mask) ++beat;
      require(dut.data_word0_o == seed + beat*2
              && dut.data_word1_o == seed + beat*2 + 1,
              "installer corrupted a replay beat");
      ++data_writes;
    }
    if (!dut.reset_i && dut.tag_v_o && dut.arrays_accept_i
        && dut.tag_opcode_o == 1)
      ++publishes;
    dut.clk_i = 1; dut.eval(); context.timeInc(5); trace.dump(context.time());
    return accepted;
  }
  void tick(unsigned count) { while (count--) step(); }
  void enqueue(uint64_t addr) {
    dut.replay_addr_i = addr; dut.replay_v_i = 1;
    for (unsigned n = 0; n < 100; ++n) {
      if (step().replay) { dut.replay_v_i = 0; step(); return; }
    }
    throw std::runtime_error("replay enqueue timeout");
  }
  void request(unsigned type, uint64_t addr) {
    dut.req_type_i = type; dut.req_addr_i = addr; dut.req_v_i = 1;
    for (unsigned n = 0; n < 200; ++n) {
      if (step().request) {
        dut.req_v_i = 0;
        if (type == miss_load) {
          dut.metadata_way_i = 3; dut.metadata_v_i = 1; step();
          dut.metadata_v_i = 0;
        }
        step(); return;
      }
    }
    throw std::runtime_error("architectural cache request timeout");
  }
  void wait_sent(unsigned count) {
    for (unsigned n = 0; n < 200; ++n) {
      step();
      if (sent.size() == count) return;
      require(sent.size() < count, "unexpected extra memory request");
    }
    throw std::runtime_error("memory request timeout");
  }
  void response(const Header &h, unsigned first = 0) {
    for (unsigned beat = first; beat < 4; ++beat) {
      dut.rev_type_i = h.type; dut.rev_size_i = h.size; dut.rev_addr_i = h.addr;
      dut.rev_way_i = h.way; dut.rev_state_i = h.state;
      dut.rev_prefetch_i = h.prefetch;
      dut.rev_word0_i = seed + beat*2; dut.rev_word1_i = seed + beat*2 + 1;
      dut.rev_v_i = 1;
      bool accepted = false;
      for (unsigned n = 0; n < 100; ++n) {
        if (step().response) { accepted = true; break; }
      }
      require(accepted, "reverse replay response timeout");
      dut.rev_v_i = 0; step();
    }
  }
  void one_response_beat(const Header &h) {
    dut.rev_type_i = h.type; dut.rev_size_i = h.size; dut.rev_addr_i = h.addr;
    dut.rev_way_i = h.way; dut.rev_state_i = h.state;
    dut.rev_prefetch_i = h.prefetch;
    dut.rev_word0_i = seed; dut.rev_word1_i = seed + 1; dut.rev_v_i = 1;
    for (unsigned n = 0; n < 100; ++n) {
      if (step().response) { dut.rev_v_i = 0; step(); return; }
    }
    throw std::runtime_error("first replay response beat timeout");
  }
  void wait_idle_empty() {
    for (unsigned n = 0; n < 500; ++n) {
      step();
      if (dut.install_state_o == 0 && dut.replay_valid_o == 0
          && dut.credits_empty_o) return;
    }
    throw std::runtime_error("replay state failed to drain");
  }

public:
  Test() {
    context.traceEverOn(true);
    dut.trace(&trace, 99); trace.open("uce-icache-replay.fst");
    dut.reset_i = 1; dut.replay_v_i = 0; dut.req_v_i = 0;
    dut.metadata_v_i = 0; dut.arrays_accept_i = 1; dut.fwd_ready_i = 1;
    dut.rev_v_i = 0; dut.rev_state_i = 0;
  }
  ~Test() { dut.final(); trace.close(); }
  void run() {
    tick(4); dut.reset_i = 0; tick(10);
    require(dut.replay_ready_o && !dut.req_lock_o, "UCE initialization failed");

    // A complete reply must install all four beats before publishing its tag.
    enqueue(0x80010027); wait_sent(1);
    require(sent[0].prefetch && sent[0].size == 6
            && sent[0].addr == 0x80010000, "full-line request malformed");
    response(sent[0]); wait_idle_empty();
    require(data_writes == 4 && publishes == 1,
            "complete replay did not install exactly one full line");

    // Once a fence is accepted, an issued reply may drain but may not install.
    enqueue(0x80011000); wait_sent(2); one_response_beat(sent[1]);
    unsigned old_writes = data_writes, old_publishes = publishes;
    request(cache_inval, 0);
    response(sent[1], 1); wait_idle_empty();
    require(data_writes == old_writes && publishes == old_publishes,
            "fence-cancelled replay modified or published L1 state");

    // Architectural demand arriving during installation must abort advisory
    // work and enter the ordinary UCE path without waiting for publication.
    enqueue(0x80012000); wait_sent(3); response(sent[2]);
    for (unsigned n = 0; n < 100 && dut.install_state_o != 5; ++n) step();
    require(dut.install_state_o == 5, "test failed to reach replay fill state");
    old_publishes = publishes;
    request(miss_load, 0x80013000); wait_sent(4);
    require(!sent[3].prefetch && sent[3].addr == 0x80013000,
            "demand did not preempt replay installation");
    require(publishes == old_publishes,
            "preempted replay published before demand was accepted");
    response(sent[3]);
    for (unsigned n = 0; n < 300 && !dut.last_o; ++n) step();
    require(dut.replay_valid_o == 0, "preempted replay slot was not retired");

    std::cout << "[UCE-ICACHE-REPLAY] PASS: full-line install, fence drain-without-publish, "
                 "demand-priority abort\n";
  }
};
}

int main() {
  try { Test test; test.run(); }
  catch (const std::exception &error) {
    std::cerr << "[UCE-ICACHE-REPLAY] FAIL: " << error.what() << '\n';
    return 1;
  }
  return 0;
}
