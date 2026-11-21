#include "Vlarge_retained_control.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>

static void need(bool condition, const char *message) {
  if (!condition) throw std::runtime_error(message);
}
int main(int argc, char **argv) {
  VerilatedContext context; context.commandArgs(argc, argv); context.traceEverOn(true);
  Vlarge_retained_control d{&context};
  VerilatedFstC trace; d.trace(&trace, 50); trace.open("large-retained-control.fst");
  auto low = [&] { d.clk_i = 0; d.eval(); };
  unsigned cycles = 0;
  auto step = [&] {
    need(++cycles < 20000, "bounded CSR gate exceeded cycle limit");
    low(); context.timeInc(5); trace.dump(context.time());
    d.clk_i = 1; d.eval(); context.timeInc(5); trace.dump(context.time());
  };
  try {
    need(argc == 2 && (std::string(argv[1]) == "0" || std::string(argv[1]) == "1"),
         "expected exact feature setting0/1 argument");
    const bool enabled = std::string(argv[1]) == "1";
    d.reset_i = 1; d.write_i = d.instret_i = d.ctxtsw_i = d.restore_i = d.status_load_i = 0;
    d.current_thread_i = d.read_thread_i = d.retire_thread_i = 0;
    d.csr_addr_i = 0x5c2; d.decode_write_i = 0; d.read_v_i = 1;
    step(); step(); d.reset_i = 0; step(); low();
    need(bool(d.read_illegal_o) == !enabled, "feature0 must report absent CSR at read interface");
    need(!d.command_o, "reset/idle emitted retained command");

    auto restore = [&](unsigned bank, unsigned privilege) {
      d.write_i = 0; d.instret_i = 0; d.ctxtsw_i = 0;
      d.retire_thread_i = bank; d.restore_priv_i = privilege; d.restore_i = 1;
      step(); d.restore_i = 0; step();
    };
    auto status = [&](uint64_t value) {
      d.write_i = 0; d.instret_i = 0; d.status_i = value; d.status_load_i = 1;
      step(); d.status_load_i = 0; low();
      need(d.model_status_o == value, "external stand-in status load failed");
    };
    auto read = [&](unsigned bank, uint64_t expected) {
      d.read_thread_i = bank; low();
      need(bool(d.read_illegal_o) == !enabled, "feature flag lost on a bank-selected read");
      if (enabled) need(d.read_data_o == expected, "full64-bit global status differs across read banks");
    };
    uint64_t expected = 0xd39a2468ace01230ULL;
    status(expected);
    restore(0, 3); restore(1, 3);
    // Current, reservation/read and retirement banks deliberately disagree.
    // Cover every combination and every control mask, including new bit3.
    for (unsigned mask = 0; mask < 16; ++mask) {
      for (unsigned current = 0; current < 2; ++current)
        for (unsigned reader = 0; reader < 2; ++reader)
          for (unsigned retiring = 0; retiring < 2; ++retiring) {
            d.current_thread_i = current; d.read_thread_i = reader; d.retire_thread_i = retiring;
            d.payload_i = UINT64_C(0xfedcba9876543200) | mask;
            d.write_i = d.instret_i = 1; low();
            need(bool(d.command_o) == enabled, "retirement bank command route/feature gate");
            if (enabled) need(d.control_o == mask, "four-bit payload truncated or contaminated");
            step(); d.write_i = 0; d.instret_i = 0;
            if (enabled) expected = (expected & ~UINT64_C(15)) | mask;
            need(d.model_status_o == expected, "command changed upper/global status or feature0 emitted command");
            read(0, expected); read(1, expected);
          }
    }
    for (unsigned write = 0; write < 2; ++write)
      for (unsigned retired = 0; retired < 2; ++retired)
        for (unsigned ctxt = 0; ctxt < 2; ++ctxt) {
          d.write_i = write; d.instret_i = retired; d.ctxtsw_i = ctxt; d.payload_i = 5;
          low(); need(bool(d.command_o) == (enabled && write && retired && !ctxt),
                      "instret/context-switch/write exclusion");
        }
    d.write_i = d.instret_i = d.ctxtsw_i = 0;
    // A command's privilege must come from its retiring bank, even when the
    // currently decoded instruction belongs to a differently privileged bank.
    for (unsigned priv0 : {0u, 1u, 3u})
      for (unsigned priv1 : {0u, 1u, 3u}) {
        restore(0, priv0); restore(1, priv1);
        for (unsigned current = 0; current < 2; ++current) {
          d.current_thread_i = current; d.read_thread_i = 1-current;
          for (unsigned operation = 0; operation < 2; ++operation) {
            d.decode_write_i = operation; low();
            need(bool(d.illegal_o) == ((current ? priv1 : priv0) == 0),
                 "decoder did not allow S/M or deny U CSR read/write");
          }
          for (unsigned retiring = 0; retiring < 2; ++retiring) {
            d.retire_thread_i = retiring; d.write_i = d.instret_i = 1; d.payload_i = 10; low();
            need(bool(d.command_o) == (enabled && (retiring ? priv1 : priv0) != 0),
                 "command privilege followed active/read bank instead of retirement bank");
            d.write_i = d.instret_i = 0;
          }
          read(0, expected); read(1, expected);
        }
      }
    // Context restore updates banked CSRs; the cache-owned global state is
    // outside the saved image and must not roll back with either bank.
    need(d.model_status_o == expected, "context restore overwrote global status");
    restore(0, 3); restore(1, 3);
    for (unsigned address : {0x5c0u, 0x5c1u, 0x5c3u, 0x7c2u}) {
      d.csr_addr_i = address; d.write_i = d.instret_i = 1; low();
      need(!d.command_o, "neighbor/legacy CSR aliased the new control");
    }
    d.csr_addr_i = 0x5c2; d.write_i = d.instret_i = 0;
    d.read_v_i = 0; low(); need(!d.read_illegal_o, "absent CSR trapped when no read was requested");
    d.read_v_i = 1; low(); need(bool(d.read_illegal_o) == !enabled, "feature0 read legality not restored");
    status(0xbbaa99887766554dULL); read(0, 0xbbaa99887766554dULL); read(1, 0xbbaa99887766554dULL);
    d.final(); trace.close();
    std::cout << "[LARGE-RETAINED-CONTROL] PASS: feature=" << enabled
              << " all4bit masks, exact retirement-bank routing, instret/ctxtsw gates, global64bit status, S/M privilege, U denial, feature0 absent read/no command\n";
    return 0;
  } catch (const std::exception &e) {
    d.final(); trace.close(); std::cerr << "[LARGE-RETAINED-CONTROL] FAIL: " << e.what() << '\n'; return 1;
  }
}
