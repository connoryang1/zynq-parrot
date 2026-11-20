This review strengthens the baseline collision gate to halfword alignment and binds the old executable image to the exact accepted kernel payload. Raw potential encodings are retained and classified explicitly, including data and reserved SYSTEM patterns.

The archived `oldstripped.elf` hashes to `0792746ba2caf6b2370d923319187f62243c8a0262c876c19a18e2946257d4a3`. Independently running objcopy reproduces old payload `bf0318e848701a99a58a27436861f88d43340245071c036788488e58dcf7be6d` byte-for-byte; disassembly of all its executable sections finds zero CSR `0x5c1` operations. The reconstructed firmware window `0x80000000..0x80200000` also contains zero potential `0x5c1` encodings at every two-byte boundary, including words crossing NBF records. Its nominal-memory SHA-256 is `c7e557599e4b7eebaa33e62fc5b32b6848eee70e47d0b18d66640db99e9ef179`; unwritten bytes are zero-filled, and six final bootarg-string overwrites are retained in the scan metadata.

The full old-kernel byte scan retains three potential encodings, all inside `.init.data` and a CRC-validated gzip CPIO span at offsets `0xc126b0..0xf38d3c`:

| Kernel offset | Word | Classification |
| --- | --- | --- |
| `0xca9eba` | `0x5c16cf73` | Compressed data; funct3=4 is reserved SYSTEM, not a valid CSR operation |
| `0xdf6dca` | `0x5c1ebaf3` | Compressed data; CSR-like bit pattern, outside executable sections |
| `0xea5eb8` | `0x5c1f58f3` | Compressed data; CSR-like bit pattern, outside executable sections |

The raw scan remains available in `baseline-halfword-csr5c1.json`; classification and binding are in `baseline-csr5c1-review.json` and `old-elf-csr5c1.json`. No candidate was silently removed. The new kernel has exactly its two expected executable uses, recorded in `linked-csr5c1.json`; neither this scan nor that disassembly is a runtime old-hardware probe.

The data classification also exposed an image-scope distinction: accepted source `ef50...` contains CPIO SHA-256 `e2f7dbc4d02d0ae99bb66832fe94b4882e19d7c95acd2cc0521299ff6aa73f50` (8,194,560 bytes), while the new linked kernel preserves prepared-SDK CPIO SHA-256 `ac6afe2de4e786e2a63109d5ea0867878d888693c4ac83c244b0a7cbbd5daca0` (8,365,568 bytes). Package metadata now states this scope explicitly. Firmware/collateral and forward/reverse payload checks remain exact, but performance comparisons across the two kernel images cannot isolate retention from kernel/rootfs differences.

The exact old CPIO and its original gzip stream are now retained in external `kernel27/accepted-rootfs.cpio` and `accepted-rootfs.cpio.gz`; `accepted-rootfs-extraction.json` binds their hashes to kernel offsets `0xc126b0..0xf38d3c`. The `ac19...` image remains diagnostic-only while the root agent restores this accepted rootfs in a separate input directory and repeats the kernel link/package gate.
