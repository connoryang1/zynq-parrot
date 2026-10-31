This directory records exact-image FPGA measurements of conditional Linux instruction-prefix replay. It preserves the accepted timing batches, rejected boots, and interpretation rules needed to reproduce the result without treating incomplete miss traces as invalid timing samples.

# Conditional Linux prefix replay

The routed design is top-level `3a08584daff9d070c4e1429eda81b6da63929ff5` with BlackParrot `b1a06528161ca5ac08835268698320086e6fd4dd`; the bitstream SHA-256 is `e1e66020ef2cf1a286077229ecd8a62d8ef56ca68bd3497afe0dfc91a7492338`. Linux executes `csrw 0x5c0, zero` only inside `if (likely(prev != next))`, after `pick_next_task()`. The exact measurement ELF has SHA-256 `14bf2ab9c232d5c71c21a6204c3dfaa6ee42e3e949d63d994168b1a84da1bf4d`.

The four replay targets are the first four distinct instruction lines demanded after that trigger in a fresh replay-disabled source-to-peer trace. Their addresses and selection policy are retained in `targeted-prefix-results.json`.

## Exact-image prefix sweep

The disabled and four-line images are the original matched `/bin/sh` comparator images. The one-, two-, and three-line images retain every original NBF write and add one final aligned write before unfreeze that changes only the compressed `addi a5,a5,4` count operand at `0x80006dba`. Reconstructing the loaded bytes finds exactly one differing byte from the four-line image for each arm.

| Arm | NBF SHA-256 | Final aligned write |
| --- | --- | --- |
| disabled | `eee6fa9ff26307f7b8f0edf3cf3e2718f2a6ad2a073a11fa87aa6c27235fe716` | none |
| one line | `066f02cdd52536c00cadbdef60c9fce2cff1cd08d9819419e25e2cee0e5b93d4` | `03_0000000080006db8_7c279073078517fe` |
| two lines | `b9b9e93ee931c579e2f20ef958077f5f0cbe942bbb6b16de9cabc879c14e8c6a` | `03_0000000080006db8_7c279073078917fe` |
| three lines | `3a8ae8538caff5329b8591806d416c2f009bfd8aca857c3a1efbfccd8aa8bc48` | `03_0000000080006db8_7c279073078d17fe` |
| four lines | `05f77de44c26096d73a47e916a59128c3eb01206e9609a07aef64f7ebb1423d9` | original image |

Each primary 50-sample arm used a fresh power cycle, readiness wait, hash-checked overlay and image, one unrecorded warmup, and `--window to-peer --summary-only`. The one-line arm stopped at 14 exploratory samples because it already trended slower. Every completed primary 50-sample run ended with `CORE PASS` and `BSG PASS`.

`elapsed` equals `peer_begin - start`, so it remains a valid timing endpoint when `i_overflow=1`; overflow only says that the 256-entry instruction-miss history is incomplete. Excluding overflow cases censors the slow intervals and biases the median downward. The earlier seven-sample non-overflow comparison is therefore retained only as superseded evidence.

| Active lines | Samples | I-trace overflows | Median cycles | Mean cycles | Q1--Q3 | Median change vs disabled |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 50 | 11 | 14,463.5 | 21,237.7 | 12,259.5--17,947.5 | baseline |
| 1 | 14 | 6 | 17,026.5 | 28,201.1 | 12,303.5--42,119.75 | +17.7% |
| 2 | 50 | 16 | 17,003 | 23,715.2 | 12,196.75--37,583 | +17.6% |
| 3 | 50 | 11 | 14,028 | 20,920.8 | 11,532--20,019.25 | -3.0% |
| 4 | 50 | 14 | 14,519 | 22,487.8 | 11,355.5--37,606 | +0.38% |

A deterministic 100,000-resample bootstrap gives a three-minus-disabled median-difference interval of `[-2,349, +1,872]` cycles and only 71.0% resamples favoring three lines. Four lines gives `[-2,347.5, +3,389.5]` cycles and 44.2% favoring replay. Two lines has a `+2,539.5`-cycle point estimate with interval `[-2,097.5, +16,911]`. None demonstrates a speedup; three lines is merely the best point estimate in this noisy sweep.

Full transcripts and SHA-256 values are summarized in `matched-results.json`. The primary transcript hashes are:

- disabled: `31885d204708731c4690921bbac3d6986c567eb33f9ec7ede6215c809f61eaf6`;
- one line: `83511b9b293c6760aad68b2c450d1cbc3df76f140460a38ac1f9551587f72e9c`;
- two lines: `2edd7b71407a2863c5fa1db1fc761c1c853d5e935fe4cff0018b1d465ccd9035`;
- three lines: `6d3adc0b58ac33bbbf21eaa104c15386f5d5919e289f1ae7b5f957b0298578b4`;
- four lines: `06758a5ab425ffbb20bc579e409df82563ea31924fc676a739590dd3012e9e06`.

## Rejected runs and guardrails

The first exact two-line boot reached `Run /bin/sh as init process` but never produced a prompt and hit the native target-runtime limit. It was power-cycled and excluded; the retry booted and completed normally. The first three-line boot panicked in `scheduler_tick` before the benchmark, while a fresh power-cycle retry booted and completed normally; it is likewise excluded rather than interpreted as replay performance.

During the next three-line retry, an overlong single-line base64 paste exceeded the guest PTY's safe line length and left the shell at a continuation prompt. That run was terminated, power-cycled, and excluded. Future interactive binary transfers must use bounded chunks (512 base64 characters were used successfully). The rejected transcripts are retained as `raw/target2-exact-boot-stall-*`, `raw/target3-exact-boot-failure-local.log`, and `raw/target3-exact-transfer-contaminated-local.log`.

An earlier rebuilt two-line image (`10d77bbd...ffb4`) booted `/init` rather than the direct `/bin/sh` comparator payload. It remains invalid packaging evidence only; the exact one-byte image above supersedes it.

## Conclusion

Conditional replay can cover the selected demand misses, but the complete exact-image size sweep does not show an end-to-end Linux handoff speedup. The useful work is too small relative to the roughly 14.5k-cycle median and highly variable scheduler path. Further tuning of this four-address instruction prefix is not justified; the next performance experiment should change the target class or lead time, such as a data footprint or a pre-switch hint, rather than add more prefix-size points.
