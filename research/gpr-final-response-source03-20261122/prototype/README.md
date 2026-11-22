SOURCE-ONLY prototype; no compiler, model, inventory, vendor or native run.
No production source, HEAD, geometry, capacity or bisection policy changed.
This isolated packet is UNADMITTED. No area saving or functional PASS exists.

The selected contract is the exact resource agent audit under:
/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/csr256-fixed-state-area-audit-20261122/{source-contract.json,FINDINGS.md}
TOP a44c03bb7 / BP1e7aa2fdc. The production bp_be_top file was read directly;
bp_be_context_mem was read using git show of exact BP1e7, not parent-directory
Git discovery. No new checkout or full88KB top snapshot is needed here.

Implementation: gpr_context_held.sv is fixed actual
4contexts x32registers x64bits,16 independent banks with8words perbank. Each
has independent synchronous1R+1W. Remote port1 wins over port0 on every write;
selected addresses/cycles are unchanged. A read only updates its actual raw
response on r_v. Independent subsequent writes, even to that held address,
cannot change the response. No separate1024b holding latch/bypass is added.
The direct synchronous response declaration is intended to infer the enabled
RAM read output; actual inference/resources/primitive semantics are pending.
Captured16 valid bits, taken from the old bitmap at accepted read, mask each
response lane. Payload RAM is not reset. Reset clears tokens and validity;
like the original leaf, physical writes/reads are independent of metadata reset.

The source's bsg_mem_1r1w_sync uses read_write_same_addr=0. The prototype
exports the identical forbidden selected-write/read-bank-address condition;
the ROOT gate must reject it. Different-address read+write remains concurrent.
The original generic BSG no_llr leaf deliberately sets its registered address
X on idle. Merely changing the top data mux to that current output is unsound.
Enabling generic latch_last_read would add a hold path and is not the proposal.

gpr_prefetch_shell.sv keeps line0's1024b snapshot and original two response/valid
and install events. It removes only line1's duplicate. Candidate final data is
the held backing response and captured16-bit mask, not the live validity map.
A full1024b snapshot remains in the REFERENCE only. Atomic branch choices are
extracted from bp_be_top:466-470/500-533/1023-1090/1144-1215/1239-1264.
The envelope fixes FP-disabled actual production behavior, including:
- exactly two reads during wait-for-commit/drain; issue_done stops a third;
- original response acceptance even during redirect, followed by identical
  new-miss/reset priority; squashed buffered data cannot install;
- drain can install the first line on the same edge it enters save/restore;
- final RF write can coincide with FE launch/capture; FE backpressure goes to
  launch_fe with no new backing read, preserving the final-line ownership;
- reset/redirect ends the old lease; a new miss clears both slot-valid tokens.
No next read is permitted while the final line is leased. This is checked
explicitly, not inferred from absence in a trace. No pending PF lease or
retained-backend atomic-copy change is involved.

The minimum leaf/controller gate is driver.cpp plus four named-module SV files. The
reference stores scalar words, reproduces BSG idle-X addressing and live
validity, and takes BOTH old top snapshots. The independent C++ scoreboard
uses its own scalar store, validity, accepted-read snapshots and FSM. It checks
all1024 response bits and every full1024 RF write, metadata/request/response/
slot-valid/control and RF/FE timing. It exercises partial/full valid contexts,
both write intents/priority, legal parallel read+write, writes after the final
read to its same address, early and long drain, no-dirty bypass, simultaneous final RF/FE and FE holds, redirect/abort, held reset,
new misses and consecutive two-line reads. READ_FIRST ordering is explicit in
the oracle. Negative1 corrupts a borrowed high data bit; negative2 corrupts
captured lane15 validity. Both must reject at the full1024 oracle. A separate
same-bank-collision invocation must reject before unsafe acceptance.

This is a source recipe, not a frozen executable admission. ROOT should bind
all packet bytes, exact production sources/dependencies and actual installed
Verilator/G++/make plus qualified software_owned_v2 API before running. New
prospective stage128MiB, source packet64KiB, no waveform output, 2compile
workers/cacheoff/PCHoff,120s each generation/build/runtime phase,512MiB free
floor plus complete remaining allocation and all current OTHER reservations.
Fresh ROOT metadata/admission/global-idle review is required. None is assumed.

ROOT command structure after funded source review (DO NOT run this README as
a script; ROOT must wrap each argv with the qualified owned bounded lifecycle):

  verilator --cc --exe --top-module gpr_prefetch_miter --Mdir FRESH/normal \
    --Wall gpr_context_reference.sv gpr_context_held.sv \
    gpr_prefetch_shell.sv gpr_prefetch_miter.sv driver.cpp
  make -C FRESH/normal -f Vgpr_prefetch_miter.mk -f QUALIFIED_NO_PCH_MK \
    -j2 OBJCACHE= Vgpr_prefetch_miter
  FRESH/normal/Vgpr_prefetch_miter
  FRESH/normal/Vgpr_prefetch_miter --collision

Generate two NEW directories/snapshots with exactly -Gnegative_p=1 and2
(parameter int, not the previous one-bit CLI issue), same remaining args and
compile flags; each executable must run --negative and produce the anchored
GPR_BORROW_NEGATIVE_REJECTED marker with return0. Positive requires exactly
one GPR_BORROW_PASS and no negative/FAIL; collision requires its exact rejected
marker. Capture full stdout, source/end hashes, all command/lifecycle receipts,
all actual counters and instantiated production widths. Stop on any failure;
no retries, timing truncation, warning disable or coverage omission. This
packet has deliberately not been compiled or syntax-qualified yet.

Next gates if component passes: matched production-context inference and real
mapped memory read enable/hold/collision test, then fullcore architecture and
source-qualified context-switch timing. A whole-device gate is separate. At
most1024 duplicate declared bits are removed; physical FF/LUT/BRAM/controlset
and routed headroom effects are unknown. The independent parallel regfile
operand memories and RPC/state shadows are untouched.

The two *.sv.source-history files preserve unexecuted initial aggregation.
They are not compilation inputs; named-module files avoid filename lint noise.
All prospective packet accounting includes that history. No source gate ran.

ATTEMPT02 source-only successor: failed01 is durably preserved by closure
1633f6cb25a40bc616763ad51a92fe682f50c7d2ba52aef59c5a9ff5d5bb3987.
Only leaf memory namespace and branch-local raw/mask hookups change; the
reference, oracle, stimulus, policy, equations and all control/data gates do
not change. See successor-source.diff and successor-proof.json. New helper
uses fresh RUN02 and charges compiler temporaries with TMPDIR=RUNroot.
No source/helper01 file is changed and no generation/compile run occurred here.

ATTEMPT03: actual02 header declares VL_INW(&w_data_i,127,0,4).
Only its initialization range-for becomes four explicit32-bit indexed stores.
All RTL and every oracle/stimulus statement after that initialization are
byte-identical. See initialization-only.diff/proof. Attempt02 generated
without warnings, then stopped at C++ begin/end errors before model execution.
Fresh03 remains SOURCE ONLY; exact failure02 closure binding is required
before its execution authority is prepared/promoted. No compiler ran here.
