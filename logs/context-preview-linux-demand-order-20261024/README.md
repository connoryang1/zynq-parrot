This directory records a physical Linux control that reverses the peer's four target-data loads. It compares matched direct and exact-hint modes with forward and reverse demand order to test whether the long first-load interval follows a physical target line or the load's execution position.

# Reverse target demand order, 2026-10-24

The routed ten-context bitstream SHA-256 was `f234819855ee79028ccf6387a356fe297962b9e30e36420f4da224150384a7b8`, the non-debug shell NBF SHA-256 was `892b19f7a9d697bfc84adc2853e2fe9165a92ced7305a4971d2bb7577c8b1438`, and the guest ELF SHA-256 was `51a7f58713bd7cf4dd4e71803b3a8031ee6e9acf29a8292fd2d6d9679db8ab02`. The line-ending-normalized `board.log` SHA-256 is `adf106c935872eee924b19941494474dc8c84f6c5c86eb5a181a523da4b49ae9`; the original terminal stream SHA-256 is `e9ff4db399c181acc62f36f9ef02de6a145532e7ed1bd0f0d6b3dc9e64311f04` and remains local as `board.raw.log`. Run `python3 audit_run.py` to verify all 144 benchmark and per-load row pairs, exact cycle sums, guest hash, and clean host completion.

| Mode | Hints | Peer load order | Median cycle intervals in execution order | Median four loads |
| --- | --- | --- | --- | ---: |
| 0 | none | 0, 1, 2, 3 | 122, 53, 57, 53 | 285 |
| 4 | 0, 1, 2, 3 | 0, 1, 2, 3 | 67, 16, 16, 16 | 115 |
| 7 | none | 3, 2, 1, 0 | 122, 50, 58, 50 | 281 |
| 8 | 0, 1, 2, 3 | 3, 2, 1, 0 | 64, 13, 21, 13 | 111 |

Each mode has 16 rotated trials. The output labels `l0` through `l3` by physical target-line index, while the table orders intervals by execution position. The long first-load interval moves from line 0 to line 3 when demand order reverses, in both direct and hinted controls. In mode 8, line 1 is the third demand and stays at 21 cycles in 15 of 16 trials (17 in the remaining trial); line 2 is the second demand and has four intervals of 30–60 cycles. In mode 4, line 1 is the second demand and has one 60-cycle interval. This weakens the earlier interpretation that the occasional slow interval is inherently tied to line 1's address; demand position and code layout matter.

The first-load interval includes more than data service and remains roughly 64–67 cycles even with exact hints, versus 122 cycles direct. Per-load cycle reads, extra branches, and the changed ELF layout affect the absolute values. This control does not identify whether an individual hint was accepted, completed, or evicted, and it does not establish a whole Linux handoff speedup. Future request-level instrumentation needs an image that implements both the preview path and the recorder; the exact preview image here lacks recorder CSR `0x805`.
