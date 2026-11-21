#include "Vbp_fe_icache_retained_bram.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <stdexcept>

static Vbp_fe_icache_retained_bram *dut;
#define d (*dut)
static VerilatedFstC *tracer;
static uint64_t cycle = 0;
static void check(bool ok, const char *message) {
  if (!ok) throw std::runtime_error(message);
}
static void eval() { d.eval(); }
static void tick() {
  d.clk_i = 0; eval(); tracer->dump(cycle++);
  d.clk_i = 1; eval(); tracer->dump(cycle++);
  d.clk_i = 0; eval(); tracer->dump(cycle++);
}
static void clocks(unsigned n = 1) { while (n--) tick(); }
static uint64_t word(unsigned index, uint64_t salt) {
  return 0x715392bca0468defULL ^ (uint64_t(index) * 0x102030405060708ULL) ^ salt;
}
static void response(bool hit, uint64_t salt) {
  d.resp_hit_i = hit;
  for (unsigned w = 0; w < 8; ++w) {
    const uint64_t x = word(w, salt);
    d.resp_data_i[2*w] = uint32_t(x);
    d.resp_data_i[2*w+1] = uint32_t(x >> 32);
  }
  d.resp_v_i = 1; tick(); d.resp_v_i = 0; eval();
}
static void beat(uint64_t addr, unsigned index, bool demand, bool first, uint64_t salt) {
  d.capture_v_i = 1; d.capture_paddr_i = addr;
  d.capture_demand_i = demand; d.capture_first_i = first;
  d.capture_beats_i = 1 << index;
  for (unsigned w = 0; w < 2; ++w) {
    uint64_t x = word(index*2+w, salt);
    d.capture_data_i[2*w] = uint32_t(x);
    d.capture_data_i[2*w+1] = uint32_t(x >> 32);
  }
  tick(); d.capture_v_i = 0; eval();
}
static void line(uint64_t addr, bool demand, uint64_t salt) {
  // Ordinary responses can be critical-first, including zero halfway through.
  for (unsigned i = 0; i < 4; ++i) beat(addr, (i+2)%4, demand, i == 0, salt);
}
static void payload(uint64_t salt) {
  for (unsigned w = 0; w < 8; ++w) {
    uint64_t x = uint64_t(d.insert_data_o[2*w]) | (uint64_t(d.insert_data_o[2*w+1]) << 32);
    check(x == word(w, salt), "full-line payload differs");
  }
}
static void finish_insert(bool published, bool expected_demand) {
  d.insert_ready_i = 1; tick(); d.insert_ready_i = 0;
  check(!d.insert_v_o, "inflight insert must not be sent twice");
  d.insert_done_i = 1; d.insert_published_i = published; eval();
  check(bool(d.demand_published_o) == (published && expected_demand), "publication source/provenance");
  tick(); d.insert_done_i = 0; d.insert_published_i = 0; eval();
}
int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv); Verilated::traceEverOn(true);
  VerilatedFstC local_trace; tracer = &local_trace;
  dut = new Vbp_fe_icache_retained_bram;
  d.trace(tracer, 8); tracer->open("icache-retained-adapter.fst");
  try {
    d.reset_i = 1; d.enable_i = 1; clocks(3); d.reset_i = 0; tick();
    check(d.idle_o, "reset adapter is not idle");
    d.lookup_v_i = 1; d.lookup_paddr_i = 0x80001240; eval();
    check(d.lookup_v_o && d.wait_o, "initial lookup must wait without UCE fallback");
    clocks(3); check(d.lookup_v_o, "backpressured query must remain offered");
    d.lookup_ready_i = 1; tick(); d.lookup_ready_i = 0;
    check(!d.lookup_v_o, "accepted query must not repeat");
    check(!d.idle_o, "accepted query missing from lifecycle busy");
    d.cancel_i = 1; tick(); d.cancel_i = 0;
    d.lookup_paddr_i = 0x81203440; eval();
    check(!d.lookup_v_o, "redirect must retain old response ownership");
    response(true, 1); check(!d.hit_o, "canceled response served a fetch");
    check(d.lookup_v_o, "new fetch did not resume after canceled response");
    d.lookup_ready_i = 1; tick(); d.lookup_ready_i = 0;
    response(true, 2); check(d.hit_o && !d.wait_o, "live complete reply did not hit");
    clocks(3); check(d.hit_o, "unconsumed reply not held");
    d.consume_i = 1; tick(); d.consume_i = 0; d.lookup_v_i = 0; tick();
    d.lookup_v_i = 1; d.lookup_ready_i = 1; tick(); d.lookup_ready_i = 0;
    response(false, 3); check(!d.hit_o && !d.wait_o, "miss must release ordinary UCE path");
    d.lookup_v_i = 0; tick(); d.lookup_v_i = 1; d.lookup_ready_i = 1; tick();
    d.lookup_ready_i = 0; d.lookup_v_i = 0; tick(); d.lookup_v_i = 1;
    response(true, 4); check(!d.hit_o, "disabled-then-enabled old query resurrected");
    d.lookup_ready_i = 1; tick(); d.lookup_ready_i = 0; d.clear_i = 1;
    response(true, 5); check(!d.hit_o, "clear concurrent with reply served stale fetch");
    d.clear_i = 0; d.lookup_v_i = 0; tick();

    beat(0x80010000, 2, true, true, 11);
    beat(0x80010000, 3, true, false, 11);
    check(!d.insert_v_o, "partial line published");
    beat(0x80010000, 0, true, false, 11);
    check(!d.insert_v_o, "critical-first wrap published early");
    beat(0x80010000, 1, true, false, 11);
    check(d.insert_v_o && d.insert_paddr_o == 0x80010000, "complete line not staged");
    payload(11); clocks(2); payload(11);
    check(d.insert_replace_o, "RR demand replacement disabled");
    finish_insert(true, true);

    d.demand_pin_i = 1; line(0x80014000, true, 12);
    check(!d.insert_replace_o, "first-completed demand did not pin");
    d.demand_cancel_i = 1; eval(); check(!d.insert_v_o, "pending demand not canceled");
    tick(); d.demand_cancel_i = 0; eval(); check(!d.insert_v_o, "canceled demand survived");
    beat(0x80018000, 0, true, true, 13);
    beat(0x80018000, 1, true, false, 13);
    beat(0x80018000, 2, false, false, 14);
    beat(0x80018000, 3, false, false, 14);
    check(!d.insert_v_o, "mixed demand/advisory generations published");
    beat(0x80018000, 0, false, false, 14);
    beat(0x80018000, 1, false, false, 14);
    check(d.insert_v_o && d.insert_replace_o, "advisory insertion lost replacement");
    payload(14); finish_insert(true, false);

    line(0x80020000, true, 21);
    line(0x80024000, true, 22);
    check(d.drop_o && d.insert_paddr_o == 0x80020000, "full queue must drop whole second line");
    payload(21); finish_insert(true, true);
    beat(0x80028000, 2, true, true, 23);
    d.clear_i = 1; tick(); d.clear_i = 0;
    beat(0x80028000, 3, true, false, 23);
    beat(0x80028000, 0, true, false, 23);
    beat(0x80028000, 1, true, false, 23);
    check(!d.insert_v_o, "clear retained partial publication state");
    line(0x80030000, true, 24);
    d.insert_ready_i = 1; tick(); d.insert_ready_i = 0;
    d.demand_cancel_i = 1; eval(); check(d.insert_cancel_o, "active demand cancellation not forwarded");
    d.insert_done_i = 1; d.insert_published_i = 1; eval();
    check(!d.demand_published_o, "canceled inflight insert set sticky publication");
    tick(); d.demand_cancel_i = 0; d.insert_done_i = 0; d.insert_published_i = 0;
    line(0x80034000, false, 25); finish_insert(false, false);
    line(0x80038000, true, 26); finish_insert(true, true);
    d.enable_i = 0; line(0x8003c000, false, 27);
    check(!d.insert_v_o && d.idle_o, "disabled late advisory line captured");
    d.enable_i = 1; line(0x80040000, false, 28);
    d.insert_ready_i = 1; tick(); d.insert_ready_i = 0;
    d.enable_i = 0; eval();
    check(d.insert_cancel_o && !d.idle_o, "disable lost accepted advisory insert ownership");
    d.insert_done_i = 1; tick(); d.insert_done_i = 0; eval();
    check(d.idle_o, "disabled adapter not idle after canceled insert completion");
    std::cout << "[ICACHE-RETAINED-ADAPTER] PASS: canceled response ownership, wait/hit/miss, full payload, wrap, source isolation, queue drop, clear, insert cancellation/publication\n";
    tracer->close(); delete dut; return 0;
  } catch (const std::exception &e) {
    std::cerr << "FAIL at cycle " << cycle << ": " << e.what() << '\n'; tracer->close(); delete dut; return 1;
  }
}
