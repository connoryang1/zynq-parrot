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

A new routed implementation is still required before accepting the candidate for FPGA/Linux use. The already-running route `20261101T125426Z-0fb3da28` predates this candidate and therefore cannot validate it.
