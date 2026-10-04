# Hardware-demand lifecycle isolation

This run asks whether the longer demand-path attribution failure requires its
four mixed benchmark modes. It executes only `resident-demand-handoff` from the
same newer ELF for 64 requested samples on the same FPGA image.

The warmup and samples 1--26 complete with the expected 8,192 requests and
checksum. Sample 27 prints its begin marker and then reports
`hardware context/completion verification failed`; it never produces a result
or returns to the shell before the ten-minute control watchdog ends the run.
The 26-row prefix is diagnostic and is **not an accepted performance result**.

This changes the lifecycle diagnosis in three useful ways:

- Mixed benchmark modes are not required: demand-only execution also fails.
- There is no deterministic 16-sample boundary: this run reaches 26, whereas
  the mixed run reaches 16 samples per mode.
- The older demand-only ELF completes all 32 requested hardware samples on the
  same bitstream. Its `source_demand` and `peer_demand` opcode sequences are
  byte-for-byte identical to the newer ELF, but both functions move forward by
  264 bytes (`0x11d50` to `0x11e58` and `0x11d90` to `0x11e98`).

Code placement or accumulated architectural/microarchitectural state is
therefore plausible, but neither is established. In particular, the address
shift is not evidence by itself of an instruction-cache conflict. The generic
verification message also does not reveal whether the wrong value was the
returning context, peer completion count, or peer terminal context. A useful
next experiment must print all three values and vary code placement while
leaving the measured routines unchanged.

The follow-up experiments show that placement alone is not a fix. A reporting
variant whose functions move 32 bytes completes 64 samples, but a controlled
variant with both loops aligned to 64-byte boundaries stops inside sample 51;
an exact-ELF repeat stops inside sample 3. The aggregate evidence supports an
intermittent sustained-handoff hazard. See
`logs/linux-hardware-demand-lifecycle-repeats-20261003/`.

The physical identities are:

| Artifact | SHA-256 |
| --- | --- |
| New guest ELF | `8d95f0cfbf91686836ab72b2fe3029bdee1f338a2658774ca1034debf5b1d643` |
| Older 32-sample-passing guest ELF | `de53ce7c669c469630367b4b93e512a2f85ea5a8b6337c787ad7eb4b5971d2ee` |
| Bitstream | `9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf` |
| Linux shell NBF | `af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3` |

Reproduce the analysis with:

```sh
python3 -B logs/linux-hardware-demand-lifecycle-isolation-20261003/analyze.py \
  > logs/linux-hardware-demand-lifecycle-isolation-20261003/analysis.stdout
cmp logs/linux-hardware-demand-lifecycle-isolation-20261003/analysis.json \
  logs/linux-hardware-demand-lifecycle-isolation-20261003/analysis.stdout
```
