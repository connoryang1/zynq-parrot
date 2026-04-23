# Context Switch Architecture

This note explains the current BlackParrot multithreading/context-switch path in
this repo, what was optimized to reach the verified 7-cycle microbenchmark
result, and what work remains if the goal is to make that 7-cycle path happen as
often as possible.

Current verified checkpoints:

- `zynq-parrot`: `4a02afe` (`tighten ctxtsw microbenchmark to immediate csr writes`)
- `import/black-parrot`: `3affb651` (`allow ctxtsw to escape icache miss state`)

## Current Bottom Line

The current repo has two independently useful timing checks for ctxtsw:

- `mt_ctxtsw_microbench`
  - measures the minimal warm `T0 -> T1 -> T0` round-trip
  - current result: `14` cycles round-trip, i.e. `7` cycles per switch
- `mt_ctxtsw_partial_unroll_benchmark`
  - measures steady-state switch cost in a ring while amortizing loop overhead
  - current result: `7` cycles/switch
- `mt_ctxtsw_unrolled_ring_stress`
  - checks a dense 4-context pure ring with 8 consecutive `csrwi` per context
  - current result: `CORE PASS` / `BSG PASS`

Together, those are enough to support the practical claim that the warm ctxtsw
fast path is `7 cycles/switch` on this implementation.

For correctness coverage, the most important supporting tests are:

- `mt_regfile_test`
- `mt_csr_isolation_test`
- `mt_frf_isolation_test`
- `mt_banyan_benchmark`

Older timing variants such as the naive round-trip benchmark with heavier
printing and the extra hotness/boundary sweep tests were useful during bring-up
but are no longer the primary checkpoints.

## Big Picture

This machine is still a normal pipelined BlackParrot core. The multithreading
support does not create multiple independent pipelines. Instead, it adds
per-thread architectural state and a hardware-controlled way to jump from one
thread context to another.

Conceptually, a context switch is:

1. Software executes `csrw 0x081, tid`.
2. The BE retires that instruction and changes the current thread id.
3. Hardware loads the target thread's saved context state.
4. The FE redirects fetch to that thread's saved next PC.
5. The target thread resumes executing.

So the machine behaves like one core that can rapidly swap which thread's
architectural context is "live".

## Main Blocks

### Backend

- `bp_be_thread_scheduler.sv`
  - Holds the current thread id register.
  - On a committed write to CSR `0x081`, updates the live thread id.

- `bp_be_context_storage.sv`
  - Stores per-thread:
    - next PC
    - privilege mode
    - translation enable
    - ASID
  - On context switch, the current thread's resume state is saved.
  - On the next switch, the target thread's saved state is read back out.

- `bp_be_director.sv`
  - Converts backend events into frontend commands.
  - For ctxtsw, emits `e_op_context_switch` with:
    - target NPC
    - privilege / translation / ASID state
    - target thread id encoded in FE metadata

- `bp_be_top.sv`
  - Wires the scheduler, context storage, and director together.
  - This is where the backend's committed ctxtsw becomes a frontend redirectable
    event.

### Frontend

- `bp_fe_controller.sv`
  - Consumes FE commands.
  - Treats ctxtsw as an immediate redirect-like event.
  - Drives `icache_force_o` during immediate redirects.

- `bp_fe_pc_gen.sv`
  - Chooses the next fetch PC.
  - Updates the selected thread id on ctxtsw redirect.
  - Already uses per-thread predictor structures, but not a fully duplicated FE.

- `bp_fe_icache.sv`
  - Shared frontend icache pipeline/state machine.
  - This turned out to be the key performance bottleneck.

## What The Machine Was Doing Before The Fix

Before the final optimization, the context-switch mechanism was functionally
correct but not always fast.

The backend part was already relatively quick:

1. `csrw 0x081, tid` retired.
2. The thread scheduler updated the current thread id.
3. Context storage exposed the target thread's saved NPC/state.
4. The director emitted a ctxtsw FE command.
5. FE consumed the command quickly.

The hidden problem was in the shared frontend icache state machine.

Even after FE had accepted the redirect, the icache could still be in
`e_miss` or `e_recover` because of an older request from the previously running
thread. When that happened, the new thread's first fetch had to wait behind old
thread miss handling.

So the machine looked like this:

- backend handoff was fast
- FE redirect signal was fast
- but actual resumed-thread fetch could still be blocked by shared old-thread
  icache miss state

That is why the earlier measurements stayed far above 7 cycles even after we
improved the BE-to-FE path.

## The Key Optimization

The final hardware fix was in `bp_fe_icache.sv`.

Old behavior:

- `e_miss` waited until the miss fully completed
- `e_recover` returned to ready
- a forced redirect could override the TL handoff, but it could not escape the
  shared icache miss state machine itself

New behavior:

- if `force_i` is asserted during `e_miss`, the icache returns directly to
  `e_ready`
- if `force_i` is asserted during `e_recover`, the icache also returns directly
  to `e_ready`

In other words:

- a ctxtsw redirect is now allowed to break out of the old thread's outstanding
  frontend miss/recover state
- the new thread is no longer serialized behind stale speculative FE work

