This package now contains a root-built, validated trace-filtered 200-tick model and a separately prepared strict 32 KiB natural-data control. Root completed the host-only copied-object build and its own 1,944-cycle mode0 validation; there was no RTL elaboration or target recompilation. The preparing agent performed source review, host-policy tests and retained-trace analysis, without executing a model or board. The formerly active 32 KiB/40-tick case was read only after closure and its full audit passed.

The new driver and 105-leaf allowlist are derived from the previously validated host-only trace filter. The original 40-tick driver and current data-workload runner are unchanged. `source-review/` contains the root agent's exact generated-source/header/object inventory; it is referenced rather than duplicated.

| Pinned original200 input | SHA256 |
|---|---|
| Complete recorded session | `68edbecf3b012d73c9c926e7df2e690ed4ce887aa9307837859667091aff6b50` |
| Immutable original200 executable | `a654e3fdc1ecbed116f249350515f0967edbb68cf027ff1f1317c17f0e50785a` |
| Closed original build log | `06711afa3d0ef07210670367ae19ec2bb6bc80f4fb596dcdd3426c5e6dcec748` |
| Generated Syms C++ | `0b18a9494fc274cd95333648cba1480ee4beb9f8ac887ff755366512e9e4c687` |
| Original model archive (26,864,620 bytes) | `dd1448b39780f5648007f8f0d5d3ee30802ce3b1b6fa18148b7b4fa7e8495914` |
| 430-file generated source/object/header inventory | `d81d77b7614a56afa4f577bb1c759ba151de7f4960aac8d6bb18951c78f0aed4` |

The saved session/source is FFC `ffc9bd7641bc1d9b3df6cf530f3a432db3ebae57`, capture off, full-burst transport, two resident slots/four logical contexts, 64-bit AXI beats, queue depth four and configured first response 200 model ticks. The exact Syms compilation argv includes `-DVM_TRACE=1`, `-DVM_TRACE_FST=1` and `-DBP_AXI_MEM_READ_LATENCY=200`. The original slow-PCH creation and Syms compiler prefixes match exactly; the driver preserves every flag and maps only the `.h.slow` PCH alias to its actual `.h` text source after checking that proof. No `.gch` is copied or rebuilt.

The generated Syms source is byte-identical to the reviewed 40-tick Syms source, so the same insertion point is valid: add 105 `dumpvars(1, exact_leaf_name)` calls between trace registration and `open()`. The complete retained old200 header independently verifies every selected canonical path, including packed array indexes and all 48 per-way tag fields. The allowlist's origin is now the **own old200 audit**, not an old40 count/timestamp oracle. All cached accesses and actual tag/refill ports remain observed; no target-address filtering or SRAM data-array dumps are introduced.

The read-only old200 baseline is complete and valid. `old200-audit/` binds the original 29,015,502-byte FST, unchanged mode0 ELF/NBF/log, frozen auditor/helper and clean converter EOF/zero exit/empty stderr. It validates 512 initialized tag slots, 5,133 synchronous tag-read rows, 4,742 cached references (4,639 hits/103 misses), 103 actual tag publications/complete refills and 824 beats. These counts were measured on old200; they happen to match old40. **The full event stream differs**: old200 SHA256 is `536f21200d76458a73f6c4f88e3cca7d710d1ba8a95d6fbbb0b00d4be52bc0f9`, versus old40's `de84af...`. This driver never substitutes old40 events, counts or timestamps.

The `build` stage copies the frozen original200 object tree to a new RAM directory, verifies every non-PCH-blob file against the reviewed inventory, and first directly relinks the untouched archive plus seven frozen host/runtime objects. That executable must reproduce the original `a654e3fd...` byte for byte. Only then does it compile the copied Syms translation unit, replace that one archive member and directly relink. All evaluation files and other objects/archive members must remain byte-identical, as must the original directory and durable original model. There is no make target, RTL elaboration, host-runtime dependency rebuild, synthesis or board operation.

The separate `validate-mode0` stage uses the original old200 mode0 ELF/NBF verbatim, native 240 seconds and a hard 150 MiB trace limit. It requires maintained whole guest/host acceptance, mode0, checked output and **1,944 cycles**. The new scoped trace must contain exactly the 105 variables and pass the frozen full-access auditor. Its statistics and complete ordered accepted reference/fill/eviction stream must match **own old200**. The hash-bound old200 baseline is reused rather than decompressing the same large original trace again. Count equality alone is insufficient; a host test explicitly rejects the old40 event stream even when supplied with equal counts. The gate stops before any natural-data workload.

