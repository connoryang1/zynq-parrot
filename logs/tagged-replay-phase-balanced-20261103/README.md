This directory preserves the corrected FPGA/Linux data-replay footprint and lead-time sweep. It replaces a fixed-polarity A/B interpretation that aliased replay enablement with a repeatable four-trial scheduler phase, while retaining exact executable, transfer, status, analysis, and compressed console evidence.

# Phase-balanced tagged replay sweep

## Identity and method

All accepted runs used routed bitstream SHA-256
`168909eecd407d296202d16961f08f2ce96652f05d3a82321f7a5fbfcedb8bd8`,
shell NBF SHA-256
`08628c15185f4e99df9d8b19b0af6f24990d89e06fd4f1e9f50e2e2853056892`,
and phase-balanced benchmark ELF SHA-256
`3ea9aa25b5cd3cee000f68e4ba6077d66ef3eae94ea0942a8f9afb343ead8a91`.
Each run contains 512 accepted trials, 256 per arm, with alternating block
polarity: `[off,on,on,off]`, then `[on,off,off,on]`. Every enabled command
completed its configured entry count with one accepted trigger and zero
filters or drops.

The benchmark accepts one through eight lines per each of four pinned page
bases. This gives 4, 8, 16, or 32 total dependent first-use lines without
changing the board image, scheduling policy, cache pressure, or pin lifetime.

## Accepted results

Saved-cycle convention is positive for improvement and negative for harm.

| Lines | Lead | Local load saved, cycles | Wake-to-entry saved, cycles | Wake-to-load saved, cycles |
|---:|---:|---:|---:|---:|
| 32 | 0 | `+223.5 [211.75,233]` | `-5036 [-6124.5,-2699.25]` | `-5561.75 [-7612.25,-2998.75]` |
| 16 | 0 | `+152 [145,174.25]` | `-3644.5 [-7189.25,-752.5]` | `-3184.75 [-6793.5,-414.25]` |
| 8 | 0 | `+153.5 [147.5,166]` | `-2291.75 [-6127.25,552]` | `-1673.5 [-5802.5,1187.5]` |
| 4 | 0 | `+149.25 [144.5,152.5]` | `-4300.5 [-6858.75,-1960.5]` | `-4256.5 [-7399.25,-2131.75]` |
| 32 | 10000 | `+201.75 [190,220.75]` | `-2529.25 [-7191.5,1156.25]` | `-4068.5 [-9265.75,-808.5]` |
| 32 | 50000 | `+182.25 [148.5,206]` | `-5779 [-12115.5,1616]` | `-24559.5 [-30361.75,-16551]` |

The footprint sweep shows that local warming is real but does not repay
critical-path interference. Eight lines are end-to-end unresolved and retain
roughly the same local benefit as sixteen, but the four-line nonmonotonic loss
means no software-only line-count optimum is established. A 10,000-cycle
head start reduces the entry point estimate without neutralizing first use;
50,000 cycles perturbs scheduler timing and is rejected as an optimization.

## Architectural interpretation and next gate

The routed configuration has four D-cache prefetch slots
(`dcache_prefetch_els = 4`). The replay controller holds later entries until a
slot frees, so a 32-line tag streams through a four-entry window and can remain
active across the handoff. Status entry counters report admission into that
window, not a separate timestamp for memory completion and useful cache
publication.

An opt-in diagnostic first sampled status in the waking parent. Zero lead saw
203/256 enabled trials with all 32 entries admitted and 53 with no visible
trigger; 10,000 cycles of parent lead saw 186 complete and 70 not visible. The
all-or-nothing result is a parent scheduling race, not a monotonic completion
curve: the child can preempt the parent, finish, and clear counters for its next
trial before the parent completes its status syscall.

The corrected target-entry probe samples status immediately after the resumed
child records entry and before its dependent loads. All 256 enabled trials
report one trigger, 32/32 admissions, controller idle, and no queued or held
entry. Wake-to-entry is already `4202.75 [2938,6745.5]` cycles worse at that
boundary. The entry status syscall itself costs 1,295.5 enabled versus 1,093.5
disabled median cycles; this roughly 202-cycle difference cancels the usual
local-load saving and confirms that downstream replay effects remain after the
controller reports idle. The status ABI therefore needs true UCE/AXI
outstanding or completion state before increasing replay width.

The first target-entry-probe launch timed out during early Linux driver
initialization before reaching a shell or transferring the guest ELF. It is
retained as rejected infrastructure evidence; a full power cycle, readiness
wait, and exact-overlay reload preceded the accepted retry.

The exact physical AXI path already prioritizes an ordinary cache AR over a new
prefetch AR, but accepted prefetch bursts remain on the shared HP/DDR path and
all read transactions currently drive `ARQOS=0`. Zynq-7000 documents
per-transaction AXI QoS as a low-latency arbitration input, making high-demand /
low-prefetch QoS a small candidate to test separately from a one-outstanding
prefetch cap. Neither is yet a validated optimization.

