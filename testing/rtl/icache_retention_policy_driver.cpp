#include "Vicache_retention_policy.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>

namespace {
constexpr uint64_t line = UINT64_C(0x80012000);
constexpr uint64_t seed = UINT64_C(0x7193000000000000);
bool capture = false;
unsigned mode = 0;
void require(bool value, const char *message) {
  if (!value) throw std::runtime_error(message);
}
class Test {
  VerilatedContext context;
  Vicache_retention_policy dut{&context};
  VerilatedFstC trace;
  unsigned cycles = 0;
  void low() { dut.clk_i = 0; dut.eval(); }
  void step() {
    require(++cycles < 600000, "demand capture cycle limit");
    low(); context.timeInc(5); trace.dump(context.time());
    dut.clk_i = 1; dut.eval(); context.timeInc(5); trace.dump(context.time());
  }
  void idle(unsigned n = 4) { while (n--) step(); }
  void reset() {
    dut.fetch_v_i = dut.fence_i = dut.abort_i = dut.flush_i = 0;
    dut.fetch_uncached_i = dut.data_v_i = dut.init_v_i = dut.query_v_i = 0;
    dut.data_first_i = dut.data_last_i = 0;
    dut.retention_cmd_v_i = 0; dut.retention_mode_i = 0; dut.consume_i = 1;
    dut.reset_i = 1; idle(3); dut.reset_i = 0; step();
    for (unsigned i = 0; i < 4; ++i) clear_index(i);
    require(dut.retention_status_o == (UINT64_C(1)<<63), "reset policy/status mismatch");
    policy(mode);
  }
  uint64_t status() { low(); return dut.retention_status_o; }
  void policy(unsigned value) {
    dut.retention_mode_i = value; dut.retention_cmd_v_i = 1; step();
    dut.retention_cmd_v_i = 0; low();
    require(status() == ((UINT64_C(1)<<63) | (value == 3 ? 0 : value)),
            "policy write/reset statistics mismatch");
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
  void fill_line(uint64_t addr, uint64_t data_seed = seed, unsigned first = 0, int expected = -1) {
    start_miss(addr + first*16);
    for (unsigned n = 0; n < 4; ++n) {
      beat(addr, (first+n)%4, data_seed, n == 0, n == 3);
      if (n < 3) require(!query(addr), "partial ordinary refill published");
    }
    end_data();
    require(query(addr) == (expected < 0 ? capture : bool(expected)), "ordinary demand capture enable mismatch");
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
  void held_side_hit(uint64_t addr) {
    const uint64_t before = status() >> 16 & 65535;
    dut.consume_i = 0; dut.fetch_addr_i = addr; dut.fetch_v_i = 1;
    bool accepted = false;
    for (unsigned n=0; n<30; ++n) {
      low(); if (dut.fetch_yumi_o) {step(); accepted=true; break;} step();
    }
    require(accepted, "held hit acceptance timeout"); dut.fetch_v_i=0;
    bool hit = false;
    for(unsigned n=0;n<30;++n) {low();if(dut.hit_v_o){hit=true;break;}step();}
    require(hit,"held side hit missing");
    idle(7); require((status() >> 16 & 65535)==before,"unconsumed side hit counted");
    dut.consume_i=1;step();idle(2);
    require((status() >> 16 & 65535)==before+1,"released side hit not counted exactly once");
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
    trace.open("icache-retention-policy.fst");
  }
  ~Test() { dut.final(); trace.close(); }
  void run() {
    for (mode = 0; mode < 3; ++mode) { capture = mode != 0; run_mode(); }
    mode = 2; capture = true;
    reset(); fill_line(line);
    require((status() & 4) != 0, "completed demand publication not sticky");
    require((status() >> 16 & 65535) == 0, "ordinary L1 hit counted as side-only");
    for (unsigned w=0; w<8; ++w) fetch(line+w*8, true);
    require((status() >> 16 & 65535) == 0, "duplicate L1 copy counted");
    clear_index((line >> 6) & 3);
    for (unsigned w=0; w<8; ++w) fetch(line+w*8, true);
    require((status() >> 16 & 65535) == 8, "consumed side-only count mismatch");
    held_side_hit(line);
    // Policy changes reset diagnostics, but preserve all existing data.
    policy(0); require(query(line), "policy write invalidated retained data");
    fetch(line, true);
    require((status() >> 16 & 65535) == 1, "legacy mode lost existing side lookup");
    policy(2);
    // The 16-bit counter saturates instead of rolling over.
    for (unsigned i=0; i<65540; ++i) fetch(line, true);
    require((status() >> 16 & 65535) == 65535, "side-only hit counter wrapped");
    policy(3); require(query(line), "reserved policy write invalidated data");
    std::cout << "CASE global-policy-stats-saturation PASS\n";
    // A policy write cancels the registered final demand beat as well as
    // the active demand token, without changing the ordinary SRAM response.
    mode=2; reset(); start_miss(line);
    for(unsigned b=0;b<4;++b) beat(line,b,seed,b==0,b==3);
    dut.data_v_i=0; policy(0); idle();
    require(!query(line),"queued demand publication survived policy disable");
    require((status() & 4)==0,"canceled publication set sticky");


    // A bank with seven complete entries plus an aborted partial entry has
    // one usable pin slot. Complete entries must survive its reclamation.
    mode = 2; reset();
    uint64_t same[10]; unsigned n=0;
    auto bank=[](uint64_t a) { a >>= 6; return ((a^(a>>13))&1) | (((a>>3)^(a>>6))&1)<<1; };
    for (uint64_t a=line; n<10; a+=64) if (bank(a)==bank(line)) same[n++]=a;
    start_miss(same[0]); beat(same[0],0,seed,true,false);
    dut.data_v_i=0; dut.abort_i=dut.flush_i=1; step();
    dut.abort_i=dut.flush_i=0; idle();
    for(unsigned b=1;b<4;++b) beat(same[0],b,seed,false,b==3);
    end_data();
    for (unsigned i=1; i<=8; ++i) fill_line(same[i],seed+i*16);
    for (unsigned i=1; i<=8; ++i) require(query(same[i]), "aborted slot poisoned pin budget");
    require(!query(same[0]), "aborted slot published");
    // Full bank rejects demand line nine. Explicit advisory replay retains
    // its legacy replacement permission even while demand admission is pinned.
    start_miss(same[9]);
    for(unsigned b=0;b<4;++b) beat(same[9],b,seed+144,b==0,b==3);
    end_data(); require(!query(same[9]), "full pinned bank admitted ninth demand line");
    for(unsigned b=0;b<4;++b) beat(same[9],b,seed+144,false,false,2);
    end_data(); require(query(same[9]), "pin mode changed explicit replay admission");
    std::cout << "CASE partial-reclaim-advisory-compatibility PASS\n";
    std::cout << "[ICACHE-RETENTION-POLICY] PASS: runtime modes 0/1/2, pin/RR, epochs, abort, fence, stats, saturation\n";
  }
  void run_mode() {
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
    fill_line(line + 32*64, seed + 32*16, 0, mode == 1);
    require(query(line) == (mode == 2), "RR versus first-completed admission mismatch");
    require(query(line + 64) == capture, "learned replacement altered wrong bank");
    require(query(line + 32*64) == (mode == 1), "new line admission mismatch");

    std::cout << "CASE mode=" << mode << " complete ordinary-refill regression PASS\n";

  }
};
}
int main() {
  try { Test test; test.run(); }
  catch (const std::exception &error) {
    std::cerr << "[ICACHE-RETENTION-POLICY] FAIL: " << error.what() << '\n';
    return 1;
  }
  return 0;
}
