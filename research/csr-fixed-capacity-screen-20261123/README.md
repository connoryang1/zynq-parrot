This review chooses the next capacity point without changing the fixed BP1e hardware implementation. It uses existing source and resource reports only; the current768 job is still unclassified here. Component RAM counts and planning arithmetic do not establish whole-device placement, timing, FPGA correctness or a global maximum.

Try1024 full64B lines per side (128KiB combined) if768 fits; try512 per side (64KiB combined) if768 fails. These are the next complete-way midpoints between the tested capacity points, with256sets, epoch8, ordinary32KiB I/32KiB D/16KiB L2,2resident/4logical,20MHz/8MHz, trace0/observe1/native0 and implementation options held fixed. Fit need not be monotonic. In particular1024 has four ways instead of768's three, so RAM growth does not imply a known LUT/slice increase.

The exact BP1e backend file SHA is `c04764548493f2a1109c36f25881c32444d0171b434e777c9e2b5fc2f631bcf2`; mapped8df reference SHA is `68d1dd0c7df7e56ffe76317f9bae5a3ca3e09d13cb44d1167c0f737acefcbea6`. Their synthesized source tokens are identical after removing comments and the single synthesis-disabled payload-lease assertion block. The original RAM-only storage slice is also literally present in both. This establishes the actual port/storage bridge: two owning clocks, separate tag29/payload64 arrays per lane, synchronous independent enables, one logical read/write port, registered READ_FIRST output. It does not assume that a CSR-only change automatically preserves inference, and it does not make the old RAM-only Default probe a production controller/whole-core result. `observations.json` binds exact source hashes, normalization, storage slice and reports.

No comparable synthesized512/1024/2048 production-wrapper reports were located in the reviewed existing artifact/report families. The located512/1024 old records are Verilator functional evidence and cannot supply RAM/LUT counts. Existing RAM-only measured pairs are1280=41tiles and1536=48; actual full-controller1792 is56tiles/1142LUT/2211FF under its recorded production wrapper. Existing canonical1793 and1824 already mapped60tiles. These results are retained, not rerun. Cell36/static/parity alternative-layout maps are excluded.

| Actual retained payload, combined | Whole RAM tiles | Backend evidence | Residual by subtraction |
|---|---:|---:|---:|
|32KiB:256/side|93.5|9, actual whole hierarchy|84.5|
|160KiB:1280/side|125.5|41, exact-array RAM-only probe|84.5|
|192KiB:1536/side|132.5|48, exact-array RAM-only probe|84.5|

The32KiB entry clock table independently deduplicates90RAMB36+7RAMB18, including8RAMB36+2RAMB18 under the retained backend; ROOT reports the same counts in routed07. The1280/1536 whole values are actual clean synthesis reports; subtracting their separate component counts is an empirical84.5 residual, not an independent whole-hierarchy proof of invariance. The old1792 whole result used earlier source/implementation and cannot be transferred as a matched newArea failure. Current matched1280/1536 synthesis used54394/54441LUT and26945/26943FF, then detailed placement failed133/252slices short. RAM below140 did not solve logic packing.

For equal capacitiesL and the source's independent arrays, a raw lower bound in36Kb-tile equivalents is `ceil(L*512/18432)+ceil(L*29/18432)` across both lanes. It assumes ideal bit use and half-tile granularity, so is optimistic. A conservative hand-mapping allowance is `4*ceil(L/128)+2*ceil(L/1024)`: two32-bit payload banks per lane per1024 words, plus one29-bit tag bank per lane per1024 lines. That is an explicit possible storage organization, not a guarantee of Vivado's chosen mapping or an observed resource count.

| Unmeasured capacity/side | Raw lower bound, backend | Conservative hand-mapping allowance | Conditional whole allowance with84.5 residual |
|---:|---:|---:|---:|
|512|16|18|100.5–102.5|
|768|24|26|108.5–110.5|
|1024|31|34|115.5–118.5|
|2048|61|68|145.5–152.5|

These columns are planning bounds for the stated storage construction, not confidence intervals or actual inferred whole-RAM bounds. Thus1024 or512 has plausible BRAM room, but neither has a LUT/slice or timing acceptance. At2048, payload alone needs at least57tile equivalents; adding the observed84.5 residual already exceeds140 at141.5, before the separate tags. The complete independent-array lower bound raises the conditional total to145.5. Even allowing the older1792 residual84.0 gives145.0. Therefore2048 is a cheap planning rejection unless new actual evidence shows the fixed nonbackend mapping falls substantially; this is not an unconditional global impossibility theorem.

Likewise1793/1824's existing60-tile source-grounded maps imply144.5 with the repeated residual. Do not repeat that probe or spend a new whole-device build above1792 without evidence that the fixed source can recover the RAM deficit and logic packing. Failures at1280/1536 and old1792 are recorded tested points, not proof that every larger or intermediate capacity fails. No exact global maximum follows.

The cheap next screen first reuses the active768 synthesis/implementation RAM reports and existing source bridge when ROOT publishes them. After ROOT selects1024 or512, only if the missing exact component mapping matters, reuse the existing production wrapper (Iinvalidate0, Dvariable, PA34,256sets,epoch8, both full ports,50ns, same synthesis options) for that one newly selected depth under fresh authority. Preserve actual primitives/port properties and compare equal wrapper source; do not repeat1280/1536/1792 controls or change policy/workloads. Clean native qualification and a fully routed fixed-flow implementation remain required before selecting any new physical capacity. No new tool, simulation, reader, benchmark or board operation ran for this review.
