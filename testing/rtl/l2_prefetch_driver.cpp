// Ordered mock cache banks isolate controller metadata, arbitration and pumps.
// Explicit clocks work with the repository's existing C++ compiler.
#include "Vl2_prefetch.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <array>
#include <cstdint>
#include <deque>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void require(bool value, const char *message) {
  if (!value) throw std::runtime_error(message);
}
struct Request {
  uint64_t addr;
  unsigned size, way, serial, issued = 0, returned = 0, acknowledged = 0, operation = 0;
  bool prefetch;
  unsigned beats() const { return size == 6 ? 8 : 1; }
  unsigned output_beats() const { return operation == 1 ? 1 : beats(); }
  uint64_t data(unsigned beat) const { return (uint64_t(serial) << 32) | beat; }
};
struct Response { uint64_t data; bool internal; uint64_t addr; };
struct Beat {
  uint64_t addr, data;
  unsigned size, way, operation;
  bool prefetch;
  bool operator==(const Beat &b) const {
    return addr == b.addr && data == b.data && size == b.size
           && way == b.way && operation == b.operation && prefetch == b.prefetch;
  }
};
class Test {
  VerilatedContext context;
  Vl2_prefetch dut{&context};
  VerilatedFstC trace;
  std::array<std::deque<Response>, 2> banks;
  std::array<std::deque<uint64_t>, 2> commands;
  std::map<uint64_t, Request> requests;
  std::vector<Beat> replies;
  std::array<bool, 2> hold{{false, false}};
  unsigned steps = 0, serial = 0, packet_count = 0, internal_count = 0;
  bool stalled = false, unrestricted = false;
  bool check_write_lock = false;
  Beat last_stall{};

