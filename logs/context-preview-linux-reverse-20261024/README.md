This directory records a physical Linux control that reverses the issue order of four exact data hints. It tests whether the intermittent slow load observed on target line 1 follows the hint's issue position while keeping the target addresses and load order fixed.

# Reverse hint issue order, 2026-10-24

The routed ten-context bitstream SHA-256 was `f234819855ee79028ccf6387a356fe297962b9e30e36420f4da224150384a7b8`, the non-debug shell NBF SHA-256 was `892b19f7a9d697bfc84adc2853e2fe9165a92ced7305a4971d2bb7577c8b1438`, and the guest ELF SHA-256 was `23b0e1622a63faa7247b7e97d1cf51a238c5bfdcf3a0e97817ad8e595e128e8f`. The line-ending-normalized `board.log` SHA-256 is `c89a6d21624e7607d5f1b4f879982a03fe4fd3a0b213a89b56db85c3a9915971`; the original terminal stream SHA-256 is `f08c80b4a9fc556804dab90eac4cf532acbbca756c9301089d9559849ce68927` and remains local as `board.raw.log`. Run `python3 audit_run.py` to recheck 112 benchmark and per-load row pairs, hashes, exact cycle sums, and clean completion.

| Mode | Hint issue order | Trials | Slow line 0 | Slow line 1 | Slow line 2 | Slow line 3 | Median four loads |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 0, 1, 2, 3 | 16 | 0 | 6 | 0 | 0 | 50 |
| 6 | 3, 2, 1, 0 | 16 | 0 | 3 | 0 | 0 | 50 |

"Slow" means more than 15 cycles between the surrounding global-cycle reads. The fast floor was 10–14 cycles, while slow line-1 samples were 42–64 cycles in these two modes. Static disassembly confirmed the four `ori zero, addr, 1` hints reference target lines 3, 2, 1, 0 in mode 6. In both orders, the intermittent delay remains on line 1; line 2, which becomes the second issued hint in reverse order, is fast in all 16 reverse trials. This weakens an issue-position explanation. It does not yet separate target address or cache set from *second demand-load position*, because the peer always loads lines 0, 1, 2, 3. Reversing the peer's load order while holding hint order fixed is the next discriminating control.

The result is a first-use mechanism diagnostic, not a whole Linux handoff speedup. This run uses the same exact-address, same-process oracle and extra per-load timestamps as the preceding diagnostic.
