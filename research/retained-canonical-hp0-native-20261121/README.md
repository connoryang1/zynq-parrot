This preserves the completed canonical b912 native HP0 audit and independent full-payload association as compact simulation evidence. It separates memory-interface timing, retained publication and cache ACK from physical DDR and CPU readiness. The curation branch is historical; the tested source is explicitly TOPeb7d/BP8df, not the branch's RTL.

ROOT execution16534 exits0 in55.68hostseconds, with no remaining owned helper group and no model/target/board execution. Its exact admission, guard, transcript, native99 signal schema, reader/API build receipt, complete selected stream, transaction records, source snapshots and strict proof are retained. manifest.json maps every byte-exact snapshot to its external original; raw20.4MB FST and model remain external and are not copied here.

Actual platform: static two-bank16KiB L2, ordinary32KiB L1I/L1D,1792 full64B retained lines per side,256retainedsets,epoch8,2resident/4logical,20MHz core/AXI, zero added response age. Clock observations are50000FSTticks at1ps/tick. The measured model is b912913adc5fa98a0675bd323e7b37da7cbaecdabbb787ca3f466edcc4851de9; the backend source is68d1dd0c7df7e56ffe76317f9bae5a3ca3e09d13cb44d1167c0f737acefcbea6.

All648reads carry eight64-bit words. AR→first offered/acceptedR is1cycle and full line8cycles, with1cycle between beats. All487writes complete; native before/after full opaque records agree exactly. Observed read/write concurrency is1each, with no bus stalls. Those are fixture observations, not an architecture concurrency limit or physical-memory calibration.

|Target lane|Advisory admission→AR|→firstR|→fullR|→publication|FullR→publication|
|---|---:|---:|---:|---:|---:|
|I detached0x80001000|41|42|49|109|60|
|D preview0x80012000|12.5|13.5|20.5|80|59.5|

Each target has exactly one matching read between admission and publication. All512bits agree with strict publication,64file-backed bytes in the bound cold08 ELF and all eight actual winning L1 SRAM writes. RID0 alone supplies no I/D/demand/prefetch classification. The immediately preceding read finishes13cycles before each targetAR; no write overlaps either measured pair. This observed serialization does not identify an exclusive queue/arbitration bottleneck or establish a latency-sensitivity slope.

The later retained target demands take14cycles to first offered/accepted cache ACK and21cycles to the full eight-ACK completion. Backend lookup→hit is12cycles for these first-way targets. D's actual critical-offset3 word is written at17cycles. The strict proof also confirms nonaborted full SRAM writes and16retired target I instructions. ACK and critical-word SRAM timing do not establish CPUload/fetch readiness.

independent-review.json SHA d098e29cf6fd0b561a4720642490378199441220eaae3585d51e2b01506ac3b7 measures these values from NEWb912 records. Equal numeric109/80 values in dense876 are not transferred evidence; olderSP1280 publication101/76 and historical41-cycle physical load-use are different sources/endpoints. Native allslot correctness, application WHOLE effects, physical timing and routed fit remain separate gates. N40/N200 preparation stays deferred under the coordinator's synthesis-benchmark hold.

Verification of the compact packet, without reader/build/target execution:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 research/retained-canonical-hp0-native-20261121/verify_packet.py
```

The original independent analysis method is retained byte-for-byte as review.py. It binds an external full ELF for its64file-backed-byte check; that ELF is not copied into this compact packet. No main worktree/index, RTL, N40 source, RAM stage or source cache was changed by this curation.
