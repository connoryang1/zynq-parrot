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


def check_transcript(transcript, exit_code=0):
    """Raise ValueError unless both guest and host succeeded without other errors."""
    lines = transcript.splitlines()
    core = [i for i, line in enumerate(lines) if CORE_PASS.search(line)]
    host = [i for i, line in enumerate(lines) if HOST_PASS.search(line)]
    if not core or not host:
        raise ValueError("missing CORE PASS or BSG PASS")
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
    args = parser.parse_args()
    try:
        check_transcript(args.log.read_text(), args.exit_code)
    except (OSError, UnicodeError, ValueError) as error:
        print("INVALID RUN: {}".format(error), file=sys.stderr)
        return 1
    print("VALID RUN: guest and host PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
