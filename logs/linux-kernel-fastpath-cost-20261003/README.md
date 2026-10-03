# Linux kernel fast-path floor

This experiment separates privilege-entry and futex bookkeeping from actual Linux thread selection on the exact qualified PYNQ-Z2 image. A 5,848-byte no-libc RV64 binary directly executes each `ecall`, measures cycles and retired instructions, rotates path order, warms 64 iterations, and reports 512 samples per path. The exact ELF SHA-256 is `8c7dd9b998fa319f3f1441880052342c4ee24ceb0bec81c4e2d063a8db659ce6`.

| Path | Median cycles | Median instructions | Net cycles | Net instructions |
| --- | ---: | ---: | ---: | ---: |
| Empty measurement envelope | 8 | 5 | 0 | 0 |
| `gettid` | 620 | 249 | 612 | 244 |
| `FUTEX_WAKE_PRIVATE`, no waiter | 1,009 | 495 | 1,001 | 490 |
| `FUTEX_WAIT_PRIVATE`, mismatched value (`EAGAIN`) | 1,761 | 800 | 1,753 | 795 |
| `sched_yield`, no user peer | 3,473 | 1,505 | 3,465 | 1,500 |

The minimal measured privilege round trip alone is 55.0x the 11.12-cycle resident ready-bitmap handoff and 40.4x the 15.13-cycle nonresident form. Futex bookkeeping without waking or blocking anyone is already 90.0x/66.2x, while checking a futex value and returning immediately is 157.6x/115.9x. Therefore a specialized Linux group-handoff syscall could plausibly reduce the current roughly 5,500-cycle hot scheduler handoff into the high hundreds or low thousands, but it cannot reach the hardware path while retaining ordinary trap entry, kernel validation, and return.

The accepted run used bitstream SHA-256 `3c5b4ccfae4833b7210ebef2466c189419a732ea610bcd9c53914622cd970eec` and Linux NBF SHA-256 `af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3`. It passed guest ELF verification, all syscall-result checks, native exit zero, `CORE[0] PASS`, and runner exit zero. The first libc-linked transfer attempt was stopped before execution after the board watchdog expired; no result from that attempt is used.