  bool step() {
    require(++steps < 15000, "L2 unit global cycle bound");
    dut.bank_accept_i = 0;
    dut.bank_response_v_i = 0;
    for (unsigned b = 0; b < 2; ++b) {
      if (unrestricted || banks[b].size() < 3) dut.bank_accept_i |= 1u << b;
      if (!hold[b] && !banks[b].empty()) dut.bank_response_v_i |= 1u << b;
    }
    dut.bank_data0_i = banks[0].empty() ? 0 : banks[0].front().data;
    dut.bank_data1_i = banks[1].empty() ? 0 : banks[1].front().data;
    dut.clk_i = 0; dut.eval(); context.timeInc(5); trace.dump(context.time());
    bool accepted = dut.fwd_v_i && dut.fwd_ready_o;
    if (!dut.reset_i) {
      Beat beat{dut.rev_addr_o, dut.rev_data_o, dut.rev_size_o,
                dut.rev_way_o, dut.rev_write_o ? 1u : dut.rev_amo_o ? 2u : 0u,
                bool(dut.rev_prefetch_o)};
      if (stalled)
        require(dut.rev_v_o && beat == last_stall, "stalled response payload/header changed");
      stalled = dut.rev_v_o && !dut.rev_ready_i;
      if (stalled) last_stall = beat;
      if (dut.rev_v_o && dut.rev_ready_i) {
        auto it = requests.find(beat.addr);
        require(it != requests.end(), "internal cache response leaked onto BedRock");
        Request &r = it->second;
        require(beat.size == r.size && beat.way == r.way && beat.prefetch == r.prefetch
                && beat.operation == r.operation,
                "response metadata corrupted or associated with wrong bank");
        require(r.returned < r.output_beats() && (r.operation == 1 || beat.data == r.data(r.returned)),
                "response data reordered, duplicated, or lost");
        if (check_write_lock && beat.prefetch)
          for (const auto &pair : requests)
            require(pair.second.operation != 1 || pair.second.acknowledged == pair.second.beats(),
                    "prefetch escaped before all store bank acknowledgements completed");
        ++r.returned;
        replies.push_back(beat);
      }
      // Sample both handshakes before changing the mock queues.
      for (unsigned b = 0; b < 2; ++b) {
        if ((dut.bank_response_yumi_o >> b) & 1) {
          require(((dut.bank_response_v_i >> b) & 1) && !banks[b].empty(),
                  "controller consumed an absent bank response");
          if (banks[b].front().internal) ++internal_count;
          else ++requests.at(banks[b].front().addr).acknowledged;
          banks[b].pop_front();
        }
        if ((dut.bank_pkt_v_o & dut.bank_accept_i) & (1u << b)) {
          unsigned opcode = b ? dut.bank_opcode1_o : dut.bank_opcode0_o;
          if (opcode == dut.opcode_tagst_o || opcode == dut.opcode_aflinv_o) {
            banks[b].push_back({UINT64_C(0xdeadbeef), true, 0});
          } else {
            require(!commands[b].empty(), "unexpected cache command");
            Request &r = requests.at(commands[b].front());
            unsigned expected = r.operation == 2 ? dut.opcode_amoswap_o
              : r.operation == 1 ? (r.size == 6 ? dut.opcode_sm_o : dut.opcode_sd_o)
              : (r.size == 6 ? dut.opcode_lm_o : dut.opcode_ld_o);
            require(opcode == expected, "cache opcode mismatch");
            if (r.operation)
              require((b ? dut.bank_data1_o : dut.bank_data0_o) == r.data(r.issued),
                      "store/AMO input data changed or reordered");
            banks[b].push_back({r.data(r.issued), false, r.addr});
            ++packet_count;
            if (++r.issued == r.beats()) commands[b].pop_front();
          }
        }
      }
    }
    dut.clk_i = 1; dut.eval(); context.timeInc(5); trace.dump(context.time());
    return accepted;
  }
  void cycles(unsigned n) { while (n--) step(); }
  void idle() {
    for (unsigned n = 0; n < 300; ++n) {
      step();
      bool complete = true;
      for (const auto &pair : requests)
        complete &= pair.second.returned == pair.second.output_beats()
                    && pair.second.acknowledged == pair.second.beats();
      if (complete && banks[0].empty() && banks[1].empty() && dut.ready_o) {
        cycles(4); return;
      }
    }
    throw std::runtime_error("controller did not drain all expected responses");
  }
  void start(uint64_t addr, bool prefetch, unsigned size = 3, unsigned operation = 0) {
    require(!requests.count(addr), "test reused request address");
    Request r{addr, size, prefetch ? 1u : 2u, ++serial, 0, 0, 0, operation, prefetch};
    requests.emplace(addr, r);
    commands[(addr >> 6) & 1].push_back(addr);
    dut.fwd_addr_i = addr; dut.fwd_size_i = size;
    dut.fwd_way_i = r.way; dut.fwd_prefetch_i = prefetch; dut.fwd_v_i = 1;
    dut.fwd_write_i = operation == 1; dut.fwd_amo_i = operation == 2;
    dut.fwd_data_i = r.data(0);
  }
  void send(uint64_t addr, bool prefetch, unsigned size = 3, unsigned operation = 0) {
    start(addr, prefetch, size, operation);
    unsigned beats = operation == 1 ? requests.at(addr).beats() : 1;
    for (unsigned beat = 0; beat < beats; ++beat) {
      dut.fwd_data_i = requests.at(addr).data(beat);
      bool got = false;
      for (unsigned n = 0; n < 300; ++n)
        if (step()) { got = true; break; }
      require(got, "input request beat was never accepted");
    }
    dut.fwd_v_i = 0;
  }
  void wait_packets(unsigned target) {
    for (unsigned n = 0; n < 300; ++n) {
      step();
      if (packet_count == target) return;
      require(packet_count < target, "unexpected extra bank command");
    }
    throw std::runtime_error("expected cache-bank command did not arrive");
  }
  void reset() {
    dut.reset_i = 1; dut.fwd_v_i = 0; dut.rev_ready_i = 1;
    stalled = false; hold = {{false, false}};
    check_write_lock = false;
    banks = {}; commands = {}; requests.clear(); replies.clear();
    packet_count = internal_count = 0;
    cycles(4); dut.reset_i = 0;
    for (unsigned n = 0; n < 500; ++n) {
      step();
      if (dut.ready_o && banks[0].empty() && banks[1].empty()) {
        require(internal_count != 0 && replies.empty(), "initialization responses not drained internally");
        cycles(4); return;
      }
    }
    throw std::runtime_error("cache initialization did not finish");
  }
 public:
  Test() { context.traceEverOn(true); dut.trace(&trace, 99); trace.open("l2-prefetch.fst"); }
  ~Test() { dut.final(); trace.close(); }
  void run(bool baseline) {
    reset();
    // A normal bank-1 hit must escape an older, unready bank-0 hint.
    hold[0] = true;
    send(0x80000000, true); send(0x80000040, false); wait_packets(2); cycles(32);
    if (baseline) {
      require(replies.empty() && !banks[1].empty(), "baseline did not reproduce response HOL");
      std::cout << "[L2-PREFETCH] BASELINE HOL: ready normal bank 1 blocked for 32 cycles behind pending bank 0 hint\n";
      hold[0] = false; idle();
      require(replies.size() == 2 && replies[0].prefetch && !replies[1].prefetch,
              "baseline shared-FIFO reply order mismatch");
      return;
    }
    require(replies.size() == 1 && replies[0].addr == 0x80000040,
            "HOL: ready normal bank 1 blocked behind pending bank 0 prefetch");
    hold[0] = false; idle();

    reset(); hold[0] = true;
    send(0x80000100, false); send(0x80000140, false); wait_packets(2); cycles(24);
    require(replies.empty(), "ordinary cross-bank response acceptance order changed");
    hold[0] = false; idle();
    require(replies[0].addr == 0x80000100 && replies[1].addr == 0x80000140,
            "ordinary responses returned out of order");

    reset(); hold[0] = true;
    send(0x80000200, true); send(0x80000280, false); wait_packets(2); cycles(12);
    require(replies.empty(), "same-bank ordinary response overtook prefetch");
    hold[0] = false; idle();
    require(replies[0].prefetch && !replies[1].prefetch, "same-bank metadata order changed");

    reset();
    send(0x80000400, false, 6);
    // Wait for the first beat before making the other bank's hint available.
    for (unsigned n = 0; replies.empty() && n < 100; ++n) step();
    require(replies.size() == 1, "full-line response did not begin");
    dut.rev_ready_i = 0;
    send(0x80000440, true);
    cycles(12);
    require(replies.size() == 1, "response ignored reverse backpressure");
    for (unsigned n = 0; n < 80; ++n) { dut.rev_ready_i = (n % 4) == 3; step(); }
    dut.rev_ready_i = 1; idle();
    require(replies.size() == 9, "full-line packet lost beats");
    for (unsigned n = 0; n < 8; ++n)
      require(replies[n].addr == 0x80000400, "another bank interleaved an eight-beat response");
    require(replies[8].addr == 0x80000440, "queued hint response missing after packet unlock");

    reset(); check_write_lock = true;
    send(0x80000800, false, 6, 1);
    require(requests.at(0x80000800).acknowledged < 8,
            "store packet-lock test did not retain pending internal acknowledgements");
    hold[0] = true;
    // Backpressure after the store's first externally visible acknowledgement;
    // remaining bank acknowledgements still belong to the same packet.
    dut.rev_ready_i = 0;
    send(0x80000840, true);
    cycles(12);
    require(!banks[1].empty() && (replies.empty() || !replies.back().prefetch),
            "opposite-bank hint bypassed unfinished store packet");
    hold[0] = false;
    for (unsigned n = 0; n < 80; ++n) { dut.rev_ready_i = (n % 4) == 3; step(); }
    dut.rev_ready_i = 1; idle();
    require(replies.size() == 2 && replies[0].operation == 1 && replies[1].prefetch,
            "eight store acknowledgements did not collapse to one ordered BedRock reply");
    require(requests.at(0x80000800).acknowledged == 8, "store acknowledgement count mismatch");
    send(0x80000900, false, 3, 2); idle();
    require(replies.size() == 3 && replies.back().operation == 2,
            "AMO response metadata or data failed after store packet");

    reset(); hold = {{true, true}}; unrestricted = true;
    for (unsigned n = 0; n < 6; ++n) send(0x80001000 + n * 64, false);
    wait_packets(6);
    start(0x80001400, false);
    bool buffered = false;
    for (unsigned n = 0; n < 24; ++n) {
      if (step()) { buffered = true; dut.fwd_v_i = 0; }
      require(packet_count == 6, "metadata capacity overflow admitted a seventh bank command");
    }
    hold = {{false, false}};
    if (!buffered) {
      bool got = false;
      for (unsigned n = 0; n < 100; ++n) if (step()) { got = true; break; }
      require(got, "input did not recover from metadata-full backpressure");
      dut.fwd_v_i = 0;
    }
    idle(); unrestricted = false;
    require(replies.size() == 7, "metadata-full recovery lost responses");

    reset();
    unsigned before = internal_count;
    send(dut.uncached_base_o + 0x2000, false);
    idle();
    require(replies.size() == 1 && internal_count == before + 1,
            "uncached AFLINV response was not discarded exactly once");
    send(0x80003040, false); idle();
    require(replies.size() == 2, "normal request failed after uncached flush/drain");

    reset(); hold[0] = true;
    send(0x80004000, false);
    send(dut.uncached_base_o + 0x2040, false);
    wait_packets(2); cycles(24);
    require(replies.empty() && banks[1].size() == 2 && !banks[1].front().internal,
            "uncached drain consumed an unselected ordinary bank response");
    hold[0] = false; idle();
    require(replies.size() == 2 && replies[0].addr == 0x80004000
            && replies[1].addr == dut.uncached_base_o + 0x2040,
            "uncached drain lost ordinary acceptance order");
    std::cout << "[L2-PREFETCH] PASS: HOL bypass, ordinary/same-bank ordering, eight-beat read/write packet lock, AMO, stalls, metadata capacity, init and uncached drain\n";
  }
};
}
int main(int argc, char **argv) {
  try {
    Test test;
    test.run(argc == 2 && std::string(argv[1]) == "--baseline-hol");
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "[L2-PREFETCH] FAIL: " << error.what() << '\n';
    return 1;
  }
}
