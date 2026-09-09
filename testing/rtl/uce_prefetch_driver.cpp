// Exercise real UCE transactions with backpressure and response reordering.
// Explicit clock steps support the existing host compiler and retain an FST.
#include "Vuce_prefetch.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
constexpr unsigned hint = 9, demand = 0, memory_read = 0;
constexpr uint64_t seed = UINT64_C(0x1234567800000000);
struct Header { unsigned type, size, way; uint64_t addr; bool prefetch; };
struct Handshake { bool req, rev; };
void require(bool condition, const char *message) {
  if (!condition) throw std::runtime_error(message);
}

class Test {
  VerilatedContext context;
  Vuce_prefetch dut{&context};
  VerilatedFstC trace;
  bool checking = false, demand_active = false;
  unsigned steps = 0, release_arrays_at = 0;
  unsigned writes_at_stall = 0, completions_at_stall = 0;
  unsigned writes = 0, completions = 0, fills = 0, reverse_stalls = 0;
  std::vector<Header> sent;

  Handshake step() {
    require(++steps < 20000, "global UCE unit-test cycle limit");
    if (release_arrays_at && steps >= release_arrays_at) {
      require(writes == writes_at_stall && completions == completions_at_stall,
              "cache-array backpressure failed");
      dut.arrays_accept_i = 1;
      release_arrays_at = 0;
    }
    dut.clk_i = 0; dut.eval(); context.timeInc(5); trace.dump(context.time());
    Handshake accepted{bool(dut.req_yumi_o), bool(dut.rev_ready_o)};
    if (!dut.reset_i && dut.fwd_v_o && dut.fwd_ready_i) {
      Header h{dut.fwd_type_o, dut.fwd_size_o, dut.fwd_way_o,
               dut.fwd_addr_o, bool(dut.fwd_prefetch_o)};
      require(h.type == memory_read, "unexpected forward message type");
      require(!h.prefetch || (h.size == 3 && !(h.addr & 7) && h.way < 8),
              "hint word-size/alignment/slot encoding invalid");
      sent.push_back(h);
    }
    if (!dut.reset_i && checking) {
      require(demand_active || !(dut.data_v_o || dut.critical_o || dut.last_o
              || (dut.tag_v_o && dut.tag_opcode_o == 1)),
              "hint response escaped into architectural cache completion");
      if (dut.rev_v_i && !dut.rev_ready_o) ++reverse_stalls;
      if (dut.data_v_o && dut.arrays_accept_i) {
        require(dut.data_opcode_o == 0 && dut.data_way_o == 3 && dut.req_id_o == 9,
                "normal refill lost opcode/replacement way/request ID");
        unsigned mask = dut.data_fill_o;
        require(mask && !(mask & (mask-1)) && !(fills & mask),
                "normal response wrote duplicate/invalid fill index");
        unsigned index = 0;
        while ((1u << index) != mask) ++index;
        require(dut.data_word0_o == seed + index*2 && dut.data_word1_o == seed + index*2 + 1,
                "normal refill payload corrupted");
        fills |= mask;
        ++writes;
        if (dut.last_o) ++completions;
      }
    }
    dut.clk_i = 1; dut.eval(); context.timeInc(5); trace.dump(context.time());
    return accepted;
  }
  void cycles(unsigned n) { while (n--) step(); }
  void request(unsigned type, uint64_t addr, bool expected = true) {
    dut.req_type_i = type; dut.req_addr_i = addr; dut.req_v_i = 1;
    bool got = false;
    for (unsigned n = 0; n < (expected ? 200u : 4u); ++n)
      if (step().req) { got = true; break; }
    dut.req_v_i = 0;
    require(got == expected, "cache request acceptance mismatch");
    if (got && type != hint) {
      dut.metadata_way_i = 3; dut.metadata_v_i = 1;
      step(); dut.metadata_v_i = 0;
    }
    step();
  }
  void wait_sent(unsigned count) {
    for (unsigned n = 0; n < 200; ++n) {
      step();
      if (sent.size() == count) return;
      require(sent.size() < count, "unexpected extra memory request");
    }
    throw std::runtime_error("memory request timeout");
  }
  void wait_empty() {
    for (unsigned n = 0; n < 200; ++n) {
      step();
      if (dut.credits_empty_o) return;
    }
    throw std::runtime_error("memory credits did not drain");
  }
  void response(Header h) {
    for (unsigned beat = 0; beat < (h.prefetch ? 1u : 4u); ++beat) {
      dut.rev_type_i = h.type; dut.rev_size_i = h.size;
      dut.rev_addr_i = h.addr; dut.rev_way_i = h.way; dut.rev_prefetch_i = h.prefetch;
      dut.rev_word0_i = h.prefetch ? UINT64_C(0xbad0bad0bad0bad0) : seed + beat*2;
      dut.rev_word1_i = h.prefetch ? UINT64_C(0xbad0bad0bad0bad0) : seed + beat*2 + 1;
      dut.rev_v_i = 1;
      bool got = false;
      for (unsigned n = 0; n < 200; ++n)
        if (step().rev) { got = true; break; }
      require(got, "reverse response stalled permanently");
      dut.rev_v_i = 0;
      step();
    }
  }
  void normal_done(unsigned old_writes, unsigned old_completions) {
    for (unsigned n = 0; n < 200; ++n) {
      step();
      if (completions == old_completions + 1) {
        require(writes == old_writes + 4 && fills == 15,
                "normal demand completed without exactly one complete line");
        demand_active = false;
        return;
      }
    }
    throw std::runtime_error("normal demand never completed");
  }
public:
  Test() {
    context.traceEverOn(true);
    dut.trace(&trace, 99); trace.open("uce-prefetch.fst");
    dut.reset_i = 1; dut.arrays_accept_i = 1;
    dut.req_v_i = 0; dut.metadata_v_i = 0; dut.rev_v_i = 0; dut.fwd_ready_i = 0;
  }
  ~Test() { dut.final(); trace.close(); }
  void run(bool malformed) {
    cycles(4); dut.reset_i = 0; cycles(9);
    require(!dut.req_lock_o, "UCE initialization did not complete");
    checking = true;
    for (unsigned i = 0; i < 10; ++i)
      request(hint, 0x80010003 + uint64_t(i)*0x1000);
    require(!dut.credits_empty_o, "queued/unsent hints invisible to fences");
    request(hint, 0x8001a000, false);
    request(hint, 0x80010018); // Duplicate line merges even when the queue is full.
    require(sent.empty(), "forward backpressure was ignored");
    dut.fwd_ready_i = 1; wait_sent(10);
    for (unsigned i = 0; i < 10; ++i)
      require(sent[i].prefetch && sent[i].way == i % 8
              && sent[i].addr == ((0x80010003 + uint64_t(i)*0x1000) & ~UINT64_C(7)),
              "ten hints did not retain their queue order, wrapped tags, or addresses");
    if (malformed) {
      Header bad = sent[9];
      bad.addr ^= 8; // Same slot and cache line, but not the requested word.
      response(bad); cycles(8);
      throw std::runtime_error("malformed hint response was not rejected by RTL assertion");
    }
    // Slots 8 and 9 deliberately reuse wire tags 0 and 1. Exact address plus
    // the echoed low tag must still identify each internal queue entry.
    response(sent[9]); cycles(5);
    require(!dut.credits_empty_o, "one response drained two hints");
    request(hint, 0x8001a000); wait_sent(11);
    require(sent[10].way == sent[9].way, "returned wrapped-tag slot was not reusable");
    response(sent[8]);
    for (unsigned i = 0; i < 8; ++i) response(sent[i]);
    response(sent[10]); wait_empty();
    require(writes == 0 && completions == 0, "hint-only sequence changed L1");

    request(hint, 0x80020000); request(hint, 0x80021000); wait_sent(13);
    demand_active = true; fills = 0;
    unsigned old_writes = writes, old_completions = completions;
    request(demand, 0x80022000); wait_sent(14);
    require(!sent[13].prefetch && sent[13].size == 6, "normal demand became a hint");
    dut.arrays_accept_i = 0;
    release_arrays_at = steps + 12;
    writes_at_stall = writes; completions_at_stall = completions;
    response(sent[13]); normal_done(old_writes, old_completions);
    require(reverse_stalls > 0, "test did not exercise reverse-channel backpressure");
    require(!dut.credits_empty_o, "normal demand lost pending hint credits");
    response(sent[12]); response(sent[11]); wait_empty();

    request(hint, 0x80030008); wait_sent(15);
    demand_active = true; fills = 0;
    old_writes = writes; old_completions = completions;
    // The implementation may queue a matching demand or defer its acceptance.
    dut.req_type_i = demand; dut.req_addr_i = 0x80030000; dut.req_v_i = 1;
    bool accepted = false;
    for (unsigned n = 0; n < 12; ++n) {
      bool got = step().req;
      dut.metadata_v_i = 0;
      if (got && !accepted) {
        accepted = true; dut.req_v_i = 0;
        dut.metadata_way_i = 3; dut.metadata_v_i = 1;
      }
      require(sent.size() == 15 && !dut.credits_empty_o,
              "matching demand passed its pending hint");
    }
    dut.metadata_v_i = 0;
    if (!accepted) dut.req_v_i = 0;
    response(sent[14]);
    if (!accepted) request(demand, 0x80030000);
    wait_sent(16);
    require(!sent[15].prefetch && sent[15].addr == 0x80030000,
            "matching demand lost its normal memory transaction");
    response(sent[15]); normal_done(old_writes, old_completions); wait_empty();
    cycles(8);
    require(sent.size() == 16 && writes == 8 && completions == 2,
            "final request/response accounting mismatch");
    std::cout << "[UCE-PREFETCH] PASS: ten slots, wrapped tags, drops, merging, reordered replies, "
                 "demand routing, stalls, credits\n";
  }
};
}
int main(int argc, char **argv) {
  if (argc > 2 || (argc == 2 && std::strcmp(argv[1], "--bad-response"))) return 2;
  try { Test test; test.run(argc == 2); }
  catch (const std::exception &error) {
    std::cerr << "[UCE-PREFETCH] FAIL: " << error.what() << '\n';
    return 1;
  }
  return 0;
}
