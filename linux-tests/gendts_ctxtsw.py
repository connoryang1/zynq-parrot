#!/usr/bin/env python3
"""Generate a BlackParrot DTS with corrected FPGA timebase and selected init.

The upstream SDK generator remains the source of truth for the platform.  This
wrapper changes the exact bootargs string and the historical timer declaration.
Linux then executes the tiny, static context-switch proof as PID 1 before
BusyBox startup can add noise.
"""

import os
import subprocess
import sys


DEFAULT_BOOTARGS = "console=hvc0 loglevel=8 rdinit=/ctxtsw_user_tiny"
ORIGINAL_BOOTARGS = "console=hvc0 loglevel=8 root=/dev/ram0"
ORIGINAL_TIMEBASE = "timebase-frequency = <10000000>;"
DEFAULT_TIMEBASE_FREQUENCY = 8_000_000


def main() -> int:
    base_generator = os.environ.get("BP_BASE_GENDTS")
    if not base_generator:
        raise SystemExit("BP_BASE_GENDTS must name the SDK gendts.py")

    bootargs = os.environ.get("BP_DEMO_BOOTARGS", DEFAULT_BOOTARGS)
    if '"' in bootargs or "\\" in bootargs:
        raise SystemExit("BP_DEMO_BOOTARGS cannot contain quotes or backslashes")
    try:
        timebase_frequency = int(os.environ.get(
            "BP_DEMO_TIMEBASE_FREQUENCY", str(DEFAULT_TIMEBASE_FREQUENCY)))
    except ValueError as error:
        raise SystemExit("BP_DEMO_TIMEBASE_FREQUENCY must be an integer") from error
    if not 1 <= timebase_frequency <= 0xFFFFFFFF:
        raise SystemExit("BP_DEMO_TIMEBASE_FREQUENCY must fit a nonzero 32-bit cell")

    result = subprocess.run(
        [sys.executable, base_generator, *sys.argv[1:]],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    needle = 'bootargs = "{}";'.format(ORIGINAL_BOOTARGS)
    replacement = 'bootargs = "{}";'.format(bootargs)
    if result.stdout.count(needle) != 1:
        raise SystemExit("SDK DTS bootargs template changed; refusing an ambiguous image")

    output = result.stdout.replace(needle, replacement)
    if output.count(ORIGINAL_TIMEBASE) != 1:
        raise SystemExit("SDK DTS timebase template changed; refusing an ambiguous image")
    output = output.replace(
        ORIGINAL_TIMEBASE,
        f"timebase-frequency = <{timebase_frequency}>;")
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
