This gate checks that splitting the retained store into private I/D RAMs preserves its directed behavior and cycle timing. It compares the modified implementation against the original shared-RAM implementation under identical inputs while retaining the existing full-payload and coherence checks. It does not establish synthesis inference, routed fit, full-core correctness, or physical capacity.

Run from the repository root with a fresh external output directory:

```sh
python3 testing/rtl/retained-private-sp/run.py \
  --verilator /home/coyang/zynq-parrot-linux-research/install/bin/verilator \
  --output /absolute/fresh/output
```

The default matrix has twelve capacity pairs: 0/0, 64/0, 0/64, 64/64, 128/128, 256/256, 512/512, 1024/1024, 1280/1280, 1320/1320, 1536/1536, and unequal partial 93/131. Every pair uses both opposite-phase clocks and different-period clocks. The original directed driver exercises all eight payload words, capacity, replacement, duplicate updates, high physical addresses, overlapping lane writes, invalidation, response backpressure, cancellation, clear, and epoch wrap.

The runner extracts the exact original backend from BP revision `e10992a3eea3ba2ef6ae3ccb42ff5e8c658286a8` and generates a dual-instance wrapper. After every settled Verilator evaluation, it compares all client control signals, valid-hit 512-bit responses, and enabled logical global RAM addresses/write data. It also requires the FSM, policy, and assertion source tail to remain byte-identical. The existing driver checks remain intact; the generated driver adds only comparison checks and a comparison-sample count. RAM contents on invalid/miss responses are outside the client contract and are not compared.

Fresh per-geometry builds use assertions, warnings as errors, two compiler jobs, and closed FSTs. Each build is bounded to 300 seconds, each runtime to 120 seconds, and each output file to 64 MiB. Inputs and generated sources are hashed, with an end-of-run input drift check. The recorded full-payload checks use 64 retained sets and a two-bit epoch to force wrap; synthesis and any production-geometry full-core gates remain separate.

`check_sensitivity.py` takes the same `--verilator` and fresh `--output` arguments. It deliberately XORs one bit into the generated reference RAM read data and requires exit 1 with the exact cycle-mismatch failure and no PASS marker. Production RTL remains unchanged.
