# PYNQ-Z2 Build And Deployment Reference

## Current build

From `cosim/black-parrot-example/vivado`:

```bash
make fpga_build pack_bitstream \
  BOARDNAME=pynqz2 \
  VIVADO_VERSION=2024.2 \
  VIVADO_MODE=batch \
  CFG=e_bp_unicore_zynqparrot_cfg
```

A clean milestone build may prefix `make clean`, but a fresh isolated worktree does not need it.
The expected packed artifact is:

```text
cosim/black-parrot-example/black_parrot_bd_1.zynq.pynqz2.tar.xz.b64
```

Vivado's routed timing report normally resides below:

```text
black_parrot_bd_proj.runs/impl_1/
```

## Prerequisites

- `/tools/Xilinx/Vivado/2024.2/settings64.sh`
- initialized pinned submodules, including nested BlackParrot and BaseJump dependencies
- populated repository `install/` and `riscv/` trees from `make prep_lite`
- a configuration enum that exists in the pinned BlackParrot RTL

### Sourceware rate-limit fallback

The SDK's RISC-V GNU toolchain may receive HTTP 429 from Sourceware. Preserve the gitlinks and
change only the fetch transport:

- binutils: `https://github.com/riscvarchive/riscv-binutils-gdb.git`
- GDB: `https://gnu.googlesource.com/binutils-gdb`
- glibc: `https://github.com/bminor/glibc.git`
- GCC: retain `https://github.com/gcc-mirror/gcc.git`
- newlib: `https://github.com/RTEMS/sourceware-mirror-newlib-cygwin.git`

Run `../scripts/setup_sourceware_mirrors.sh` from this skill instead of editing the SDK's tracked
`.gitmodules`. The helper uses shallow checkouts and verifies the final commits against gitlinks.

The historical `bp_unicore_zynqparrot_cfg_p` argument is not the current enum used by this
repository. Prefer `e_bp_unicore_zynqparrot_cfg` unless the active branch explicitly adds a new
configuration.

## Board deployment

Keep deployment separate from build validation. First verify the package locally:

```bash
codex-skills/bp-fpga-synthesis/scripts/verify_pynq_package.sh \
  cosim/black-parrot-example/black_parrot_bd_1.zynq.pynqz2.tar.xz.b64
```

Record the package SHA, bitstream SHA, and reported artifact stem. With authorization, copy the
exact package and NBF to the board. Do not trust already unpacked collateral. Explicitly extract
the selected package and verify the resulting `.bit`:

```bash
base64 -d ../black_parrot_bd_1.zynq.pynqz2.tar.xz.b64 | tar xvJ
sha256sum black_parrot_bd_1.bit
```

The board checkout and package should come from the same top-level revision. Older checkouts may
use `blackparrot_bd_1.*` while current packages contain `black_parrot_bd_1.*`. Update the board
checkout or copy the verified `.bit`, `.hwh`, and `.map` to the expected stem together; never mix
members from different packages.

Prefer the guarded staging helper for this sequence:

```bash
codex-skills/bp-fpga-synthesis/scripts/stage_pynq_artifacts.sh \
  <package.tar.xz.b64> xilinx@192.168.4.35 <program.nbf> [...]
```

It detects the board Makefile's load stem and prevents a new NBF from being run against an old
same-directory bitstream under the historical `blackparrot_bd_1` name.

### Unattended overlay reload

Install the root-owned fixed-path loader once on the board. Copy the installer from this skill to
the board, inspect it, and run:

```bash
sudo ./install_pynq_overlay_loader.sh
```

The installer validates its sudoers fragment before activation and installs:

- `/usr/local/sbin/load-blackparrot-overlay`, owned by root and mode `0755`
- `/etc/sudoers.d/blackparrot-overlay`, owned by root and mode `0440`

The sudo rule permits only that helper. The helper accepts no arguments and loads only
`/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq/blackparrot_bd_1.bit` with its matching
HWH. It does not grant passwordless Python, shell, `make`, or arbitrary-path execution. Because
the `xilinx` user can replace the fixed-path bitstream, this deliberately grants unattended FPGA
programming capability; do not use the rule on a shared or untrusted board account.

After staging a verified package, load it from the VM with:

```bash
codex-skills/bp-fpga-synthesis/scripts/load_pynq_overlay.sh xilinx@192.168.4.35
```

Require `LOADING_BIT_SHA256` to match the staged `BOARD_BIT_SHA256` and require both
`OVERLAY_LOAD_OK=1` and `REMOTE_OVERLAY_LOAD_OK=1` before launching a target image.

### Retained board-run transcripts

`control-program` configures terminal state and must be given a pseudo-terminal. A plain detached
SSH command can lose all target output (or leave an uninspectable root child), so launch retained
board tests through `script` and poll the board-side transcript:

