#include "Vprefetch_axi_master_tb.h"
#include "verilated.h"
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>

static void fall(Vprefetch_axi_master_tb &d) {
  d.clk_i = 0;
  d.eval();
}

static void rise(Vprefetch_axi_master_tb &d) {
  d.clk_i = 1;
  d.eval();
}

static void cycle(Vprefetch_axi_master_tb &d) {
  fall(d);
  rise(d);
}

static void issue(Vprefetch_axi_master_tb &d, uint64_t address,
                  uint8_t expected_id) {
  d.req_addr_i = address;
  d.req_v_i = 1;
  fall(d);
  assert(d.req_ready_o && d.arvalid_o && d.arready_i);
  assert(d.araddr_o == static_cast<uint32_t>(address));
  assert(d.arid_o == expected_id);
  const int bytes = d.axi_data_width_o / 8;
  const int beats = 64 / bytes;
  assert(d.arlen_o == beats - 1 && d.arsize_o == (bytes == 4 ? 2 : 3)
         && d.arburst_o == 1);
  rise(d);
  d.req_v_i = 0;
}

static void response(Vprefetch_axi_master_tb &d, uint8_t id, int beat,
                     uint64_t address, bool stall) {
  const bool axi64 = d.axi_data_width_o == 64;
  const uint64_t data = axi64
    ? (static_cast<uint64_t>(id) << 56) | beat
    : (static_cast<uint32_t>(id) << 24) | beat;
  const int beats = axi64 ? 8 : 16;
  d.rid_i = id;
  d.rdata_i = data;
  d.rresp_i = 0;
  d.rlast_i = beat == beats - 1;
  d.rvalid_i = 1;
  d.rev_ready_i = stall ? 0 : 1;
  fall(d);

  const bool fill_complete = axi64 || (beat & 1);
  assert(d.rev_v_o == fill_complete);
  if (fill_complete) {
    const uint32_t prior = (static_cast<uint32_t>(id) << 24) | (beat - 1);
    const uint64_t expected = axi64
      ? data : (static_cast<uint64_t>(data) << 32) | prior;
    assert(d.rev_addr_o == address);
    assert(d.rev_data_o == expected);
  }

  if (stall) {
    assert(fill_complete && !d.rready_o);
    rise(d);
    d.rev_ready_i = 1;
    fall(d);
    assert(d.rready_o && d.rev_v_o);
  } else {
    assert(d.rready_o);
  }
  rise(d);
  d.rvalid_i = 0;
}

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  Vprefetch_axi_master_tb d;
  d.req_v_i = 0;
  d.req_addr_i = 0;
  d.arready_i = 1;
  d.rid_i = 0;
  d.rdata_i = 0;
  d.rresp_i = 0;
  d.rlast_i = 0;
  d.rvalid_i = 0;
  d.rev_ready_i = 1;
  d.reset_i = 1;
  cycle(d);
  cycle(d);
  d.reset_i = 0;

  constexpr uint64_t base = 0x80010000;
  issue(d, base, 1);
  issue(d, base + 64, 2);
  issue(d, base + 128, 3);

  d.req_addr_i = base + 192;
  d.req_v_i = 1;
  fall(d);
  assert(!d.req_ready_o && !d.arvalid_o);
  rise(d);
  d.req_v_i = 0;

  // Interleave every AXI beat across IDs and finish ID 3 before IDs 1 and 2.
  constexpr std::array<uint8_t, 3> order = {3, 1, 2};
  const int beats = d.axi_data_width_o == 64 ? 8 : 16;
  for (int beat = 0; beat < beats; ++beat)
    for (uint8_t id : order)
      response(d, id, beat, base + (id - 1) * 64,
               id == 2 && beat == 1);

  // Every slot is free again and allocation restarts at the lowest AXI ID.
  issue(d, base + 192, 1);
  std::cout << "[PREFETCH-AXI] PASS: " << static_cast<int>(d.axi_data_width_o)
            << "-bit AXI, full queue, interleaved IDs, backpressure, data assembly, slot reuse\n";
  d.final();
  return 0;
}
