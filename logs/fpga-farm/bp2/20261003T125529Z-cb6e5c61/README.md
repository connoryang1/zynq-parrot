This directory preserves the exact routed FPGA package for the rejected fifth-stage context-target dependency interlock. Routing passed, but physical Linux validation found a sustained loaded-target regression, so this image must not replace the qualified baseline.

The immutable revisions are top `cb6e5c6132efdca04a24e2a8ded39e03329c423e` and BlackParrot `116d5c7a380750536c4012ab617c73b8b8cdea8a`. Vivado reports WNS +1.852 ns, WHS +0.020 ns, 50,187 LUTs (94.34%), 28,489 registers, 83.5 BRAM tiles, and 11 DSPs. Package verification reports package SHA-256 `84f4bbd09bdcf4f24107b00daa0aa669d9118bd07dc82543131378c43f593d59` and bitstream SHA-256 `84ea265f3fc33c2647a1afd20fc523d3da466019fafcc835f512047410a4c38d`.

The image passes register-target rings and one-shot resident/nonresident loaded-target probes, but the compact sustained loaded-target ring stalls. The source change was reverted after this result.