Thirteen read-only host tests pass, covering source/configuration pins, latency/TRACE flags, PCH mapping, original200 counter/checksum, rejection of the old40 counter/event stream, all105 watch paths, incomplete audits, changed statistics and the object inventory. Exact commands/flags and test/source hashes are recorded in `preparation.json`.

The following model build/validation commands were executed by root successfully, **not by the preparing agent**. They are retained as reproduction commands (use new output directories to reproduce evidence):

```sh
python3 -B research/resume-data-reuse-latency200-20261120/build_scoped_model.py build --original /dev/shm/zp-linux-resume-capacity-20261120/burst-off200-obj --output /dev/shm/zp-linux-resume-capacity-20261120/burst-off200-scoped
python3 -B research/resume-data-reuse-latency200-20261120/build_scoped_model.py validate-mode0 --build /dev/shm/zp-linux-resume-capacity-20261120/burst-off200-scoped/evidence/build.json --output research/resume-data-reuse-latency200-20261120/scoped-mode0-validation
```

Root retained the successful copied build and model durably under `scoped-mode0-validation/model/`. The filtered executable SHA256 is `e52fa2473b3e35f0c14ae13973ec8ebdd7f0cbf9414ac49dae5e379b42230c3f`; complete validation SHA256 is `ba62705210c6970e2ba6f56836e720239274731e39bf716cc8c638ca02a3d7be`, and build-manifest SHA256 is `c247b7c9579fad02bbef5ec75d85c6db89d1c718366b33d457fc73c28652f85b`. It reproduces the own-old200 event stream byte for byte with exactly105 variables. The finalized filtered FST is1,105,582 bytes versus29,015,502 original. These are completed model/control results, superseding the earlier preparation-only status in `preparation.json`.

`run_natural32.py` is a NEW separate runner; the existing data runner and both filter drivers remain unchanged. It pins the closed32KiB/40 session (`ed751258...`) and full audit (`41949658...`), including complete64request/load/state/refill verification, as well as the exact200 build/gate/model. It verifies/copies the same compact ELF `f35e5da8dcb527cfa04c16edab0616f1f80a7715c9b05278500799c9b66393dd` and already patched32KiB NBF `18dbba12d432e6cfde94e7a16887d52f4e6edf0114b21a4fd227c0fbe4bc103d` verbatim. There is no compiler, NBF repatch, footprint/heap/layout change, address table or policy change. The only model-service change is40to200 first-response ticks, holding64-bit beat width, queue depth4 and modeled platform fixed.

The new runner requires an explicit native2400-second budget, versus1800 for the source40 case, and records a2580-second host guard and unchanged150MiB FST limit. The native wall limit is a censoring guard, never the comparison metric. Whole maintained guest/host acceptance, the exact frozen compact parser, unchanged corpus/stack/checksum metadata, and a full frozen tag/cache/reference audit with all64 independent per-request load counts are required before its state becomes `pass-full-audit`. The auditor runs only after the trace writer stops and accepted whole execution. A failed/partial execution remains failed; nothing automatically retries.

Eleven admission/preparation tests pass, including rejected wrong footprints/ELFs/models, incomplete baseline/gate, changed sources/NBF, extra evaluation-object edits and substituted old40 events. A mocked complete preparation proves exact program/NBF copying and the2400/2580 budget without invoking a process. A guard test verifies child termination. `natural32-admission.json` binds this implementation and the closed inputs. No natural200 target was executed by the preparing agent.

Ready command for root execution (new output directory):

```sh
python3 -B research/resume-data-reuse-latency200-20261120/run_natural32.py --output research/resume-data-reuse-latency200-20261120/compact-thirtytwo-kib --native-runtime-seconds 2400
```

The resulting latency comparison is valid only within fixed32KiB-per-actor work, exact ELF/NBF, contexts/heap and service bandwidth. It must not attribute the separate1KiB-versus32KiB difference to one cause or turn conditional victim coverage into execution cycles.

This is a **one-L2-bank synthetic model**, while the physical reference uses two L2 banks. The saved command selects the base configuration without `BP_ZYNQ_PREFETCH_TWO_BANKS`; that source branch specifies one bank, and generated Syms scopes contain only `.l2s.bank[0]`. These service ticks are controlled simulator parameters, not calibrated physical DRAM latency. The bank/platform distinction, full-burst beat bandwidth and shared request contention must remain explicit. Neither the mode0 result nor future fixed-footprint latency sensitivity is an FPGA/application speedup projection.
