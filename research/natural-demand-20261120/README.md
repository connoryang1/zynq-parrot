This report consolidates the first two completed physical natural-demand sessions and their four checked workloads. It preserves exact image identities and within-boot paired uncertainty, with later trigger-attribution and memory-ownership limitations stated explicitly. Later sessions are recorded separately; these initial observations do not accept a new optimization, estimate FPGA results from simulation, or include process-setup timing.

The same accepted PYNQ-Z2 package and ELF were used for all four runs. Each run measures 64 complete steady futex roundtrips after 32 warmups, with 4 paired repeats, alternating off/on then on/off by repeat. Each process owns a 32 KiB private corpus; every timed roundtrip includes the child request, return handoff and parent request, plus synchronization, kernel hint cost and any interference. The policy label is `futex-early`, but later exact disassembly and physical counter gates show that this old mode-14 kernel also replays at incoming-task selection. These are combined early-wake/selection-policy observations, not isolated early-hook or newer demand-retention CSR results. Profile is plain and terminal_handshake=1.

| Workload | Paired median saved cycles/roundtrip [95% CI] | Paired median saved percent [95% CI] |
| --- | ---: | ---: |
| scan | 2,995.51 [125.58, 6,612.27] | +1.730% [+0.071%, +3.642%] |
| lookup | 268.66 [-3,080.80, 2,818.42] | +0.222% [-2.603%, +2.345%] |
| parse | 11,262.02 [7,994.36, 16,222.44] | +1.347% [+0.956%, +1.906%] |
| chase | -858.03 [-4,479.88, 2,566.25] | -1.024% [-5.188%, +2.925%] |

Positive values mean fewer enabled cycles. These are medians of within-repeat differences and percentages, not differences of marginal medians. Scan and parse show positive intervals in these boots; lookup and chase do not, and chase has a negative point estimate. Each workload appears in one Linux boot with four paired blocks. Different workload boots are not independent same-workload replications; the intervals do not quantify between-boot uncertainty.

Work is checked against values derived independently from the immutable generator. Scan reads one byte per 64-byte line; lookup performs 64 changing open-addressed queries with deliberate misses; parse decodes variable-length generated text records and payloads; chase follows 64 dependent links per request through a rotating 512-node corpus. Both process checksums cover warmup and timed work and are verified after the timer. These broaden the synthetic demand patterns; they are not claims about general application or library performance.

The terminal protocol parks the child until the parent samples end, preventing child verification from delaying the final timed return. Allocation, fork, setup, warmup, checksum verification and teardown are outside this dataset's steady timer. Consequently these complete two-switch requests must remain distinct from the whole-cell setup/teardown metric; these logs contain no WHOLE rows. Prefix status includes the final out-of-timer release and at least the 388 known early-wake opportunities plus unlocalized selection activity, saturating accepted-trigger telemetry at 255; each run reports 320 admitted entries, 511 saturated resident drops, zero dropped triggers and clean reported-controller drain. Those counters establish activity, not first-use readiness, full memory-system drain or useful unique capacity. The exact one-byte early-only control and its separate counter gate are in `../mode14-early-only-20261120/`.

Both sessions record reservation `/home/coyang/fpga-artifacts/pynq-session.lock`, `all_three_acknowledged=true`, state complete and release timestamps. Session 1 contains scan/lookup (07:31–07:43 UTC); session2 contains parse/chase (07:58–08:11 UTC). Each raw log contains a fresh single-hart Linux boot and its own benchmark PASS plus CORE/BSG PASS; all four runner statuses are PASS.

A topology provenance conflict is explicit: the earlier requested 4-slot/4-context label is unverified. Archived routed `revisions.txt` names static `e_bp_unicore_zynqparrot_prefetch_cfg`, top `b4c82ade`, BlackParrot `684e5d8b`, and default thread/context flags. Those exact source objects resolve to 2 physical slots and 4 logical contexts: the top base configuration overrides `num_threads=2`, its prefetch configuration inherits that value, and the BP schema defaults logical contexts to 4. Archived route reports and HWH do not recover explicit elaborated dimensions; the original vds/dcp is absent locally. The report therefore records source-inferred 2/4 and leaves actual route elaboration counts unverified. Linux's one-hart boot count is separate from hardware context capacity. No simulator topology is substituted for a board proof.

A subsequent ownership audit found that this exact runner requests 46 MiB while these Linux boots initialize 64 MiB, with no corresponding upper-region reservation or remapping bound. The raw complete-run checks and paired measurements remain recorded, but the unowned address range is an additional limitation on their interpretation; no claim identifies it as the cause of a particular failure or timing effect. New performance acceptance uses a separately bound, matched 46 MiB image family and cannot pool these older boots. See `../guest-ram-ownership-20261120/`.

Exact shared identities:

- Package SHA256: `b139be87bdadf965f2d5e7eb7cd290bc56be76753a2377dc25f5c690a69d5ab1`.
- Extracted bit SHA256: `f0910fa4ee537963088cbeb6b21379ddb6b237af900a0aea7b12b87c0426fc3d`.
- Linux NBF SHA256: `ef50be197b458b512f82ed8a9deccc0bdfcfadba760ccd119d67e46837501cf4`.
- Measured ELF SHA256: `e943befa9eed8b9a4258c88c5c822745017c42ef1d5af9f3bc07c56a0eade86a`.
- v2 transfer SHA256: `40afe5254421b118c1e3e0996af99376b9548fa84176ecc6419f2e23ea325e5e`.
- Control program SHA256: `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30`.

Source checkpoint `9dbea5f7fc59c76fd18e0fc9502d3bb2abbd98a8` binds the measured plain benchmark/header, Makefile and analyzer. The parent confirmed current default guards reproduce the identical e943 ELF; this consolidation did not rebuild it. `results.json` stores SHA256/size/path for all four raw logs, statuses, analyses, both session manifests, transfer, NBF, package verification, routed identity evidence and exact Git source objects. Offline transfer decoding independently reproduces e943 without executing shell commands. No board command, partial session3 read, or new test/model run was used.
