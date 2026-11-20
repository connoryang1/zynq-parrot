This study isolates the extra scheduler-selection trigger unintentionally retained by historical Linux mode 14. It prepares a single-instruction control from the exact accepted old image and separately corrects the maintained source patch stack. Complete short FPGA runs confirm the trigger difference; execution-speed improvement remains unaccepted.

The exact accepted old ELF `0792746b...d4a3` converts to payload `bf0318e8...be6d`, matching source NBF `ef50be19...1cf4`. Its mode-14 futex-entry trigger is at virtual address `ffffffff8009848e`. The late selection path also admits mode 14: it subtracts six, truncates to a byte, and skips the trigger only when that result is at most seven. Mode 14 produces eight and reaches `csrw 0x5c0,zero` at `ffffffff80813fee`. The TTWU mode dispatch separately excludes mode 14. Mode zero bypasses the selection block; this defect does not explain failures before any task is armed.

The causal control changes compressed `li a4,7` to `li a4,8` at virtual `ffffffff80813fe8`, physical `0x80a13fe8`, payload offset `0x813fe8`, ELF offset `0x814fe8`. The two-byte instruction changes from `1d47` to `2147`; exactly one byte differs across each complete binary and ELF. Both paths join at `ffffffff80813e04`, where `ld a4,112(s3)` overwrites the bound before another use. None of the 143 exact-old `.alternative` records overlaps the instruction. Decoding the actual branch/constant skeleton and evaluating all 256 byte-valued modes changes only mode 14: the old predicate admits modes 2, 3, 5 and 14–255; the control admits 2, 3, 5 and 15–255.

| Artifact | SHA-256 |
| --- | --- |
| Original accepted NBF | `ef50be197b458b512f82ed8a9deccc0bdfcfadba760ccd119d67e46837501cf4` |
| New early-only control NBF | `d14dc8b00908bb7c7a310d4c517f31752a9db4f5836b5d60b5d916d596a7847b` |
| Original payload | `bf0318e848701a99a58a27436861f88d43340245071c036788488e58dcf7be6d` |
| New control payload | `f5744fc63c6bcca79c6252dbae0fa9462cd49fd06fe797c2431ee40c82bea481` |

The new image is `/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/mode14-early-only-control/linux-prefix32-mode14-early-only-shell.nbf`. Its sole changed record is line 1,075,385:

```text
old: 03_0000000080a13fe8_1073e0f77de3471d
new: 03_0000000080a13fe8_1073e0f77de34721
```

Two ASCII hex digits encode that one changed payload byte. Every other NBF byte is preserved, and reverse patching reproduces the original NBF byte for byte. Objcopy of the modified ELF and extraction of the candidate NBF independently reproduce the same 24,034,304-byte control payload. The accepted compressed rootfs remains byte-identical at offset `0xc126b0`; code addresses, other kernel bytes, firmware and prefix-table contents do not move. `manifest.json`, `verification.json`, the 256-mode proof and old/control predicate/join disassembly are retained locally or in the external control directory. The original accepted artifacts remain untouched.

Source patch 0028 adds `bp_preview_mode != 14` to selection replay. The maintained Makefile stages 0026→0027→0028 or upgrades complete 0027→0028, recognizes the complete stack idempotently, and rejects partial retention or out-of-order tails. That source stack includes the newer retention ABI; it is deliberately distinct from this exact-old binary control, which introduces no CSR `0x5c1` ABI. Tests apply/reverse real copied Linux files and compile the source predicate for all 256 modes. The first patch hunk failed the strict zero-fuzz test; adding complete trailing context fixed it, and no failed result was accepted or canonical source modified.

The analyzer now uses actual unsaturated sweep accounting: processed entries equal observed triggers times configured entries, and resident drops equal processed entries minus admissions, subject to saturation. Known early-wake calls supply a lower bound rather than an exact total; extra selections depend on the kernel and schedule. Saturated historical complete runs retain their measured gains. Their mechanism is early-entry plus scheduler-selection replay, and excluding internal wake callers at the dispatcher did not remove the selection trigger. For example, four repeats of 64 loops plus 32 warmups and terminal release already imply 388 early wake calls, exceeding the 255-trigger ceiling before any selection triggers are added.

A distinct `pipe-hint-benchmark-plain-resources-dynamic` target also builds resource and whole-cell timing without zlib or the retention ABI. Its compressed-transfer target is `emit-pipe-hint-benchmark-plain-resources-compressed-transfer`. The existing six ELF recipes are unchanged; the root agent owns cross-compilation and artifact identity validation. No benchmark C or frozen session-runner source changed for this addition.

`host-tests.log` records the focused patch, analyzer, policy/route comparator, retention and resource-accounting tests. The next causal measurement must compare complete execution of the original and control images with the same ELF, workload, footprint, loop/warmup counts and terminal protocol across recovered boot strata; a faster metadata sweep or an isolated local endpoint is insufficient.

Two separately reserved, hard-recovered FPGA boots close the first mechanism gate. Both use the accepted f091 bitstream, exact e943 ELF and gzip-transfer identity, scan with 32 KiB per process, 8 timed loops, 4 warmups and 2 paired repeats. The only image difference is the reviewed instruction byte. Each verifies the guest ELF, completes independent checks, returns to the shell and reaches CORE/BSG PASS with runner exit zero.

| Image / session | Accepted triggers | Admitted lines | Dropped triggers |
| --- | ---: | ---: | ---: |
| Accepted old ef50 / 11 | 93 | 160 | 0 |
| Early-only d14 / 10 | 26 | 64 | 0 |

The 26 early-only triggers equal the 26 known parent wake calls. The old image's 67 additional triggers agree with its proven selection path. These counters cover setup, warmup, timing and teardown together; they do not locate those extra triggers inside the timed interval, price their execution cost, identify unique retained capacity, or establish 93 as a general scheduling frequency. Resident drops saturate at 511 in both runs. `physical-counter-gate.json` binds raw logs, runner statuses, reservation/release manifests, configurations and unsaturated counter values. These short plain-ELF runs have no WHOLE/resource rows and are ineligible for the dedicated whole-cell performance comparator.
