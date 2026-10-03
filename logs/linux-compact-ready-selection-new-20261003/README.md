This compact matched ring tests register, loaded, and no-bubble ready-bitmap targets on the routed fifth-dependency-stage candidate. Each policy uses a 128-round-trip loop followed by a direct drain, avoiding the earlier unrolled harness's large code footprint.

Register-target context 1 passed in 2,030 cycles for 258 measured operations (7.86 cycles each including two drains), and context 2 passed in 3,171 cycles (12.29 each). The following sustained loaded-target context-1 case stalled, so bitmap modes were not reached. One-shot loaded-target probes pass on the same image, localizing the regression to recurring producer/switch dependencies across handoffs.

The exact ELF SHA-256 is `bb8c9de49e19cb9780400a328b52fe38b9d1b38a85373efffd8a4187707f40c6`; the bitstream SHA-256 is `84ea265f3fc33c2647a1afd20fc523d3da466019fafcc835f512047410a4c38d`. The stalled run was interrupted and the candidate is rejected.