```bash
ssh xilinx@<board> '\
  cd ~/zynq-parrot/cosim/black-parrot-example/zynq || exit 1; \
  rm -f <run>.log <run>.pid; \
  nohup /usr/bin/script -qef -c "sudo -n ./control-program <program>.nbf" \
    <run>.log </dev/null >/dev/null 2>&1 & \
  runner_pid=$!; echo "$runner_pid" > <run>.pid; echo "RUNNER_STARTED_PID=$runner_pid"'
ssh xilinx@<board> 'tail -n 120 ~/zynq-parrot/cosim/black-parrot-example/zynq/<run>.log'
```

Require the transcript to contain the target marker (`CORE[0] PASS` or `CORE PASS`) and record its
bitstream and NBF hashes. Treat an SSH-stream cutoff as inconclusive until the retained log is
read. If the root runner cannot be stopped through its parent `script` process, power-cycle the
board, reload the overlay, and start a fresh run; do not reuse a possibly contaminated fabric.

### Recovering an unreachable board

If the board refuses SSH and the controlled outlet is available, export its state endpoint only
for the current shell and run:

```bash
PYNQ_POWER_STATE_URL='<private-state-endpoint>' \
  codex-skills/bp-fpga-synthesis/scripts/power_cycle_pynq.sh \
  xilinx@192.168.4.35
```

The helper powers the outlet off, waits briefly, powers it on, and polls SSH with bounded timeouts.
Do not commit or print the endpoint because it contains a controller credential. Treat a successful
SSH reconnect only as evidence that the board OS rebooted. Power cycling removes the loaded
BlackParrot overlay and invalidates prior CMA/DRAM allocation state, so reload the intended overlay
and recheck the bitstream and NBF hashes before running a test.

### Interactive Linux image

The dated Jan. 25 Linux regression image runs `/init`, executes its test scripts, and powers off;
it is not Jack's missing interactive `linux.nbf`. Create a shell derivative without rebuilding
the kernel or initramfs:

```bash
codex-skills/bp-fpga-synthesis/scripts/make_linux_shell_nbf.py \
  riscv/linux/linux-6.6-jhumphri-20250125.nbf /tmp/linux-shell.nbf
```

This replaces `root=/dev/ram0` with the equal-length `rdinit=/bin/sh`. The NBF loader's byte and
halfword read-modify-write expressions are unsafe, so the helper preserves surrounding bytes and
uses aligned 8-byte commands only. Validate success with `Run /bin/sh as init process`, a shell
marker, `uname -a`, `poweroff -f`, and `CORE[0] PASS`. A direct `rdinit` shell does not run the
normal init scripts; mount `/proc` manually before reading `/proc/cpuinfo`.

The Jan. 24 historical bitstream must use its historical threaded FIFO decoder. The newer
`bsg_host` polling runner can stall this image at about 0.133 IPC with no console output, while the
compatible runner boots near 0.5 IPC. Preserve the threaded decoder and apply only the owned-CMA
fix: never reuse a DRAM pointer from a previous `control-program` process. The historical monitor
thread is not joined and can segfault after a clean target poweroff; treat that as a host teardown
bug only when `CORE[0] PASS` and the target poweroff are already present.

Reload the overlay immediately before every Linux trial, even when the previous `control-program`
exited normally. The tag-client reset does not reliably return every historical design register to
its power-on state: repeated runs without reprogramming have started with `reset(lo)=1`, retired no
instructions, and produced no console output. A fresh load starts with `reset(lo)=0`. If an external
timeout or interrupted SSH session kills the host runner, consider the fabric state contaminated
and reload before drawing any conclusion.

Do not pass the optional third argument to archived `control-program-protocol-compatible-bounded`
binaries as though it were a wall-clock millisecond deadline. At least one archived binary applies
that limit according to polling activity and can stop a healthy target less than a second after
release. Omit that argument. Do not wrap an unprivileged `sudo ./control-program` invocation with
GNU `timeout`: on the PYNQ image, `sudo` may fork the root runner, after which `timeout` kills only
the `sudo` parent and leaves `control-program` running as an orphan. A deadline is reliable only
when `timeout` itself is launched as root, for example when that exact command has been granted
non-interactive sudo access:

```bash
sudo -n timeout --signal=TERM --kill-after=5s 300s \
  ./control-program <program>.nbf
```

Without that narrow sudo permission, supervise the run from the VM and use
`scripts/power_cycle_pynq.sh` when the deadline expires. A power cycle is the dependable way to
terminate an orphaned root runner and also restores a known board state. Reload the intended
overlay after the board returns before starting the next trial.

