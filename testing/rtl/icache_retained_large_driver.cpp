#include "Vicache_retained_large.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <stdexcept>

static void require(bool value, const char *message) {
  if (!value) throw std::runtime_error(message);
}
class Test {
  VerilatedContext context;
  Vicache_retained_large dut{&context};
  VerilatedFstC trace;
  unsigned cycles = 0;
  unsigned lines;
  static uint64_t value(unsigned line, unsigned word) {
    return 0x6193dcba28000000ULL ^ (uint64_t(line)*0x15094731ULL) ^ (word*0x1020304ULL);
  }
  void low() { dut.clk_i = 0; dut.eval(); }
  void step() {
    require(++cycles < 3000000, "I large gate cycle bound");
    low(); context.timeInc(5); trace.dump(context.time());
    dut.clk_i = 1; dut.eval(); context.timeInc(5); trace.dump(context.time());
  }
  void idle(unsigned n = 4) { while (n--) step(); }
  void settle() {
    idle(12);
    for (unsigned i = 0; i < lines+1000; ++i) {
      low(); if (!dut.backend_busy_o) { idle(4); return; } step();
    }
    throw std::runtime_error("backend did not finish bounded transaction/sweep");
  }
  void policy(unsigned mode) {
    dut.retention_mode_i = mode; dut.retention_cmd_v_i = 1; step();
    dut.retention_cmd_v_i = 0; idle();
  }
  void clear_index(unsigned index) {
    dut.init_v_i = 1; dut.init_index_i = index;
    for (unsigned i = 0; i < 100; ++i) {
      low(); if (dut.init_yumi_o) { step(); dut.init_v_i = 0; idle(); return; } step();
    }
    throw std::runtime_error("ordinary tag clear timeout");
  }
  void clear_main() { for (unsigned i = 0; i < 4; ++i) clear_index(i); }
  void reset(unsigned mode = 1) {
    dut.reset_i = 1; dut.consume_i = 1; dut.ptag_valid_i = 1; dut.lookup_enable_i = 1;
    dut.init_v_i = dut.data_v_i = dut.fetch_v_i = dut.fence_i = dut.abort_i = dut.flush_i = 0;
    dut.query_v_i = dut.backend_stall_i = dut.retention_cmd_v_i = 0;
    dut.fetch_uncached_i = dut.data_first_i = dut.data_last_i = 0;
    idle(3); dut.reset_i = 0; settle(); clear_main(); policy(mode);
  }
  void offer(uint64_t addr, bool uncached = false) {
    dut.fetch_addr_i = addr; dut.fetch_uncached_i = uncached; dut.fetch_v_i = 1;
    for (unsigned i = 0; i < 100; ++i) {
      low(); if (dut.fetch_yumi_o) { step(); dut.fetch_v_i = 0; return; } step();
    }
    throw std::runtime_error("fetch offer timeout");
  }
  void start_miss(uint64_t addr, bool uncached = false) {
    offer(addr, uncached);
    for (unsigned i = 0; i < 512; ++i) {
      low(); require(!dut.hit_v_o, "expected cold miss hit retained store");
      if (dut.miss_req_v_o) { step(); idle(2); return; } step();
    }
    throw std::runtime_error("ordinary UCE request timeout");
  }
  void beat(uint64_t addr, unsigned line, unsigned index, bool first, bool last, unsigned kind = 0) {
    dut.data_v_i = 1; dut.data_kind_i = kind; dut.data_addr_i = addr + index*16;
    dut.data_fill_i = 1 << index; dut.data_word0_i = value(line, index*2);
    dut.data_word1_i = value(line, index*2+1); dut.data_first_i = first; dut.data_last_i = last;
    for (unsigned i = 0; i < 100; ++i) {
      low(); if (dut.data_yumi_o) { step(); return; } step();
    }
    throw std::runtime_error("ordinary accepted refill stalled by capture");
  }
  void end_data() { dut.data_v_i = dut.data_first_i = dut.data_last_i = 0; settle(); }
  void fill(uint64_t addr, unsigned line, unsigned first = 0, bool advisory = false) {
    if (!advisory) start_miss(addr+first*16);
    for (unsigned n = 0; n < 4; ++n)
      beat(addr, line, (n+first)%4, n == 0, n == 3, advisory ? 2 : 0);
    end_data();
  }
  void flush() { dut.flush_i = 1; step(); dut.flush_i = 0; idle(); }
  void abort(bool drain = true) {
    dut.abort_i = 1; dut.flush_i = 1; step(); dut.abort_i = dut.flush_i = 0;
    if (drain) {
      // The real UCE cannot retract an accepted request. Model its terminal
      // discarded beat before offering a new fetch, as the production cache
      // explicitly holds abort ownership until cache_req_last_i.
      dut.data_v_i = 1; dut.data_kind_i = 0; dut.data_fill_i = 1;
      dut.data_first_i = 0; dut.data_last_i = 1; step();
      dut.data_v_i = dut.data_last_i = 0;
    }
    idle();
  }
  uint64_t fetch(uint64_t addr, bool expected_hit) {
    offer(addr);
    for (unsigned i = 0; i < 512; ++i) {
      low();
      if (dut.hit_v_o) {
        require(expected_hit, "unexpected side hit");
        uint64_t result = dut.data_o; step(); idle(); return result;
      }
      if (dut.miss_req_v_o) {
        require(!expected_hit, "complete retained payload missed"); step(); return 0;
      }
      step();
    }
    throw std::runtime_error("fetch produced neither payload nor ordinary miss");
  }
  void fence() {
    dut.fence_i = 1; dut.fetch_v_i = 1; dut.fetch_addr_i = 0;
    bool accepted = false;
    for (unsigned i = 0; i < 100; ++i) {
      low(); if (dut.fetch_yumi_o) { step(); accepted = true; break; } step();
    }
    require(accepted, "fence offer timeout"); dut.fetch_v_i = 0;
    bool request = false;
    for (unsigned i = 0; i < lines+1000; ++i) {
      low(); if (dut.fence_accept_o) request = true;
      step(); if (request && !dut.backend_busy_o && i > 20) break;
    }
    require(request, "fence did not reach cache engine"); dut.fence_i = 0; settle();
  }
 public:
  explicit Test(unsigned capacity) : lines(capacity) {
    context.traceEverOn(true); dut.trace(&trace, 20); trace.open("icache-retained-large.fst");
  }
  ~Test() { trace.close(); }
  void run() {
    constexpr uint64_t base = 0x80040000ULL;
    reset(0);
    fill(base, 91, 2); unsigned before = dut.lookup_count_o;
    require(fetch(base+40, true) == value(91, 5), "ordinary L1 payload changed");
    require(dut.lookup_count_o == before, "ordinary L1 hit issued BRAM lookup");
    clear_main(); fetch(base, false); abort();
    require(dut.publish_count_o == 0, "mode zero captured ordinary demand");
    reset(1);
    for (unsigned i = 0; i < lines; ++i) fill(base+i*64, i, i%4);
    require(dut.publish_count_o == lines, "actual completed payload count differs from capacity");
    require(dut.drop_count_o == 0, "paced capacity study dropped captured lines");
    clear_main(); before = dut.lookup_count_o;
    for (unsigned i = 0; i < lines; ++i)
      for (unsigned w = 0; w < 8; ++w)
        require(fetch(base+i*64+w*8, true) == value(i, w), "retained full-line word mismatch");
    require(dut.lookup_count_o-before == lines*8, "side payload fetch bypassed synchronous lookup");
    require((dut.retention_status_o & 4) != 0, "demand publication status missing");
    std::cout << "CASE actual-full-payload lines=" << lines << " words=" << lines*8 << " PASS\n";

    before = dut.lookup_count_o; dut.lookup_enable_i = 0;
    fetch(base, false); require(dut.lookup_count_o == before, "disabled baseline still queried BRAM"); abort();
    unsigned published = dut.publish_count_o;
    fill(base+0x100000, 83, 0, true);
    require(dut.publish_count_o == published && dut.retained_idle_o,
            "disabled late advisory traffic captured or left client busy");
    dut.lookup_enable_i = 1;
    dut.backend_stall_i = 1; offer(base);
    idle(8); low(); require(!dut.hit_v_o && !dut.miss_req_v_o, "backpressured lookup escaped to UCE");
    flush(); dut.backend_stall_i = 0; idle(20);
    require(fetch(base+24, true) == value(0, 3), "redirect during unaccepted query lost next fetch");
    offer(base+8); idle(3); flush(); settle();
    require(fetch(base+48, true) == value(0, 6), "redirect during pending SRAM query corrupted new fetch");
    before = dut.lookup_count_o; dut.ptag_valid_i = 0; offer(base); idle(20);
    require(dut.lookup_count_o == before && !dut.hit_v_o, "untranslated/speculative fetch used retained physical line");
    flush(); dut.ptag_valid_i = 1;
    before = dut.lookup_count_o; start_miss(base, true);
    require(dut.lookup_count_o == before, "uncached fetch used retained payload"); abort();
    fence(); fetch(base, false); abort();
    std::cout << "CASE lookup-control permission uncached redirect fence PASS\n";

    reset(1); start_miss(base);
    beat(base, 31, 2, true, false); beat(base, 31, 3, false, false);
    abort(false);
    // Finish the canceled required UCE packet so the ordinary abort drain ends.
    beat(base, 31, 0, false, false); beat(base, 31, 1, false, true); end_data();
    clear_main(); fetch(base, false); abort();
    require(dut.publish_count_o == 0, "aborted partial demand published");
    reset(0); fill(base, 71, 0, true); clear_main();
    require(fetch(base+56, true) == value(71, 7), "advisory-only mode zero failed");
    require((dut.retention_status_o & 4) == 0, "advisory insert mislabeled demand publication");
    fence(); fetch(base, false); abort();
    std::cout << "[ICACHE-RETAINED-LARGE] PASS: lines=" << lines
              << " complete64B demand/advisory payload, unchanged L1 hit, bypass, cancellation, MMU/uncached guards, abort/fence\n";
  }
};
int main(int argc, char **argv) {
  try {
    Verilated::commandArgs(argc, argv);
    require(argc == 2, "expected configured capacity argument");
    Test test(unsigned(std::stoul(argv[1]))); test.run(); return 0;
  } catch (const std::exception &e) { std::cerr << "FAIL: " << e.what() << '\n'; return 1; }
}
