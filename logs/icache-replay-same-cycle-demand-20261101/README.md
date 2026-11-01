This directory preserves the directed evidence for a same-cycle collision between an ordinary cache miss and a detached instruction replay of the same physical line. It records the failing pre-fix case and the passing side-buffer, legacy-installer, and unrelated burst controls; it is standalone UCE simulation evidence, not a core, FPGA, or Linux performance result.

# Same-cycle demand/replay collision

## Question

The detached replay ingress and architectural cache-request FIFO have independent handshakes. The prior resident-demand suppression at BlackParrot `158adde752c4a03c0d9136acc04235f850bc8f2d` compared only against `cache_req_r`, so an ordinary miss and identical replay accepted on one edge could both survive and later issue redundant memory reads.

The added driver case holds the memory forward link, presents both requests on one edge, supplies the ordinary miss metadata, and requires the replay table to remain empty. It then requires exactly one non-prefetch memory request for the target line.

## Red result

With the test-only change and the unmodified `158adde75` RTL, the side-buffer executable accepted both ingress handshakes and failed with:

```text
[UCE-ICACHE-REPLAY] FAIL: same-cycle replay survived its accepted same-line demand
```

The retained run log hashes to `7d01b0b898b99afafb454055d78c6d437eb98d6b1bfc50339a406d640139751f`; its FST hashes to `0c52bf138f8a1e61547c09707322becf74d98f90cd7bf6c36f88a7938b8086bc`.

## Fix and passing controls

The candidate extends `detached_prefetch_demand_match` to cover an ordinary miss that is accepted on the current edge as well as a same-line miss already resident in `cache_req_r`. It acknowledges and drops only the identical detached replay; unrelated lines and unaccepted ordinary requests retain their prior behavior.

Commands, run-log SHA-256, and results:

```text
python3 testing/rtl/run_uce_icache_replay.py --side-buffer \
  --out /dev/shm/zp-joint-bestcase-uce-samecycle-green-side \
  --verilator /home/coyang/zynq-parrot/install/bin/verilator
3aaa95f2b49ad771a080d1e987aa316bc292b157ca2444e5a70fee376436b495
PASS: same-cycle collision, detached retirement, and overtaken same-line replay drop

python3 testing/rtl/run_uce_icache_replay.py \
  --out /dev/shm/zp-joint-bestcase-uce-samecycle-green-legacy \
  --verilator /home/coyang/zynq-parrot/install/bin/verilator
40681c020650c03c10da191aebdf2259cd31459d6f12610ada104e3732a68034
PASS: same-cycle collision, full-line install, resident-line drop,
      fence drain-without-publish, demand-priority abort,
      overtaken same-line replay drop

python3 testing/rtl/run_uce_icache_replay_burst.py \
  --out /dev/shm/zp-joint-bestcase-uce-samecycle-burst4-l80 \
  --prefetch-slots 4 --response-latency 80 \
  --verilator /home/coyang/zynq-parrot/install/bin/verilator
74a7bb1487f10e55aee08fafc3ffad0b889acebcfc85f10b77780abf61fc0ce6
PASS: slots=4 requests=16 latency=80 cycles=393 max_valid=4
```

The final focused-test driver hashes to `3e6568eb3058240a0f9512a6575a24bdb3c1a5e0366a0dae92f9ebc5bc3eb9b3`. The candidate `bp_uce.sv` hashes to `d0c5b357c1a0aaefadc28fa03e746a43947725e84039e8c9b262dfb12fae073d`. Each passing directory also contains the runner-generated dependency manifest and exact build command.

## Scope

These tests prove the collision existed and that the local suppression removes it without changing the established four-slot burst result. The candidate also passed a clean traced full-core gate:

```text
make -C testing run-mt_icache_replay_test \
  NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12
[BSG-PASS] shared-prefix and physical I-cache replay
CORE PASS
BSG PASS
VALID RUN: guest and host PASS
```

The exact full-core build log, FST, run log, NBF, and test ELF hash to `473a2765...ad2`, `8bbce5a5...e1`, `8be593b2...e1`, `a0447edd...945`, and `ee966c43...08e`. The run terminates with the known shutdown-only `bsg_nonsynth_dpi_gpio` finalizer assertion after both guest and host PASS; the maintained checker classifies it as valid.

