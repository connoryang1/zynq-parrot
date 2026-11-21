This review closes the advisory whole-core correctness gate while preserving its rejected fixture. It verifies exact ELF payloads, startup bounds, archived model/run identities and closed-trace evidence without executing another target or changing RTL, validator code or host tests. The accepted result is synthetic I/D full-line restoration in simulation.

| Fixture | Checked execution | Strict retained-restoration gate |
|---|---|---|
|07, ELF426d0faf… |PASS |Rejected: target lines stayed ordinary-L1 way1; both completed hints took the resident-drop guard |
|First-touch08, ELF3fe09617… |PASS |PASS: one advisory publication, accepted retained hit and complete real eight-beat L1 refill in each lane |

Fixture07's ten accesses produced ways1,2,3,4,5,6,7,0,4,2 in both caches. All evictor functions and loads executed at the intended index; tree pseudo-LRU left way1 resident. Its failed gate, original ELF/source and replacement/localization evidence remain preserved. First-touch08 warms only lines1–9 and never deliberately demands target0 before advisory, avoiding assumptions about replacement victims. The fixtures have distinct manifests: `advisory-fixture/manifest.json` and `advisory-fixture-cold08/manifest.json`; their static build manifests are preserved unchanged.

The08 proof uses the unchanged scoped06 model (64 retained full64-byte lines per side). With control3, both demand-copy bits are zero. At I physical address0x80001000 and D address0x80012000, it verifies publication before accepted lookup/hit, exact512-bit responses, ordinary tag installation, all eight real SRAM write strobes/data/addresses/masks through normal L1 ports, and non-aborted completion. Both refills use way2. D's requested/critical word is3. Code0 retires all16 exact ELF instructions in order and returns its checked value; all eight data values pass guest checks.

The I lookup is accepted at6,026,075,000ps, before the BE demand marker retires at6,026,125,000ps; its accepted hit is later at6,026,675,000ps. This is permitted FE pre-execution, not a demand-marker timing failure. Marker retirement is not an exact FE request boundary. Neither line's acceptance relies on an aborted I acknowledgment.

The data object spans0x80012000–0x8001bfff. The linked CRT zeroes only0x8001cd30–0x8001d3e7: `verify.py` checks the exact clear-loop machine bytes and decodes both bounds from the linked gp/PC-relative instructions. All linked TLS initialization sizes are zero. Thus BSS/TLS initialization does not manufacture prior target-data demand. No fence or extra L1 invalidation was added to obtain coldness.

`verification.json` binds unchanged validator/test sources and the26-test host gate, the tested reader binary, both source snapshots/manifests, selected-event evidence, compressed and losslessly decompressed run/FST/ELF/NBF hashes, the consumed model binary and its exact source-list normalization. The actual process exits134 only after the checked guest marker, CORE PASS, host return0 and BSG PASS; the maintained checker accepts precisely the documented subsequent GPIO finalization exception.

Assertion acceptance is explicitly scoped to post-initialization BP/runtime and unguarded library assertions; guarded Basejump checks are excluded and time-zero parameter checks are covered separately. This does not close the earlier global-assert scheduling/pointer failure. One first-touch line per side does not establish useful capacity, application benefit, complete-execution speedup, FPGA fit/timing or calibrated memory latency. CSR/controller idle does not establish lower-L2/AXI/DRAM drain.

Reverify these closed artifacts with `python3 research/retained-control-abi-20261121/advisory-trace-validator/closed07-08-review/verify.py`. No target runs occur.
