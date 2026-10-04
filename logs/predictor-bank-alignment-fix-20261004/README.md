# Context-redirect predictor-bank alignment fix

This directory records the simulation evidence for aligning frontend predictor
requests and results with the destination hardware thread during a context
redirect. It also connects the RTL defect to the preceding physical code-placement
experiments without claiming FPGA validation before a new routed image is tested.

## Root-cause evidence

The BTB and BHT are synchronous and replicated per resident hardware thread.
Before the fix, an explicit context redirect updated `thread_id_r` at the clock
edge but gated the same edge's predictor read with the old `thread_id_r`. The
following cycle could therefore select the new bank while consuming a result
read from the old bank. Because the predictor indexes by PC, whether the stale
row causes visible control-flow damage depends on code placement and predictor
history.

The physical experiments retained under
`logs/linux-hardware-demand-{post-switch-nop,placement-11f00}-20261004` and
`logs/linux-hardware-demand-stale-peer-probe-20261003` found:

- the original loops at `0x11e80`/`0x11ec0` failed after 50 successful launches;
- inserting a terminal-path `nop` at those addresses still failed in sample 5;
- the original instructions at `0x11f00`/`0x11f40` passed 512 launches;
- a terminal-resume detector at the passing addresses completed another 640
  launches without firing.

This isolates the symptom to absolute PC placement and rejects the parked-PC
and immediate-terminal-fallthrough explanations. The predictor-bank mismatch is
the existing frontend mechanism that explains that PC-sensitive behavior.

## RTL change

BlackParrot commit `3c8c16aca` selects `redirect_thread_id_i` for the redirect
cycle's predictor read, records the bank identity whenever the I-cache accepts a
read, and uses that recorded identity for the synchronous BTB/BHT result and
metadata. The bank identity holds across frontend stalls together with the
memory result.

## Verification

All runs used two resident hardware threads and traced simulation. The
nonresident tests used four logical contexts.

| Gate | Result | Meaning |
|---|---:|---|
| `mt_ctxtsw_gpr_ring_stress` | PASS | All GPRs survived a four-context ring. |
| `analyze_predictor_alignment.py` | PASS | 10,942 accepted reads and 10,941 returned results preserved bank provenance; four explicit redirects used their destination bank immediately. |
| `mt_ctxtsw_register_target_test` | PASS | Register-carried targets and computed returns remained correct. |
| `mt_umode_nonresident_sv39_data_handoff_test` | PASS | Nonresident instruction/data and address-space handoff redirected before sequential issue. |
| `mt_ctxtsw_target_bypass_stress_test` after a clean model rebuild | PASS | Sustained redirect target bypass completed after 34,737 retired instructions. |
| `mt_ctxtsw_nonresident_overhead_benchmark` | PASS | Warm 5.13, cold 9.26, incremental 4.13 cycles/switch, exactly matching the prior accepted same-configuration simulation. |

The clean model executable SHA-256 is
`286f4f9eae6e5bb814c4d4a9ff4709cced9c4ac3b482f5f4ad477efdd4e2b060`.
Each test directory contains its exact executable, closed waveform, run log, and
hashable immutable copies. The next acceptance step is a routed PYNQ-Z2 image
followed by repeated execution of the previously failing-address binary; the
current physical board evidence still uses the pre-fix bitstream.
