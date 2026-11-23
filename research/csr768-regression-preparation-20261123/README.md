This packet reuses the maintained four-test architectural batch on the new qualified768 scoped model. It preserves all guest source/tool/header/CRT recipes and tests, changing only the observation-family path and768 qualification label. It is source only and cannot run before the new complete768 fullcore and five-domain scoped proofs.

The fixed tests remain context CSR rebind, nonresident Sv39 data handoff, resident reseed IRQ, and protected RPC hardware, with2 physical/4 logical contexts. The source files and `software-recipe.json`/`software-sources.json` are byte-identical to the maintained1280 family; historical software snapshots remain explicit provenance. Build and run flags, target180s/host360s per test,16MiB per trace,2400s owned batch, source/loader/CORE checks and accepted precise post-completion teardown policy are unchanged. Outputs stay under the same768 pool's `scoped-csr01/architectural-regressions01` and count against its original1GiB/32MiB envelope.

After ROOT binds the new source-plan and scoped admission:

```bash
S=/home/coyang/zynq-parrot-retained-metadata/research/csr768-regression-preparation-20261123
python3 -B "$S/launch.py" --execute --source-sha ACTUAL_NEW_STD_SOURCE_SHA --clone-admission-sha ACTUAL_768_CLONE_ADMISSION_SHA
```

The terminal state remains `PASS four unchanged architectural tests on new CSR-unmasked qualified model; no performance claim`. This generic label alone is insufficient: the supervisory result must bind the exact new768 source-plan, clone admission and actual scoped model from the new flow. Current model/full-session/STD result hashes are NULL. No import, compiler/model/reader/vendor/board runtime or output allocation was performed here; this packet supplies no768 all-slot or performance qualification.
