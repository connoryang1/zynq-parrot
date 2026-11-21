This preparation integrates the functionally proved canonical epoch storage into one production source file and prepares a bounded component-equivalence gate. It does not establish whole-CPU area, timing, fit or application benefit.

The dedicated BP worktree is `/home/coyang/bp-retained-canonical-epochs-20261121`, branch `experiment/retained-canonical-epochs-20261121`, based on exact225489a435cb0b2a2c0b237077f94418dc89549b. Only `bp_common/src/v/bp_retained_line_store.sv` differs. The combined source is exact sealed b69 backend plus a767 auxiliary module, with `line_epoch/inv_epoch` and `last_slot` declarations moved before first use. File-naming lint comments surround the appended module. `normalization.json`, `production.diff` and the read-only preflight prove this construction. The bound earlier vendor log preserves the original8-6901 declaration-warning provenance.

Nine host preparation tests and the real read-only source preflight pass. No component execution has occurred. The production source must not be committed as verified until the admitted root-host gate closes.

Root invocation, only after review:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 /home/coyang/fpga-artifacts/context-resume/retained-epoch-production-20261121/helper/run_host.py --execute
```

The driver requires the exact root-host sentinel device25/inode299801 before creating a fresh `/dev/shm/zp-retained-canonical-epochs-production-20261121-01`. It never accesses the private agent RAM namespace, board, network, vendor tools, or a full-core model. The fixed allocation is32MiB RAM plus24MiB maximum durable archive, with1GiB RAM and3GiB HOME reserve plus remaining allocation. A single component build job,300s/build,120s/run,12MiB child-file limit, zero core dumps and owned-process-group cleanup apply. Any error stops the one-shot attempt; sources, logs, executables and FSTs are preserved. There is no retry, cleanup or budget extension.

The exact actual combined production file is compiled once per profile against the BP225 reference (module rename only), using the corrected all-cell OR miter. The six normal cases are1792/1792/sets256/epoch8,93/131/sets256/epoch2, and0/3/sets1/epoch2, each with inverted and different-period independent clocks. They retain full512-bit payload, nonzero-initialized metadata/data, reset/held clear, sweep, wrap, backpressure, unrelated invalidation/publication and80,000 randomized ticks. The seventh case changes only a staged copy, suppressing canonical set0 initialization. It must reject at the D all-cell comparison with protocol flags still equal. No separate helper module is passed to Verilator, avoiding duplicate definitions.

`admission.json` binds74 exact input records, including source and prior proof, corrected wrapper/driver, installed tool binaries and Verilator runtime source. `preparation.json` records the actual host-only checks. A first read-only preparation check rejected a diff-format mismatch; its correction changed only the checker and did not alter production RTL. The old failed/superseded all-cell claim remains in its original preserved prototype directory.