The verified control identity is the Jan. 24 bitstream SHA-256 beginning `d45f7e3e` with the Jan. 25
Linux NBF SHA-256 beginning `994bd900` and the compatible owned-DRAM runner SHA-256 beginning
`76db506e`. On a freshly loaded overlay this pair reaches `/init`, powers down, and reports
`CORE[0] PASS`; one Aug. 28 control run retired 321,538,678 instructions at 0.514 IPC.

Before an application run, inspect the Makefile or compile command for `DRAM_TEST`. It must be
absent. That mode performs a destructive 64 MiB connectivity diagnostic and is not evidence that
an NBF loaded or executed. Program the freshly extracted overlay in an interactive board shell:

```bash
make load_bitstream \
  BOARDNAME=pynqz2 \
  VIVADO_VERSION=2024.2 \
  VIVADO_MODE=batch

sudo ./control-program <program>.nbf
```

Record the board-side bitstream and NBF SHA immediately before the run. A successful staged
context-cache probe prints `ABRrNP` and `CORE[0] PASS`. Do not put host MMIO followed by a fence
inside the measured switch region; that tests the I/O drain path rather than a pure handoff.

## Application image

For the maintained FPGA regression images, use:

```bash
make -C testing fpga-tests NUM_THREADS=2 NUM_CONTEXTS=4
```

This rebuilds the integer-only DRAMFS startup and emits NBFs with the required `--config --debug`
preamble. Preserve the exact SDK revision and compiler flags with performance-sensitive programs.

## Required run-state checks

Before interpreting a failure, distinguish these stages in order:

1. package extracted and board-side bitstream SHA matches
2. overlay explicitly reloaded after extraction
3. host runner built without `DRAM_TEST`
4. NBF SHA matches and loader reports its finish command
5. integer startup markers execute
6. resident round trip completes
7. nonresident SRAM-backed round trip completes

Do not change RTL until the failing stage is localized. A host allocation error, diagnostic-only
runner exit, startup/FPU mismatch, MMIO fence stall, and context-switch failure can otherwise all
look like “no output.”

### Silent pre-console Linux triage

When the loader finishes and the core continues retiring instructions but neither OpenSBI nor
Linux prints anything, reduce the image before changing the kernel or host runner:

1. Preserve every NBF configuration record, but keep only firmware memory writes below the Linux
   payload boundary (normally `0x80200000`). Run this OpenSBI-only prefix with the same bitstream
   and runner.
2. If the reduced image has the same IPC/instruction-retirement signature, treat the failure as
   machine-mode firmware startup rather than Linux.
3. Disassemble the exact firmware image. OpenSBI's single-hart election normally loads the
   `_boot_status` address into `a6`, executes `amoswap.w a6,a7,(a6)`, and immediately branches on
   the returned old value. A wrong or stale nonzero value sends the only hart into the deliberate
   secondary-hart wait loop before console initialization.
4. Build the focused diagnostic and verify it in a clean traced simulator before the board:

   ```bash
   make -C testing clean run-mt_amo_swap_return_test \
     TRACE=1 NUM_THREADS=2 NUM_CONTEXTS=4
   make -C testing \
     "$PWD/riscv/bp-tests/mt_amo_swap_return_test_fpga.nbf" \
     NUM_THREADS=2 NUM_CONTEXTS=4
   ```

The diagnostic intentionally uses `a6` as both the nonzero address input and AMO destination,
uses OpenSBI's plain `amoswap.w` without `.aq`, `.rl`, or `.aqrl`, and places the conditional
branch immediately after the AMO. Do not change the ordering bits or simplify it to a separate
destination register: either change can exercise a different pipeline path or miss the speculative
memory-result catchup case. Record all four
architectural values (two returned old values and two memory values), both immediate branch
decisions, the NBF SHA, and the waveform around the AMO/branch window.

When patching firmware instructions for a board probe, emit aligned 8-byte NBF writes that preserve
the surrounding instruction bytes. Do not emit command `00` or `01` byte/halfword writes. The
current host loader's read-modify-write path uses an incorrect subword shift and ambiguous operator
precedence, so an offline reconstruction of the intended NBF can disassemble correctly even though
the board received different bytes. Confirm the final NBF contains a command `03` at an 8-byte
aligned address for every code patch. Use the repository helper rather than editing NBF lines by
hand; it reconstructs each touched 8-byte block from the source NBF before overlaying the patch:

```bash
codex-skills/bp-fpga-synthesis/scripts/patch_nbf_bytes.py \
  input.nbf output.nbf --patch 0x80000000:probe.bin
```

### Linux PC milestone probes

For a post-OpenSBI silent Linux image, prefer a disposable stop-at-PC probe before adding RTL
instrumentation. `tools/make_linux_milestone_nbf.py` replaces a small physical instruction
window with two long-standing host put-character writes and a normal finish packet:

