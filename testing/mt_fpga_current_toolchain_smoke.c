/**
 * Current-toolchain FPGA smoke probe.
 *
 * Intentionally performs no context initialization or switching. This
 * distinguishes generic ELF/NBF startup compatibility from multicontext RTL.
 */

#include "bp_utils.h"

int main(void) {
  bp_print_string("[BSG-PASS] current-toolchain FPGA smoke reached main\n");
  bp_finish(0);
  return 0;
}
