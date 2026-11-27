# Linux replay footprint patch (draft 0031)

This directory holds a draft kernel patch that lets Linux drive the address
record/replay hardware with a realistic footprint. It applies on top of the
accepted 0027+0029+0030 kernel line (0030 = kernel-gated capture) (`/home/coyang/kernel29-kgate-20261124/linux-6.6`)
and has been compile-checked only; it has not been booted.

## What it adds

- `PR_BP_REPLAY_FOOTPRINT` (0x42505066): a task hands the kernel up to 256
  line addresses. The kernel pins the pages, translates them, and programs one
  hardware data slot (0x9c1/0x9c2, wide index/count encoding). Flag bit 0
  prepends 12 lines of the task's own kernel switch state (4 at the top of the
  kernel stack, 8 at the head of `task_struct`). Pins are released on
  reconfiguration, `PR_BP_PREVIEW_PIN_SET`, exec, exit and task free (all
  through `riscv_bp_preview_release`, which first drains queued replay).
- Mode 16 (`PR_BP_PREVIEW_ENABLE`): triggers the firmware code prefix
  (0x5c0) and the task's data slot (0x9c3) at `context_switch` to the task.
  This is the end-of-turn point. The existing mode 10 triggers the same two
  lanes at wakeup (`try_to_wake_up`), the earlier point. The two modes differ
  only in when the trigger fires.

Code lines come from the boot-time firmware table (`icache_prefix.h` in the
OpenSBI platform): earlier traces put 98.5% of Linux switch-path instruction
misses in kernel or OpenSBI text, so no per-task code list is needed yet.

## Usage sketch

    prctl(PR_BP_REPLAY_FOOTPRINT, slot, lines, n_lines, PR_BP_REPLAY_FP_KERNEL);
    prctl(PR_BP_PREVIEW_ENABLE, 10 /* wake */ or 16 /* end of turn */, 0, 0, 0);

## Limits

- One possible CPU only (table and drain are CPU-local), as for 0029.
- The footprint is an oracle list supplied by the program; hardware recording
  (step 3) would replace it.
- Not yet built into an NBF or booted; the replay hardware itself still has
  an open line-corruption bug with hold enabled (see WORK_LOG).
