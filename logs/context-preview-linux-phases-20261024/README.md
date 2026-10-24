This directory records phase timing for the physical Linux target-data preview oracle. It corrects the earlier run's total endpoint by measuring peer entry and peer-load completion directly, while retaining the full four-mode control matrix and its validation evidence.

# Physical Linux preview phases, 2026-10-24

The verified routed ten-context bitstream SHA-256 was `f234819855ee79028ccf6387a356fe297962b9e30e36420f4da224150384a7b8`; the non-debug shell NBF SHA-256 was `892b19f7a9d697bfc84adc2853e2fe9165a92ced7305a4971d2bb7577c8b1438`. The phase-instrumented dynamic ELF SHA-256 was `d0b2dd2cd2d305af45d29067c180ba24cad371fc6417472b587f57305ced1284`. The line-ending-normalized `board.log` SHA-256 is `1dd950bc4ec756072eb3f7c079b0c7ee94bc9b5820e12bd80edfbd83ce7ff2da`; the original terminal byte stream SHA-256 is `7c8166878265758a03e609a5ddef558499fbae5a2f066fa676f32a274ba5ac1e` and remains local as `board.raw.log`. Run `python3 audit_run.py` to recheck all 32 rows, guest hash, guest and host pass markers, clean poweroff, and the runner status.

| Mode | Preview | Preview duration | Peer four loads | Source start to peer completion | Source round trip |
| --- | --- | ---: | ---: | ---: | ---: |
| 0 | direct | 2 | 188 | 23,476.5 | 54,744 |
| 1 | empty | 165 | 186 | 23,598.5 | 41,015.5 |
| 2 | correct | 166 | 8 | 32,704 | 56,467.5 |
| 3 | stale | 169.5 | 198.5 | 19,756 | 55,232 |

Values are medians of eight rotated trials per mode in core-wide cycles (`0xcc0`). Correct hints make the peer's first four loads fast, but the one-way completion times vary widely and establish no overall speedup. The preview helper costs about 166 cycles, close to the direct-to-correct load difference of 180 cycles in this run. The source's `futex_wake` return occurs after peer entry in multiple trials, so wake-return time cannot substitute for peer startup. The application knows the target addresses and runs the helper in the source process; it is not a kernel-owned scheduler hint.

## Recovery after the first attempt

The first attempt used the correct bitstream and NBF but stopped producing console output after the kernel's `/bin/sh` launch line. No application data was produced, and its cause is undetermined. After the interrupted runner, the board was power cycled, the PYNQ readiness check passed at 93 seconds of uptime, and the same verified overlay was reloaded before the accepted second attempt. The failed attempt's status and short transcript remain local in this directory; only the clean run supports the measurements above.
