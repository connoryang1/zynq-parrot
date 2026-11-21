#include "Vptr.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <iostream>
int main() {
  VerilatedContext context; context.randReset(2); context.traceEverOn(true);
  Vptr dut{&context}; VerilatedFstC trace; dut.trace(&trace,20); trace.open("ptr.fst");
  auto eval=[&]{dut.eval();context.timeInc(5);trace.dump(context.time());};
  auto step=[&]{dut.clk_i=0;eval();dut.clk_i=1;eval();};
  dut.reset_i=1;dut.add_i=0;step();step();dut.reset_i=0;
  for (unsigned k=0;k<60;++k) {
    dut.clk_i=0;dut.add_i=1;eval();step();
    dut.add_i=0;eval();
    if (dut.next_o!=dut.ptr_o || dut.ptr_o>=3) return 2;
  }
  dut.final();trace.close();std::cout<<"PTR_EXACT_UNCHANGED_COMPONENT_PASS\n";
}
