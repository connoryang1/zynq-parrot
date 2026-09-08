#!/usr/bin/env python3
"""Fail closed on incomplete or failed simulator transcripts.

The caller must remove the previous log before starting the run: text alone
cannot prove freshness. Only the documented post-PASS GPIO shutdown failure is
an accepted exception to a successful process exit.
"""

import argparse
from pathlib import Path
import re
import sys


CORE_PASS = re.compile(r"\bCORE(?:\[\d+\])?\s+PASS\b")
HOST_PASS = re.compile(r"\bBSG PASS\b")
FAIL = re.compile(r"\bCORE(?:\[\d+\])?\s+FAIL\b|\bBSG[- ]FAIL\b")
TIMEOUT = re.compile(
    r"(?:time[ -]?out|runtime limit).*?(?:reached|exceeded|expired|fired)"
    r"|(?:reached|exceeded).*?(?:time[ -]?out|runtime limit)", re.I)
ERROR = re.compile(r"%Fatal|%Error|\bERROR\b|\bFATAL\b|\bAborting\b"
                   r"|\bassert(?:ion)?\b.*\bfail(?:ed|ure)?\b", re.I)
GPIO_FATAL = re.compile(
    r"^(?:\[\d+\]\s*)?%Fatal: .*\bbsg_nonsynth_dpi_gpio\.sv:\d+: .*"
    r"final block executed before fini\(\) was called\s*$")
GPIO_STOP = re.compile(
    r"^%Error: .*\bbsg_nonsynth_dpi_gpio\.sv:\d+: Verilog \$stop\s*$")

# Match the selected program's completed checks, not just the common CRT exit.
# The benchmark banner is emitted only after both measured rings return.
TEST_MARKERS = {
    "mt_ctxtsw_smoke_test": "[BSG-PASS] ctxtsw smoke test completed",
    "mt_ctxtsw_logical_csr_readback_test": "[BSG-PASS] logical context CSR reported 0 -> 1 -> 0",
    "mt_regfile_test": "ALL TESTS PASSED",
    "mt_csr_isolation_test": "[BSG-PASS] CSR isolation verified",
    "mt_frf_isolation_test": "[BSG-PASS] FP regfile isolation verified",
    "mt_abi_preservation_test": "[BSG-PASS] ABI state preserved across ctxtsw",
    "mt_ctxtsw_register_target_test": "[BSG-PASS] register targets and computed returns",
    "mt_ctxtsw_late_wb_hazard_test": "[BSG-PASS] ctxtsw late writeback hazard test completed",
    "mt_ctxtsw_load_overlap_test": "[BSG-PASS] resident delayed-load and load-ahead data/register checks",
    "mt_load_ahead_benchmark": "[BSG-PASS] load-ahead benchmark completed",
    "mt_request_interleave_benchmark": "[BSG-PASS] independent requests",
    "mt_ctxtsw_gpr_ring_stress": "[BSG-PASS] all GPRs preserved through 4-context ring",
    "mt_ctxtsw_pure_ring_stress_test": "[BSG-PASS] pure ctxtsw ring stress completed",
    "mt_umode_resident_sv39_data_handoff_test": "[BSG-PASS] resident U-mode Sv39 instruction/data handoff and ECALL preserved state",
    "mt_umode_nonresident_handoff_test": "[BSG-PASS] U-mode nonresident bare handoff redirected before sequential issue",
    "mt_umode_nonresident_sv39_handoff_test": "[BSG-PASS] U-mode nonresident Sv39 instruction handoff redirected before sequential issue",
    "mt_umode_nonresident_sv39_data_handoff_test": "[BSG-PASS] U-mode nonresident Sv39 instruction/data handoff redirected before sequential issue",
    "mt_ctxtsw_nonresident_overhead_benchmark": "=== Nonresident Context Switch Overhead Benchmark ===",
}


def check_transcript(transcript, exit_code=0, test=None):
    """Raise ValueError unless both guest and host succeeded without other errors."""
    lines = transcript.splitlines()
    core = [i for i, line in enumerate(lines) if CORE_PASS.search(line)]
    host = [i for i, line in enumerate(lines) if HOST_PASS.search(line)]
    if not core or not host:
        raise ValueError("missing CORE PASS or BSG PASS")
    if test is not None:
        if test not in TEST_MARKERS:
            raise ValueError("unknown test: {}".format(test))
        if not any(line.strip() == TEST_MARKERS[test] for line in lines[:core[0]]):
            raise ValueError("missing success marker for {} before CORE PASS".format(test))
    if any(FAIL.search(line) or TIMEOUT.search(line) for line in lines):
        raise ValueError("guest failure or runtime timeout")

    errors = [(i, line.strip()) for i, line in enumerate(lines) if ERROR.search(line)]
    known_shutdown = (
        len(errors) == 3
        and errors[0][0] > max(core[-1], host[-1])
        and errors[1][0] == errors[0][0] + 1
        and errors[2][0] == errors[1][0] + 1
        and GPIO_FATAL.fullmatch(errors[0][1]) is not None
        and GPIO_STOP.fullmatch(errors[1][1]) is not None
        and errors[2][1] == "Aborting..."
    )
    if errors and not known_shutdown:
        raise ValueError("unexpected error or assertion in simulator transcript")
    if exit_code != 0 and not known_shutdown:
        raise ValueError("simulator exited with status {}".format(exit_code))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("--test", choices=sorted(TEST_MARKERS))
    args = parser.parse_args()
    try:
        check_transcript(args.log.read_text(), args.exit_code, args.test)
    except (OSError, UnicodeError, ValueError) as error:
        print("INVALID RUN: {}".format(error), file=sys.stderr)
        return 1
    print("VALID RUN: guest and host PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
