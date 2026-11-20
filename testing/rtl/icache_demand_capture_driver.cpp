#include "Vicache_demand_capture.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>

namespace {
constexpr uint64_t line = UINT64_C(0x80012000);
constexpr uint64_t seed = UINT64_C(0x7193000000000000);
constexpr bool capture = CAPTURE_ENABLED != 0;
void require(bool value, const char *message) {
  if (!value) throw std::runtime_error(message);
}
class Test {
  VerilatedContext context;
  Vicache_demand_capture dut{&context};
  VerilatedFstC trace;
  unsigned cycles = 0;
  void low() { dut.clk_i = 0; dut.eval(); }
  void step() {
    require(++cycles < 20000, "demand capture cycle limit");
    low(); context.timeInc(5); trace.dump(context.time());
    dut.clk_i = 1; dut.eval(); context.timeInc(5); trace.dump(context.time());
  }
  void idle(unsigned n = 4) { while (n--) step(); }
  void reset() {
    dut.fetch_v_i = dut.fence_i = dut.abort_i = dut.flush_i = 0;
    dut.fetch_uncached_i = dut.data_v_i = dut.init_v_i = dut.query_v_i = 0;
    dut.data_first_i = dut.data_last_i = 0;
    dut.reset_i = 1; idle(3); dut.reset_i = 0; step();
    for (unsigned i = 0; i < 4; ++i) clear_index(i);
  }
  void clear_index(unsigned index) {
    dut.init_index_i = index; dut.init_v_i = 1;
    for (unsigned n = 0; n < 30; ++n) {
      low();
      if (dut.init_yumi_o) { step(); dut.init_v_i = 0; idle(2); return; }
      step();
    }
    throw std::runtime_error("ordinary SRAM tag clear timeout");
  }
  bool query(uint64_t addr) {
    dut.query_addr_i = addr; dut.query_v_i = 1; low();
    const bool hit = dut.query_hit_o;
    dut.query_v_i = 0; low(); return hit;
  }
  void start_miss(uint64_t addr, bool uncached = false) {
    dut.fetch_addr_i = addr; dut.fetch_uncached_i = uncached;
    dut.fetch_v_i = 1; dut.fence_i = 0;
    bool accepted = false;
    for (unsigned n = 0; n < 30; ++n) {
      low();
      if (dut.fetch_yumi_o) { accepted = true; step(); break; }
      step();
    }
    require(accepted, "demand fetch acceptance timeout");
    dut.fetch_v_i = 0;
    for (unsigned n = 0; n < 30; ++n) {
      low(); require(!dut.hit_v_o, "expected ordinary demand hit retained data");
      if (dut.miss_req_v_o) { step(); idle(2); return; }
      step();
    }
    throw std::runtime_error("ordinary cached request was not emitted");
  }
  void set_beat(uint64_t addr, unsigned beat, uint64_t data_seed,
                bool first, bool last, unsigned kind = 0) {
    dut.data_v_i = 1; dut.data_kind_i = kind;
    dut.data_addr_i = addr + beat*16; dut.data_fill_i = 1u << beat;
    dut.data_word0_i = data_seed + beat*2;
    dut.data_word1_i = data_seed + beat*2 + 1;
    dut.data_first_i = first; dut.data_last_i = last;
  }
  void beat(uint64_t addr, unsigned index, uint64_t data_seed,
            bool first, bool last, unsigned kind = 0) {
    set_beat(addr, index, data_seed, first, last, kind);
    for (unsigned n = 0; n < 30; ++n) {
      low();
      if (dut.data_yumi_o) { step(); return; }
      step();
    }
    throw std::runtime_error("ordinary SRAM beat acceptance timeout");
  }
  void end_data() {
    dut.data_v_i = dut.data_first_i = dut.data_last_i = 0; idle();
  }
  void fill_line(uint64_t addr, uint64_t data_seed = seed, unsigned first = 0) {
    start_miss(addr + first*16);
    for (unsigned n = 0; n < 4; ++n) {
      beat(addr, (first+n)%4, data_seed, n == 0, n == 3);
      if (n < 3) require(!query(addr), "partial ordinary refill published");
    }
    end_data();
    require(query(addr) == capture, "ordinary demand capture enable mismatch");
  }
  uint64_t fetch(uint64_t addr, bool expect_hit) {
    dut.fetch_addr_i = addr; dut.fetch_uncached_i = 0;
    dut.fetch_v_i = 1; dut.fence_i = 0;
    bool accepted = false;
    for (unsigned n = 0; n < 30; ++n) {
      low();
      if (dut.fetch_yumi_o) { accepted = true; step(); break; }
      step();
    }
    require(accepted, "fetch acceptance timeout");
    dut.fetch_v_i = 0;
    for (unsigned n = 0; n < 30; ++n) {
      low();
      if (dut.hit_v_o) {
        require(expect_hit, "evicted ordinary cache unexpectedly hit");
        const uint64_t value = dut.data_o; step(); idle(2); return value;
      }
      if (dut.miss_req_v_o) {
        require(!expect_hit, "captured complete line missed");
        step(); return 0;
      }
      step();
    }
    throw std::runtime_error("fetch produced neither hit nor demand");
  }
  void fence(bool pipeline_replay = false) {
    dut.fetch_addr_i = 0; dut.fetch_v_i = dut.fence_i = 1;
    bool accepted = false;
    for (unsigned n = 0; n < 30; ++n) {
      low();
      if (dut.fetch_yumi_o) { accepted = true; step(); break; }
      step();
    }
    require(accepted, "fence frontend acceptance timeout");
    dut.fetch_v_i = 0;
    if (pipeline_replay) set_beat(line + 4096, 3, seed + 100, false, false, 2);
    for (unsigned n = 0; n < 30; ++n) {
      low();
      if (dut.fence_accept_o) {
        step(); dut.data_v_i = dut.fence_i = 0; idle(5); return;
      }
      step();
    }
    throw std::runtime_error("fence engine acceptance timeout");
  }
public:
  Test() {
    context.traceEverOn(true); dut.trace(&trace, 99);
    trace.open("icache-demand-capture.fst");
  }
  ~Test() { dut.final(); trace.close(); }
  void run() {
    // No replay CSR, controller, address table, or detached response is needed.
    reset(); fill_line(line);
    for (unsigned word = 0; word < 8; ++word)
      require(fetch(line + word*8, true) == seed + word,
              "ordinary SRAM refill changed execution data");
    std::cout << "CASE ordinary-side-lookup\n";
    clear_index((line >> 6) & 3);
    if (capture) {
      for (unsigned word = 0; word < 8; ++word)
        require(fetch(line + word*8, true) == seed + word,
                "demand-retained word selection mismatch");
    } else fetch(line, false);

    // Critical-first 2,3,0,1 is one publication epoch, not a reset at beat0.
    reset(); fill_line(line, seed + 16, 2);
    clear_index((line >> 6) & 3);
    if (capture) {
      for (unsigned word = 0; word < 8; ++word)
        require(fetch(line + word*8, true) == seed + 16 + word,
                "rotated retained refill mixed data beats");
    } else fetch(line, false);

    // A valid final beat stalled by a frontend SRAM read cannot publish.
    reset(); start_miss(line);
    for (unsigned i = 0; i < 3; ++i) beat(line, i, seed, i == 0, false);
    dut.data_v_i = 0; step();
    set_beat(line, 3, seed, false, true);
    dut.fetch_addr_i = line + 64; dut.fetch_v_i = 1;
    low(); require(dut.fetch_yumi_o, "stall test could not accept SRAM read");
    require(!dut.data_yumi_o, "SRAM arbitration did not stall final beat");
    step(); require(!query(line), "unaccepted final beat published");
    dut.fetch_v_i = 0; dut.flush_i = 1;
    low(); require(dut.data_yumi_o, "held final beat did not become ready");
    step(); dut.flush_i = 0; end_data();
    require(query(line) == capture, "accepted held beat was not captured");

    // A partially copied aborted refill never becomes an executable line;
    // its next rotated refill must discard every old partial beat.
    reset(); start_miss(line);
    beat(line, 0, seed, true, false); beat(line, 1, seed, false, false);
    dut.data_v_i = 0; dut.abort_i = dut.flush_i = 1; step();
    dut.abort_i = 0; dut.flush_i = 0;
    beat(line, 2, seed, false, false); beat(line, 3, seed, false, true);
    end_data(); require(!query(line), "aborted refill published");
    fill_line(line, seed + 32, 2);
    clear_index((line >> 6) & 3);
    if (capture)
      for (unsigned word = 0; word < 8; ++word)
        require(fetch(line + word*8, true) == seed + 32 + word,
                "aborted generation contaminated a new refill");

    // Abort between final SRAM acceptance and registered side publication.
    reset(); start_miss(line);
    for (unsigned i = 0; i < 4; ++i) beat(line, i, seed, i == 0, i == 3);
    dut.data_v_i = 0; dut.abort_i = 1; step();
    dut.abort_i = 0; idle();
    require(!query(line), "queued final beat survived demand abort");

    reset(); start_miss(line, true);
    beat(line, 0, seed, true, true, 1); end_data();
    require(!query(line), "uncached response entered retained store");

    // With no accepted demand request, ordinary writes cannot train capture.
    reset();
    for (unsigned i = 0; i < 4; ++i) beat(line, i, seed, false, false);
    end_data(); require(!query(line), "unsolicited ordinary write was captured");

    std::cout << "CASE fence-invalidation\n";
    reset(); fill_line(line); fence();
    require(!query(line), "fence did not invalidate demand-retained copy");
    fetch(line, false);

    // Existing registered replay writes must also lose to the same accepted
    // fence: a pending beat cannot republish a pre-fence generation.
    reset();
    for (unsigned i = 0; i < 3; ++i)
      beat(line + 4096, i, seed + 100, false, false, 2);
    dut.data_v_i = 0; step(); fence(true);
    require(!query(line + 4096), "pipeline beat republished across fence");

    // Demand learning uses the exact existing 32-entry banked capacity.
    reset();
    for (unsigned slot = 0; slot < 32; ++slot)
      fill_line(line + slot*64, seed + slot*16);
    for (unsigned slot = 0; slot < 32; ++slot)
      require(query(line + slot*64) == capture, "demand capture lost capacity");
    fill_line(line + 32*64, seed + 32*16);
    require(!query(line), "33rd learned line did not replace oldest bank entry");
    require(query(line + 64) == capture, "learned replacement altered wrong bank");
    require(query(line + 32*64) == capture, "replacement line not retained");

    std::cout << "[ICACHE-DEMAND-CAPTURE] PASS: capture=" << capture
              << " ordinary execution, no-trigger learning, 2/3/0/1 epoch, "
                 "SRAM stall, partial/queued abort, uncached exclusion, fence "
                 "pipeline cancellation, and equal 32-entry replacement\n";
  }
};
}
int main() {
  try { Test test; test.run(); }
  catch (const std::exception &error) {
    std::cerr << "[ICACHE-DEMAND-CAPTURE] FAIL: " << error.what() << '\n';
    return 1;
  }
  return 0;
}