```bash
python3 tools/make_linux_milestone_nbf.py \
  riscv/linux/linux-6.6-jhumphri-20250125.nbf /tmp/linux-m1.nbf \
  --pc 0x802010d0 --marker 1 --expect-first-word 0x10401073
```

The runner prints `M1` immediately before `CORE PASS` only if execution reached
that exact PC. Run separate probes at increasingly later known physical PCs to bracket a stall.
The optional expected-word guard rejects stale addresses or a mismatched image. These probes are
diagnostic only: host MMIO changes timing and the probe intentionally terminates, so never use them
to measure performance or certify an uninstrumented Linux boot. They are reliable before virtual
memory is enabled. A source-NBF patch after the first main-kernel `satp` write is conclusive only
when the translated physical address of that PC is known: the pre-translation physical address need
not contain the next fetched instruction. `--disable-satp` is safe only after that mapping has been
established, because it clears translation and exits immediately; it is not a continuing Linux
instrumentation mechanism.

For the archived `linux-6.6-jhumphri-20250125.nbf`, begin with this ordered map (each value is
the guard word at that physical PC):

| Marker | PC | Guard word | Meaning |
| --- | --- | --- | --- |
| 1 | `0x802010d0` | `0x10401073` | Linux S-mode entry |
| 2 | `0x80201102` | `0x016eb697` | boot-hart AMO path completed |
| 3 | `0x80201120` | `0x016eb617` | BSS clear completed |
| 4 | `0x8020113c` | `0x4097852e` | stack initialized, first kernel call pending |
| 5 | `0x80c05544` | `0xe8a2711d` | early main-kernel target reached |
| 6 | `0x80c06430` | `0x18079073` | immediately before first main-kernel `satp` write |
| 7 | `0x80201146` | `0x00004517` | early main-kernel routine returned to its S-mode caller |
| 8 | `0x80201000` | `0x01299597` | caller's relocation / `stvec` / `satp` transition helper entered |
| 9 | `0x80201044` | `0x18051073` | immediately before the helper's first `satp` write |

Start at 1 and 6. If one fails, use the intervening entries; add a narrower address range only
after those coarse boundaries identify it. Derive virtual-to-physical translation before attempting
a post-`satp` probe.

### Silent-Linux diagnostic bundle

Treat a silent Linux boot as a staged diagnosis, not a single pass/fail result. Before any RTL
change or another routed build, retain a directory containing:

1. top-level, BlackParrot, package, extracted-bitstream, runner, and NBF SHA-256 values;
2. the exact board console log and whether the overlay was freshly loaded;
3. ordered physical milestones through marker 9, stopping as soon as the first expected marker is
   absent; and
4. a matching local `TRACE=1` S-mode/Sv39 run and its FST, analyzed with
   `tools/satp_fst_tail.awk`:

   ```bash
   BSG_TRACE_TIMEOUT_S=120 \
     make -C testing clean run-mt_smode_sv39_entry_test TRACE=1
   fst2vcd cosim/black-parrot-minimal-example/verilator/dump.fst \
     | awk -v tail=128 -f tools/satp_fst_tail.awk
   ```

`BSG_TRACE_TIMEOUT_S` is a simulator-internal clean trace bound. Prefer it to an external
`timeout` around the simulator Makefile: a process-group timeout can kill the parent while leaving
the Verilator child and shared `run.log` alive. The tail extractor records SATP writes and the
final retired PCs/virtual addresses without materializing a giant VCD. Once an earlier run has
identified a useful cycle range, pass it without rebuilding the test program:

```bash
SIM_RUN_ARGS='+bsg_trace_start_cycle=<first> +bsg_trace_stop_cycle=<last>' \
  BSG_TRACE_TIMEOUT_S=120 \
  make -C testing run-mt_smode_sv39_entry_test TRACE=1
```

This dramatically reduces FST conversion time by excluding the slow NBF load from the waveform.

Do not add an ILA merely to obtain these milestones: the current candidate already uses all 140
PYNQ-Z2 BRAM tiles. A translation-aware software probe or a focused local FST is lower risk and
does not perturb a resource-limited routed image.

If the focused AMO test passes, patch OpenSBI's aligned
`_start_hang` window to report `mcause` through host MMIO before changing RTL; this distinguishes a
post-lottery machine-mode trap from an intentional firmware polling loop.

Board automation calls `sudo -n` so it cannot pause invisibly at a password prompt. Use only the
validated fixed-path overlay helper above and the separately scoped `control-program *` rule for
unattended runs. If either rule is absent, run the exact command manually in an authorized board
terminal; never grant passwordless Python, a shell, `make`, or a wildcard executable merely to
bridge per-TTY sudo timestamps.
