This directory records a fixed embedded-file transport for repeated failures during console input transfer. It embeds five unchanged workload files into a matched Linux image pair while preserving kernel addresses and the reviewed mode-14 instruction control. A complete physical known-flow gate validates the transport; it establishes a new rootfs baseline without a performance acceptance claim.

The two images are under `/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/embedded-workloads/`:

| Image | SHA-256 |
| --- | --- |
| `linux-prefix32-embedded-baseline-shell.nbf` | `e9aeba407073407cd01f91e2a687c21c4c8a6917b70886d997ce6852270b4508` |
| `linux-prefix32-embedded-control-shell.nbf` | `edd3e71672241c40f1b6ee3f2b4b130367a35e7823cf30dd988d4cff0e1d3bb4` |

The source arms are the exact accepted `ef50...` image and reviewed one-byte `d14...` control. No kernel build occurred. Both new arms replace the same compressed rootfs window at payload offset `0xc126b0`, physical `0x80e126b0`, with exactly 3,303,052 bytes. Gzip9 occupies 3,073,651 bytes and is followed by 229,401 NUL bytes. CRC32 `0x87a86df7`, ISIZE 7,699,828, gzip decompression and exact trailing-NUL consumption all pass. The new CPIO hashes to `2c2947254da730b962b17ba043f53eef279d1b232b1fb659669e46a6b284e9d7`; the padded gzip hashes to `f1b4b240e06ffc5fb5387d775c4dca207abab79683a45d1794600da6b8258aa7`, reproducing the earlier feasibility result.

Only the obsolete regular, single-link `usr/bin/ctxtsw_user_smoke` is replaced among the original 419 CPIO members. Its exact old body is verified by SHA-256; its new body is `#!/bin/sh\nexit 1\n`. Only that member's filesize, body and body padding change. All other original member records, fields, body bytes, order and original archive padding remain exact. The appended deterministic newc archive adds `opt/bp-resume` and these unchanged files; the existing `opt` directory retains its original metadata:

| Embedded path under `/opt/bp-resume/` | SHA-256 |
| --- | --- |
| `plain` | `e943befa9eed8b9a4258c88c5c822745017c42ef1d5af9f3bc07c56a0eade86a` |
| `plain_resources` | `ce0a21a67a36f522c46c590cf790b18bc535f09b85e8d8f20fd36e9a591cec70` |
| `probe` | `8f8887579c81e4633ebe445ada38ab7311aae58c21656f4b98a38bbc6ac0c9a2` |
| `zlib` | `407fd9ec2edb0e67cce2e3b7c7049cc3cfa85809189619d99d13dabc51574308` |
| `libz.so.1` | `e2c082d208dc2c6041fdef01579e1e86a441bb0dbc930e13fe8e2eee9eedc63b` |

Host GNU cpio independently extracts all five appendix files to stdout and reproduces their exact bytes. The strict newc parser verifies parent directories and deterministic uid/gid, mode, nlink and mtime. The earlier feasibility parser independently verifies preservation of the original members. The archive remains restricted to the accepted interactive `rdinit=/bin/sh` workflow; replacing the obsolete executable intentionally invalidates the legacy `/sbin/init` auto-smoke workflow. The original CPIO, gzip, workload files and accepted images remain untouched. Embedding the probe does not add its required kernel ABI to these old kernels, and no probe execution is implied.

Each modified ELF preserves all executable sections byte-for-byte relative to its source arm. Objcopy reconstructs the exact corresponding new payload. Every payload byte outside the gzip span remains exact, including the four outside bytes in the final partially overlapping NBF word. All ordered nonkernel NBF records remain unchanged; per-arm reverse splices reproduce the exact original NBFs, and independent extraction reconstructs each new payload. Comparing the new arms still finds exactly one changed payload byte at `0x813fe8` (`0x1d`→`0x21`), one changed ELF byte at `0x814fe8`, and the sole reviewed mode-14 NBF record. Decoding all 256 modes changes only mode 14. No optional retention-kernel image was created.

Primary Linux 6.6 source snapshots under the external `linux-source-proof/` retain the evidence for concatenated newc records, gzip termination, NUL padding, streaming decompression, compressed `__initramfs_size` and direct rdinit execution. Their recorded source hashes remain unchanged. `manifest.json` binds archive preservation, exact payloads, both arm conversions, executable-section hashes, reverse/extraction checks, source snapshots and the full pair difference. `verification.json` independently rechecks those artifacts and records PASS. `build.log`, `verify.log`, `host-tests.log` and `comparator-tests.log` retain the closed offline checks.

The dedicated comparator now accepts the fixed selector `--image-pair embedded`, with pinned image, manifest and verification hashes. Its default remains `original`; no arbitrary image/manifest override is available. It rejects mixing either embedded arm with original-rootfs logs. Both selected arms still require identical ELF, transfer, bitstream and complete configuration, at least two complete independent boots each, WHOLE/resource rows and all terminal/drain gates. Whole-cell paired benefit is primary, with steady transaction effects secondary. Existing policy/route comparators and host runners are unchanged.

Future board results must compare the two embedded arms with one exact workload ELF and transfer identity. They cannot be pooled with measurements from the original `e2f7...` rootfs: changing the archive changes boot/allocation state even though kernel instruction addresses remain fixed. The separately implemented embedded-copy transport and its runtime gates belong to the root agent.

## Physical transport gate

`transport-regression.json` binds session14's complete known `e943...` scan workload, embedded baseline, mandatory copied-ELF hash, independent checks, normal shell return, CORE/BSG PASS and runner zero exit. The fixed namespace protocol is a three-line declaration/copy/chmod sequence; its header alone does not prove embedded bytes. Runtime SHA verification is mandatory before execution, including the separately declared library when present. Thirteen new host tests include wrong ELF/library hash failures that never execute the application; 47 focused transport/runner/session tests pass.

Session14 used the older 64 MiB guest declaration with a 46 MiB host allocation. It is a transport gate with this ownership limitation, not a timing result. The separately recorded `../embedded46-20261120/physical-bounds-gate.json` closes the actual memory-bounds gate for a new matched image pair. The legacy resource ELF embedded here also has the policy-scope limitation documented in `../complete-policy-scope-20261120/`; its WHOLE rows cannot support a causal complete-cell comparison.