## Pacing proxy and safety rejection

An uninstrumented same-binary control using ELF SHA-256
`3521811b...1ec` passes all 512 trials at gap zero. It saves
`183.75 [158.25,211]` local load cycles but loses
`5408 [506.5,7141.75]` wake-to-entry cycles and
`5278.75 [761.5,7235.75]` wake-to-load cycles. This independently reproduces
the accepted mechanism/critical-path tradeoff with the target-entry-probe
binary while keeping probe syscalls disabled.

A 64-cycle controller gap was then tested as an existing-image proxy for
limiting downstream occupancy. It is rejected for correctness before any
performance interpretation. The first exact run reached child PASS, then
Linux reported `refcount_t` saturation and underflow in PID 1's `wait4` path
and the benchmark returned 145. After full board recovery, the exact retry
completed all 512 benchmark rows and printed child/parent PASS, but `poweroff`
entered an OpenSBI misaligned-store trap and never reached CORE/BSG PASS. A
diagnostic-only parse of those pre-failure rows still showed a harmful
`-4144`-cycle wake-to-entry and `-7180.75`-cycle wake-to-load point, so even
the incomplete run does not suggest that gap 64 is a useful operating point.
Both raw failures and runner FAIL statuses are retained; neither is accepted
as a benchmark result.

The same binary's passing gap-zero control, together with two independently
recovered gap-64 architectural failures, distinguishes the pacing setting
from retry count and binary layout. Do not rerun gap 64 or use controller gap
as the one-outstanding implementation. A real occupancy cap must act at the
UCE/AXI allocation boundary and pass correctness gates before performance.

The subsequent status audit found a confirmed lifecycle safety bug. Kernel
patch `0017` described its page-release loop as a tagged-replay drain, but it
tested only status bits 3:0 (controller busy/queue/held). The old CSR had no
downstream state, and CSR `0x9c0` tracks only narrow speculative previews, not
tagged full-line prefetch slots. Thus a controller-idle observation could be
followed by unpinning while D-UCE/AXI work remained live. This is a concrete
mechanism capable of explaining the gap-64 post-benchmark corruption, but the
specific failure attribution remains provisional until the corrected image
passes the exact reproduction.

The corrected kernel cleanup and configuration paths now require both bits
3:0 and allocated-slot bits 62:60 to be zero. The benchmark uses the same mask
between trials and before releasing pins. This wait occurs after the measured
first-use endpoint, so it prevents cross-trial/lifetime contamination without
serializing the wake-to-load interval under study.

The exact retained Linux output tree rebuilds and links the correction with
Buildroot GCC 13.2. `vmlinux` and raw payload SHA-256 values are
`94596d75...c09` and `f05b1119...971`. Fail-closed payload replacement creates
interactive-shell NBF `4e91d7b6...8d9`; reversing that replacement reproduces
the prior shell NBF `08628c15...892` byte for byte. The rebuilt dynamic
benchmark and 50-command transfer hash to `69c76086...f1a` and
`62cbc361...f5e`, and local transfer execution reconstructs the exact ELF.
All 153 discovered Linux tests pass. Patch `0017` also passes explicit reverse
dry-run against the built tree and forward dry-run against an isolated
pre-patch reconstruction; this caught and corrected one intermediate malformed
hunk count before checkpointing.

## Downstream occupancy instrumentation

The diagnostic candidate exports the instantaneous number of allocated UCE
prefetch slots and whether any memory reply is complete but not yet retired.
Replay status bits 62:60 carry the allocated-slot count, saturated at seven,
and bit 63 reports any completed reply awaiting retirement. These were the four
reserved bits, so existing admission,
filter, trigger, queue, and active-slot fields retain their encoding. The
analyzer now reports both counts at the parent pre-block probe and at target
entry, separately for enabled and disabled arms.

The first telemetry checkpoint `291ff1a97` passed the controller, UCE, and
clean trace-enabled full-core gates, but a subsequent exact-configuration audit
found that its two-bit count could encode all four occupied FPGA slots as zero.
Synthesis job `20261104T055758Z-cb7e1392` was canceled before board use. The
corrected encoding is therefore the only board candidate: the UCE source count
now represents the inclusive range from zero through `prefetch_els_p`, status
bits 62:60 saturate that value at seven, and bit 63 is an any-complete flag.
This cannot alias any nonzero occupancy through either the four-slot FPGA or
ten-slot simulation endpoint.

The corrected ten-slot UCE gate fills all ten entries and reads an exported
count of ten. The controller packing gate, all 153 discovered Linux tests, and
a clean trace-enabled two-thread/four-context full-core replay run pass through
guest, CORE, and host markers. The known post-PASS GPIO finalizer assertion is
classified as `VALID RUN`. Exact full-core build/run/FST/ELF/NBF SHA-256 values
are `5931752f...e0f`, `106d383a...659`, `fb5dc0ff...e70`,
`c6c9e734...89c`, and `abb83ed0...9a9`.