Streaming the exact FST through `fst2vcd` counts zero rising assertions of `icache_uce.detached_prefetch_accepted_demand_match`, one resident-demand match at time 2,167,275,000, and zero matches of either kind in the D-cache UCE. `full-core/predicate-audit.json` retains those counts and the source FST hash. Therefore the full-core run is an integration regression gate; only the directed UCE red/green case causally exercises the new same-edge branch.

A new routed implementation is still required before accepting the candidate for FPGA/Linux use. Prefetch5 routes `20261101T125426Z-0fb3da28` and `20261101T132904Z-e4861a8f` use ten contexts/five slots, while the accepted 2.68% futex-v1 control bitstream used four contexts/four slots; those jobs can provide endpoint-stress and comparator data but cannot validate the physical performance rerun. The exact matched candidate route is synthesis-farm job `20261101T134139Z-24d10370`, pinned to top `24d103705dd3fd9af28ef5c0fedc0c2f1cc1f7c0`, BlackParrot `174f2787a05ca48a6e4362fc59dc462d3d95572c`, and `e_bp_unicore_zynqparrot_prefetch_cfg`; it must finish with a verified timing-clean package before board use.

The final prefetch5 endpoint-stress route is now terminal `FAIL`, not a pending performance gate. Synthesis uses 55,700/53,200 LUTs (104.70%), 30,152 registers, 94 BRAM tiles, and 11 DSPs; detail placement reports 11,535 required slices with only 10,934 available. The failure is scoped to the ten-context/five-slot configuration and does not classify the matched four-context route. Retained artifacts and SHA-256 values are:

```text
14e10e5c818d16949bb0bbdad81a8f5d12aa164773dc75f03783c6b6891def05  prefetch5-route-failure-artifacts.tar.xz
d79677f104d65fc558a6ee019f29e886478072abf044055e8c77c24d8bccc427  prefetch5-route-console.log
ee5112ff3b3fa0a7b54b036a1a668c9f887184367eda7220c0c45c908b6f95c5  prefetch5-route-revisions.txt
1238dd4051605ecb971bc003326e7b95c09ce45d874692c92d7962efe614ede6  prefetch5-route-utilization-synth.rpt
```

## Predeclared FPGA/Linux gate

If the exact candidate route passes, rerun the accepted futex-v1 best-case comparison without changing the table or benchmark. Recover the board before every arm, wait for complete PYNQ readiness, stage and hash-check the new package plus the exact NBF, reload and verify the overlay, and run four fresh boots in these two opposite orders:

1. wake-trigger, then disabled;
2. disabled, then wake-trigger.

Each arm uses 201 `to-peer` samples with summary-only capture, permitted recorder overflow, and final addresses. The fixed identities are:

```text
NBF SHA-256:             93b2e29de83be627631a6cb6e78b2a5529f9a42c89cb365894cfe7138a028629
benchmark ELF SHA-256:   91f0db111470e9f3fd1a53bfd9b8d7b4404ffe8e20a792e4caa99171bbc1c0cf
transfer SHA-256:        b5103c89b270f5cdcee8156de0a0a6d8b98ca32ecbba7de77e5cc11a6f0f5518
control-program SHA-256: 2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30
```

The exact ELF and transfer are under `../mode6-persistent-pair-protocol-20261101/recovered-board-artifacts/`. The exact NBF is durably archived as `/home/coyang/fpga-artifacts/context-resume/linux-mode6-wakeup-futex-prefix16.nbf.xz`; streamed decompression reproduces the NBF hash above. Every arm must pass the matched route's exact bitstream SHA through `run_cache_miss_trace_capture.py --bitstream-sha256`; the board helper verifies the actual Makefile overlay load target before execution, and the status plus transcript retain the hash. Analyze only after all four arms pass their bitstream/NBF/ELF/transfer/control identities, numbered-sample, runtime-mode, final-capture, runner-exit, CORE, and BSG gates with `linux-tests/analyze_persistent_preview_ab.py --bitstream-sha256` and `../mode6-persistent-pair-protocol-20261101/futex-prefix16-candidate.json`. This measures the complete corrected RTL checkpoint; no late-drop mechanism attribution is allowed without direct event telemetry.
