#include "Vprefetch_mshr_table_tb.h"
#include "verilated.h"
#include <cassert>
#include <cstdint>
#include <iostream>

static void tick(Vprefetch_mshr_table_tb &d, uint64_t t) {
  d.clk_i = 0; d.eval();
  d.clk_i = 1; d.eval();
}
static void reset(Vprefetch_mshr_table_tb &d) {
  d.reset_i = 1; for (int i = 0; i < 2; ++i) tick(d, i); d.reset_i = 0;
}
int main() {
  Vprefetch_mshr_table_tb d;
  d.alloc_v_i = d.issue_v_i = d.response_v_i = d.response_last_i = d.demand_v_i = 0;
  d.issue_id_i = d.response_id_i = d.response_beat_i = 0; reset(d);
  d.alloc_addr_i = 0x1000; d.alloc_context_i = 1; d.alloc_way_i = 3; d.alloc_v_i = 1;
  d.eval(); assert(d.alloc_yumi_o && d.alloc_id_o == 0); tick(d, 0); d.alloc_v_i = 0;
  d.alloc_addr_i = 0x2000; d.alloc_context_i = 2; d.alloc_way_i = 5; d.alloc_v_i = 1;
  d.eval(); assert(d.alloc_yumi_o && d.alloc_id_o == 1); tick(d, 0); d.alloc_v_i = 0;
  d.issue_id_i = 0; d.issue_v_i = 1; d.eval(); assert(d.issue_ready_o); tick(d, 0); d.issue_v_i = 0;
  d.issue_id_i = 1; d.issue_v_i = 1; d.eval(); assert(d.issue_ready_o); tick(d, 0); d.issue_v_i = 0;
  assert(d.valid_o == 3 && d.issued_o == 3 && d.addr0_o == 0x1000 && d.addr1_o == 0x2000);
  d.demand_addr_i = 0x2038; d.demand_v_i = 1; d.eval();
  assert(d.demand_join_o && d.demand_id_o == 1); d.demand_v_i = 0;
  d.response_id_i = 1; d.response_beat_i = 2; d.response_v_i = 1; d.response_last_i = 0; d.eval(); assert(d.response_ready_o); tick(d, 0); d.response_v_i = 0;
  assert(d.valid_o == 3 && d.issued_o == 3 && d.fill_mask1_o == 4);
  d.response_v_i = d.response_last_i = 1; d.eval(); assert(d.response_ready_o); tick(d, 0); d.response_v_i = d.response_last_i = 0;
  assert(d.valid_o == 1 && d.issued_o == 1);
  d.response_id_i = 0; d.response_v_i = d.response_last_i = 1; d.eval(); assert(d.response_ready_o); tick(d, 0); d.response_v_i = d.response_last_i = 0;
  assert(d.valid_o == 0 && d.issued_o == 0);
  std::cout << "[PREFETCH-MSHR] PASS: out-of-order issue/retire\n";
}