The accepted performance baseline uses the four-context/four-slot 16 KiB
endpoint `e_bp_unicore_zynqparrot_prefetch16k_cfg`, as confirmed by its 94.5
BRAM route. The corrected telemetry candidate must use that same endpoint;
the canceled job's base `prefetch` endpoint was not a matched physical control.

The matching Linux candidate links as `vmlinux` `b3eff097...641`; raw payload
`c1a7bbea...9b0` splices into shell NBF `22a6e794...9b5`, and reverse splicing
reproduces the prior corrected shell NBF `4e91d7b6...8d9` byte-for-byte. The
dynamic benchmark and 50-command transfer hash to `83ea1cf3...f43` and
`b6ea2b9b...b2a`, and local transfer execution reconstructs the exact ELF.
Patch `0017` passes reverse dry-run against the linked source and forward
dry-run against an isolated pre-patch reconstruction. The complete simulator,
waveform, UCE, kernel, NBF, benchmark, and transfer bundle is preserved under
`/home/coyang/fpga-artifacts/context-resume/tagged-replay-telemetry-count3-20261104/`;
its manifest verifies in full.

The exact matched route signs off only after post-route physical optimization:
setup WNS/TNS is `+0.009/0 ns`, hold WHS/THS is `+0.026/0 ns`, and utilization
is 50,423 LUTs (94.78%), 25,191 registers, 94.5 BRAM tiles, and 11 DSPs. The
farm launcher initially selected the earlier routed report and falsely labeled
the job failed; a branch-pinned recheck selected the post-physopt report and
marked job `20261104T063840Z-9722a332` PASS. The exact package and bitstream
hashes are `dec404e7...9e4` and `7c90de5e...403`.

On FPGA, the first corrected telemetry run completes 512 balanced trials and
final CORE/BSG PASS. Both the parent pre-block probe and the child userspace
entry probe report zero allocated UCE slots and zero completed replies awaiting
retirement in every arm. The latter probe costs roughly 1,200--1,400 cycles,
so this proves only that replay has drained by the syscall observation point;
it does not prove that no work was live at the architectural switch boundary.
The corresponding unprobed retry saves `186.75 [169,200.5]` local-load cycles
but loses `2048.25 [692,3764.5]` wake-to-load cycles. A later recovered old-image
control saves `213.5` local cycles and loses `1539.5` wake-to-load cycles. These
are separate runs rather than pooled replicates, but both preserve the same
conclusion: useful cache warming remains smaller than the wake-path penalty.

One unprobed launch stalled during Linux initialization and was rejected before
benchmark execution. A proposed earlier kernel-side snapshot was also rejected:
both an expanded-`thread_struct` build and a layout-safe build that reused
existing diagnostic counters emitted binary fragments into the boot console and
lost the runner before userspace, while a fully recovered old-kernel control on
the same route completed all trials and terminal markers. All snapshot code was
reverted and the 97-test baseline harness passes.

The replacement instrument preserves the exact passing Linux image. Replay
status bits 59:58, whose old active-slot value is not consumed by the benchmark,
now encode time since the controller and downstream UCE both became idle: zero
means no completed drain or live replay, one means 1--511 cycles, two means
512--2047 cycles, and three means at least 2048 cycles. Counter clear resets the
age, so disabled trials remain a zero control. The standalone controller checks
all four transitions and a new trigger reset; the full-core guest additionally
requires a visible fresh drain and saturation after 2050 cycles. The controller,
all 154 discovered Linux tests, and a clean trace-enabled two-thread/four-context
full-core run pass. Exact build/run/FST/ELF/NBF hashes are
`1c36551e...526`, `568cf8e5...fd5`, `227d7265...afe`,
`c29e5e55...d5d`, and `acdedcac...98f`.

Two command-invocation mistakes produced no test result: direct module-style
`unittest` omitted the `linux-tests` import path, and the first standalone RTL
runner call omitted its required `--out` flag. The guardrail is to use
`make -C linux-tests check-harness` and inspect each isolated runner's
`--help`/argument parser before launch. Both canonical reruns pass as reported
above. A later incremental Linux link also omitted `BR_BINARIES_DIR`, stopped
before linking because `/rootfs.cpio` was unavailable, and produced no image;
the accepted rerun explicitly binds it to the retained Buildroot images path.

Do not continue delay/gap/lead tuning from this checkpoint. The next diagnostic
must measure the non-invasive RTL drain-age telemetry on the matched FPGA;
after that, the next RTL
candidates should separately test demand-high/prefetch-low AXI QoS and a
one-outstanding prefetch cap. A wider replay window is lower priority because
it may increase the already measured scheduler-path contention. Any candidate must rerun
the phase-balanced 32/16/8-line gates and preserve the existing overlap
liveness tests.

`evidence/SHA256SUMS` binds every retained compressed transcript, status,
analysis, exact executable, and guest transfer.
