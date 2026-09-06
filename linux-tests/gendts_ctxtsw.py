#!/usr/bin/env python3
"""Generate the normal BlackParrot DTS with a dedicated context-switch init.

The upstream SDK generator remains the source of truth for the platform.  This
wrapper changes only the exact bootargs string so Linux executes the tiny,
static context-switch proof as PID 1 before BusyBox startup can add noise.
"""

import os
import subprocess
import sys


DEFAULT_BOOTARGS = "console=hvc0 loglevel=8 rdinit=/ctxtsw_user_tiny"
ORIGINAL_BOOTARGS = "console=hvc0 loglevel=8 root=/dev/ram0"


def main() -> int:
    base_generator = os.environ.get("BP_BASE_GENDTS")
    if not base_generator:
        raise SystemExit("BP_BASE_GENDTS must name the SDK gendts.py")

    bootargs = os.environ.get("BP_DEMO_BOOTARGS", DEFAULT_BOOTARGS)
    if '"' in bootargs or "\\" in bootargs:
        raise SystemExit("BP_DEMO_BOOTARGS cannot contain quotes or backslashes")

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

    sys.stdout.write(result.stdout.replace(needle, replacement))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
