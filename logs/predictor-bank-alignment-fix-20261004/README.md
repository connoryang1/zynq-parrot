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

## FPGA acceptance status

The first routed candidate, job `20261004T050934Z-2bcf8b5e`, used
`e_bp_unicore_zynqparrot_prefetch_cfg` and passed timing at WNS `+1.953 ns`
and WHS `+0.023 ns`. It cannot qualify the retained failing-placement ELF:
that ELF was compiled with `BP_NUM_CONTEXTS=10`, while this endpoint has two
logical contexts. CSR `0x802` places the five-bit register address immediately
above the context ID, so the binary encodes it at bit 43 while the two-context
hardware decodes it at bit 40. The attempted peer launch therefore reached its
correct seeded NPC but did not seed `a0` through `a4`; it faulted at `0x11ed4`
on address zero. This is recorded as an excluded configuration mismatch, not
an RTL failure.

Corrected job `20261004T060922Z-2bcf8b5e` uses the same two-resident,
ten-logical-context endpoint as the failing baseline. It routes cleanly at WNS
`+1.528 ns` and WHS `+0.030 ns`, with 50,730 LUTs, 28,385 registers, 83.5
BRAM tiles, and 11 DSPs. Relative to the last qualified image, this is +77 LUTs
and +1 register; BRAM and DSP use are unchanged. The package SHA-256 is
`8fba9bfc79cc919dd8c7fdfb2e285784abb90dec478228f7cce316537e856f5e`, and
the contained bitstream SHA-256 is
`7994ad2f6cb2ee108452b9f89e600b2e74cab2e6f64077604c5d4fb49e0eb5dd`.

The last physically qualified 10-context image used top `7a38ae96` and
BlackParrot `57302ca5b`. The current synthesized hardware configuration files,
top-level RTL, BaseJump revision, and subsystem revision are unchanged from
that image. Across BlackParrot, the only source change from `57302ca5b` to
`3c8c16aca` is `bp_fe/src/v/bp_fe_pc_gen.sv` (31 insertions and 15 deletions).
This makes the corrected FPGA run a controlled hardware comparison of the
predictor-bank change; intervening top-level commits add benchmarks, evidence,
and simulator-side instrumentation rather than synthesized design changes.

## Physical verdict

The predictor provenance defect is real and the RTL correction passes its
targeted simulations, but it is **not** the root cause of the physical
placement-dependent failure:

| Exact program | Loop PCs | Corrected-image result |
|---|---|---:|
| formerly failing aligned ELF `90411570...` | `0x11e80` / `0x11ec0` | Hung in the first warmup; zero samples completed; the 600-second controller watchdog stopped the run. |
| previously passing placement ELF `e62165fa...` | `0x11f00` / `0x11f40` | PASS, 128/128 samples, clean request and core exit. |

The timed-out run retired 766,980,248 instructions at reported IPC 0.227. The
processor and DDR path therefore continued making progress while the two-context
handoff failed to complete; this is not a global core or memory-controller
deadlock.

At the passing placement, the corrected image's median is 611,878 cycles for
8,192 requests (74.692 cycles/request). The previous image's 512-sample median
was 612,178 cycles (74.729 cycles/request). The -300-cycle, -0.049% difference
is noise-level: the correction has no measurable steady-state cost in the
stable case.

A one-request diagnostic retained the exact failing loop addresses and
byte-identical loop bodies while reporting which terminal checks failed. Both
the corrected and previous bitstreams returned context zero with the peer
completion and terminal records still zero. This is a separate pre-existing
short-stream lifecycle edge case, so it does not implicate the predictor patch.

The follow-up FPGA experiment disabled conditional predicted-taken decisions
while retaining predictor reads/training, architectural branch resolution, and
context redirects. Both the failing and formerly stable placements then hung in
their first warmup with nearly identical retirement and MTIME signatures. A
later simulation reproduced a resident Sv39 relaunch failure with prediction
enabled and disabled: a commit-time state-reset fallback fetched the correct PC
without changing the frontend register-bank tag. BlackParrot `332ada47b` fixes
that independent path. The prediction-off board result is therefore confounded,
and a routed image containing the fallback fix is the next physical test.
Machine-readable results are in `fpga-analysis.json`; follow-up evidence is
under `logs/conditional-prediction-off-20261004/` and
`logs/translated-resident-relaunch-fix-20261004/`.
