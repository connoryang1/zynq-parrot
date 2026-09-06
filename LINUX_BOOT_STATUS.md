This file records the accepted FPGA Linux boot and context-switch demonstration. It identifies the exact hardware and software artifacts, explains the boot stages, and separates acceptance from broader untested claims.

# Linux boot status

This is the living, plain-language status record for booting Linux on the
PYNQ-Z2 BlackParrot image.  Update it whenever a boot-stage result changes.
The payload is a single NBF image: it loads OpenSBI in M-mode, which starts
the Linux kernel in S-mode; Linux then starts the root filesystem's `/init`.

Status labels: **pre-existing** means it was known to work before this
context-switch work; **fixed here** names a repair authored during this work;
**accepted** means the exact repaired image has passed on the FPGA.

## Boot path and status

| Step | What happens | Status |
| --- | --- | --- |
| 1 | The ARM host resets the PYNQ programmable logic and loads the BlackParrot bitstream. | **Pre-existing:** working. |
| 2 | The host allocates/zeros 64 MiB of board DRAM and loads the Linux NBF into it. | **Pre-existing:** working. |
| 3 | The host releases BlackParrot reset; its boot ROM enters the NBF-provided OpenSBI firmware in machine mode (M-mode). | **Pre-existing:** working. |
| 4 | OpenSBI initializes machine CSRs, timer/interrupt delegation, PMP, and its trap path. | **Accepted:** the repaired routed image prints the complete OpenSBI v1.4 banner and capability report without temporary-trap failure. |
| 5 | OpenSBI executes `mret`, transferring to the Linux kernel in supervisor mode (S-mode). | **Accepted:** the repaired routed image enters Linux and prints its normal kernel banner. |
| 6 | Linux performs early CPU, page-table, and trap initialization. | **Accepted:** the repaired routed image completes this stage and prints the normal Linux boot log. |
| 7 | Linux allocates its DMA pools and continues device/kernel initialization. | **Accepted:** the repaired routed image completes all kernel initialization through the initramfs handoff. |
| 8 | Linux runs architecture capability probes, including unaligned-access checks. | **Accepted:** the repaired routed image completes these probes and frees the unused kernel image. |
| 9 | Linux mounts the bundled initramfs and executes the selected init program. | **Accepted:** Linux runs `/ctxtsw_user_tiny`; the U-mode C program switches 0→2→0, executes a Linux `write` syscall from context 2, verifies logical ID and independent/restored `s11`, prints PASS, powers off, and returns `CORE[0] PASS`. |

## Accepted repaired checkpoint (2026-09-06)

The accepted bitstream uses top-level RTL `032420c33624d08df2a5852da9d0c49394fa1cef`
and BlackParrot `25089713baa090aba719ec0f18f82ff9214d5f0d`. It routed for the
static two-resident/four-logical PYNQ-Z2 configuration at 46,851 LUTs
(88.07%), 80 BRAM tiles (57.14%), 11 DSPs, WNS +1.781 ns, and TNS 0. The
package SHA-256 is `ffbb0142dcac50ff2d3406cc0d56a85cd4bf6457c2e7506f599f408160d998c9`
and the extracted bitstream SHA-256 is
`9ce659b764213adbf7ca1b347b8c43e4a58c6661e092a35b12ca1ceb9a3b9824`.

The translated bare-metal handoff NBF
(`6cbee152430e0aa5ec471664cf8e1874487d166a459fcce69c38c8082e69bb01`)
passed first. The freshly validated Linux PID-1 image
(`0728cd34650d49c4fe38522d6e139befb51732b426be1b1d1eec11d3ced36959`)
then booted through
OpenSBI and Linux, reached the context-switch program, printed its target and
PASS markers, and ended cleanly. Finally, the physical global-cycle benchmark
(`da85ec1f46c8217241adacb0b8c801bef65968db2c6f25d09bfca8fd337152f2`)
measured 5.10 resident and 11.12 nonresident cycles/switch;
the waveform-derived architectural handoff remains 11--12 cycles before any
separate cold translation/refill tail.

This is a PID-1 application demonstration, not an interactive-shell or general Linux scheduler acceptance test. Complete nonresident floating-point preservation is excluded from the accepted FPGA endpoint. Current source location is recorded in [CURRENT_CHECKOUT.md](CURRENT_CHECKOUT.md); earlier boot failures and fixes are retained at [the historical checkpoint](HISTORY.md).
