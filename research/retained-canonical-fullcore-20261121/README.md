This fresh gate qualifies only full-core functional correctness of the canonical D-epoch source. It does not establish FPGA fit, mapped-netlist equivalence, application improvement or a whole-CPU area saving.

Source is root-created sparse TOP eb7d390134a0025331a2366a979a774263b146d5, exact dense482 baseline with only BP gitlink8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c. The source root is /dev/shm/zp-linux-canonical-fulltop-20261121-01; no helper creates or mutates it. Source configuration remains staticprefetch16k,1792 full64B retained lines per side,sets256,epoch8,observe1,native0,20MHz,2resident/4logical, unchanged ordinary caches. Existing known-good1792 integrity6dc1/f856 and cold083fe/627 software is reused byte-for-byte from dense program02; there is no software build or NBF regeneration.

run_full.py is adapted directly from the maintained dense gate. Complete guest/CORE/host checkers, scoped assertion handling, precise postPASS-only teardown allowance, strict512b/eight real L1 writes/I retirement, independent counters,16 actual parameters, generated L2 geometry, consumed-source metadata/stamp and before/after checks remain intact. Changes are source/helper/artifact paths, BP/base pins, only-gitlink source validation, explicit prepared source identity, and resource guards. Historical immutable helper/program inputs remain in the HOME dense baseline. geometry.py is unchanged. close_full.py retains compact proofs plus exact new modelgzip, all consumed sources, both full rawFSTs and software snapshots on HOME, validating lossless archive contents.

The combined sparse source plus build/runtime RAM allocation is768MiB with1GiB free plus remaining allocation; HOME total includes every file in this helper directory and is128MiB with3GiB free plus remaining allocation. One clean3-job build,3600s build/600s integrity/180s cold08 native budgets,150MiB per runtime file, existing outer deadlines and owned-group cleanup remain fixed. No retry or extension. Original models, sources, traces and published proofs remain unchanged.

Root prepare command:

PYTHONDONTWRITEBYTECODE=1 python3 /home/coyang/fpga-artifacts/context-resume/retained-canonical-fullcore-20261121/run_full.py --out /dev/shm/zp-linux-canonical-fullcore-20261121-01/prepared01 --prepare-only

After explicit root review/admission of prepared01/session.json:

PYTHONDONTWRITEBYTECODE=1 python3 /home/coyang/fpga-artifacts/context-resume/retained-canonical-fullcore-20261121/run_full.py --out /dev/shm/zp-linux-canonical-fullcore-20261121-01/full01 --execute --prepared /dev/shm/zp-linux-canonical-fullcore-20261121-01/prepared01/session.json

After PASS, root closure command:

PYTHONDONTWRITEBYTECODE=1 python3 /home/coyang/fpga-artifacts/context-resume/retained-canonical-fullcore-20261121/close_full.py --external /dev/shm/zp-linux-canonical-fullcore-20261121-01/full01 --out /home/coyang/fpga-artifacts/context-resume/retained-canonical-fullcore-20261121/closed-full01

These commands are prepared for the actual root host namespace. The agent has not run a target or created a RAM source/build tree.
