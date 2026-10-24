This directory records a fresh-boot physical Linux comparison of direct source-thread hints with the earlier hardware-context preview helper. It retains all 48 trials and the board audit so hint issue cost can be separated from the reliability of the peer's first data loads.

# Inline source-hint control, 2026-10-24

The routed ten-context bitstream SHA-256 was `f234819855ee79028ccf6387a356fe297962b9e30e36420f4da224150384a7b8`, the non-debug shell NBF SHA-256 was `892b19f7a9d697bfc84adc2853e2fe9165a92ced7305a4971d2bb7577c8b1438`, and the guest ELF SHA-256 was `677379a38b8896e65cc340263a875db8a5dd6e5c8501c41f6edfb3cb14159a52`. The line-ending-normalized `board.log` SHA-256 is `10243cabbf53058f23589ccb257e3245c952f0f82fd87f355a3990f2518ba42e`; the original terminal stream SHA-256 is `a8462d51cb3463d98dd3f700499b42236786609303b16af72c7b97293dc716ab` and remains local as `board.raw.log`. Run `python3 audit_run.py` to verify all modes, rows, hashes, markers, and clean shutdown.

| Mode | Preview | Median hint phase | Median peer four loads | Median source start to peer completion |
| --- | --- | ---: | ---: | ---: |
| 0 | direct | 9 | 169 | 22,261.5 |
| 1 | empty helper | 151 | 187 | 38,925.5 |
| 2 | correct helper | 141 | 41 | 19,845 |
| 3 | stale helper | 142 | 199 | 29,903.5 |
| 4 | correct inline | 19 | 95.5 | 28,256 |
| 5 | stale inline | 22 | 177 | 19,444.5 |

All values are medians from eight rotated trials per mode in core-wide cycles (`0xcc0`). The inline hints remove most of the helper cost, but their peer-load timing is variable: the eight correct-inline four-load intervals are 224, 183, 41, 8, 8, 158, 41, and 150 cycles. Correct-helper reaches the eight-cycle floor in only two of eight trials in this six-mode run. Its earlier four-mode median was eight cycles; mode count, order, and ELF layout changed, so these are separate matched experiments. The broad one-way times and lack of stable mode ordering do not establish an end-to-end gain or loss.

The next diagnostic must identify whether each hint was accepted and completed before demand, displaced from the side buffer, or too late. The four-load sum alone cannot distinguish those mechanisms. Both inline modes use source-process addresses and are oracle controls, not Linux task prediction or a scheduler interface.
