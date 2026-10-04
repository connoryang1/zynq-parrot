# Exact-placement terminal diagnostic

This diagnostic starts from aligned ELF `90411570...` and changes only the
out-of-loop hardware completion failure reporter. `source_demand` remains at
`0x11e80`, `peer_demand` remains at `0x11ec0`, and both function bodies are
byte-identical to the retained failing ELF. The emitted bit mask is: bit 0,
wrong returning context; bit 1, wrong peer completion count; bit 2, wrong peer
terminal context.

On corrected bitstream `7994ad2f...`, a one-request warmup reports code 6:
context zero returned, but completion and terminal were wrong. This result is
refined by `fpga-failure-zero`.
