This directory records a physical Linux diagnostic that times each of the four target-data loads separately. It locates the intermittent first-use delay within the correct-hint trials while preserving direct, empty, and stale controls on the same routed FPGA image.

# Per-load preview timing, 2026-10-24

The routed ten-context bitstream SHA-256 was `f234819855ee79028ccf6387a356fe297962b9e30e36420f4da224150384a7b8`, the non-debug shell NBF SHA-256 was `892b19f7a9d697bfc84adc2853e2fe9165a92ced7305a4971d2bb7577c8b1438`, and the guest ELF SHA-256 was `0567ad7db3fe36385f7d05f0b776db3d1fb8a54a019a331f11898fdc3471ec7c`. The line-ending-normalized `board.log` SHA-256 is `d38db4f9874ebb609e5c9502681fcb317ca5f83edf3c0a2b3645ea883df6e759`; the original byte stream SHA-256 is `3b9e754a25ed32d403211e4261ab9ca50a253b139361b3343962db048acf011c` and remains local as `board.raw.log`. Run `python3 audit_run.py` to verify 48 trial and per-load pairs, their exact cycle sums, the guest hash, and clean completion markers.

| Mode | Preview | Median line 0 | Median line 1 | Median line 2 | Median line 3 | Median four loads |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 0 | direct | 119.5 | 47 | 47 | 47 | 286 |
| 1 | empty helper | 91 | 47 | 47 | 48 | 286 |
| 2 | correct helper | 12 | 10 | 10 | 10 | 68 |
| 3 | stale helper | 122 | 79.5 | 47 | 47 | 290.5 |
| 4 | correct inline | 12 | 10 | 10 | 10 | 42 |
| 5 | stale inline | 102.5 | 47 | 47 | 47 | 261 |

Each mode has eight rotated trials. The timing inserts a cycle read after each volatile load, so its four-load intervals are not directly comparable to the earlier uninstrumented values. Within this run, lines 2 and 3 are at the 10-cycle floor in all 16 correct-hint trials, and line 0 is near that floor in 15 of 16. Line 1 is slow in three of eight correct-helper trials (84, 93, and 126 cycles) and two of eight correct-inline trials (124 and 150 cycles). Thus the variable four-load result is concentrated on one address; this evidence does not yet distinguish whether that hint was dropped, late, or displaced. Reversing hint order while preserving target addresses is the next causal control.