That is what changed the hardware behavior materially.

## Why That Was Enough To Reach 7 Cycles

After the icache fix, the remaining extra cycles came from the benchmark
itself, not the hardware path.

The resumed thread in the original stripped microbenchmark still executed a few
setup instructions before switching back:

- `la gp, __global_pointer$`
- `li t0, 0`
- `csrw 0x081, t0`

That is not "switch overhead"; it is worker-thread instruction overhead.

So the benchmark was tightened to use immediate CSR writes on both sides:

- T0 uses `csrwi 0x081, tid`
- T1 immediately executes `csrwi 0x081, 0`

With that benchmark shape, the repo now verifies:

- warm round-trip: `0x0e`
- warm single-switch estimate: `0x07`

So the story is:

1. hardware fix removed the real FE bottleneck
2. benchmark cleanup removed software measurement overhead
3. the resulting number matches the 7-cycle target

## What 7 Cycles Means

It means the machine can perform a warm, minimal context switch in 7 cycles per
switch when:

- the target thread has already been seeded
- the target thread's first instructions are I$-hot
- the switched-to thread immediately switches back
- the measured window excludes unrelated software/setup overhead

It does not mean every arbitrary workload switch will always be 7 cycles.

## Why One Ring Benchmark Read As 9 Cycles

After the restore-path correctness fixes, the repo still showed an apparent
discrepancy:

- `mt_ctxtsw_microbench`: warm round-trip `14`, implying `7` per switch
- naive steady-state ring benchmark: `9` cycles/switch

That looked like a hardware discrepancy at first, but disassembly showed the
naive ring benchmark was not a pure switch stream. Each resumed thread was
executing:

- `csrw 0x081, next_tid`
- `addi counter, -1`
- `bnez counter, loop`

So the benchmark was charging two extra retired loop-control instructions to
every switch.

To check that directly, a partial-unroll ring benchmark was added that keeps
the same seeded-thread/resume model but performs four ctxtsw instructions per
loop iteration. That reduces the `addi + bnez` overhead to one pair per four
switches instead of one pair per switch.

With that benchmark shape, the repo again measures:

- `7 cycles/switch`

So the earlier `9`-cycle number was a benchmark artifact, not evidence that the
hardware fast path had regressed.

## Unrolled Ring Robustness

One remaining concern was whether the machine could handle a denser pure-switch
pattern with no loop bookkeeping at all. A 4-context stress test was added that
seeds three worker contexts and then runs a pure ring:

- T0 executes 8 straight `csrwi 0x081, 1`
- T1 executes 8 straight `csrwi 0x081, 2`
- T2 executes 8 straight `csrwi 0x081, 3`
- T3 executes 8 straight `csrwi 0x081, 0`

This test now passes cleanly. An earlier apparent "wedge" turned out to be a
simulation-timeout artifact during slow Verilator startup/rebuilds, not a
confirmed RTL bug.

## When It Will Take Longer

The switch will legitimately exceed 7 cycles when:

- the resumed thread executes extra instructions before switching back
- the resumed thread takes an icache miss
- the measurement includes setup/printing/loop/control overhead
- the machine is in a colder or more disturbed FE state
- the test is measuring end-to-end work rather than the bare ctxtsw path

Correctness/isolation features like ASID tagging help preserve the fast path in
realistic address-space-switch scenarios, but they are not the primary source
of the 7-cycle result.

## Plan To Make 7 Cycles More Common

The current repo has proved that the hardware path can hit 7 cycles. The next
phase is robustness, not proof-of-possibility.

1. Keep the current checkpoints as the restore baseline.
   - `4a02afe`
   - `3affb651`

2. Keep at least one steady-state benchmark that amortizes loop bookkeeping.
   - The partial-unroll ring benchmark is a useful complement to the round-trip
     microbench because it validates `7 cycles/switch` without relying only on
     `14 / 2`.

3. Add one or two more narrow measurements if needed.
   - warm switch with target-thread I$ line intentionally hot
   - warm switch with target-thread code placed to stress a nearby miss boundary

4. Investigate the remaining non-clean console behavior separately.
   - do not mix console cleanup with further ctxtsw hardware work

5. If needed, reduce avoidable FE disturbance further.
   - only if measurements show recurring non-7-cycle cases caused by FE sharing
   - do not broaden the RTL unless data shows a real remaining bottleneck

## File Map

- `import/black-parrot/bp_be/src/v/bp_be_top.sv`
- `import/black-parrot/bp_be/src/v/bp_be_thread_scheduler.sv`
- `import/black-parrot/bp_be/src/v/bp_be_context_storage.sv`
- `import/black-parrot/bp_be/src/v/bp_be_checker/bp_be_director.sv`
- `import/black-parrot/bp_fe/src/v/bp_fe_controller.sv`
- `import/black-parrot/bp_fe/src/v/bp_fe_pc_gen.sv`
- `import/black-parrot/bp_fe/src/v/bp_fe_icache.sv`
- `testing/mt_ctxtsw_microbench.c`
- `testing/mt_ctxtsw_partial_unroll_benchmark.c`
