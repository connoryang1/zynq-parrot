# Linux CTZ FPGA probe

This no-libc Linux probe isolates the corrected Zbb `ctz` datapath from context switching. It executes adjacent `ld; ctz; sd` sequences for zero, bits 0/1/2/9/31/32/63, checks the architectural results, exits zero, and powers off through the accepted interactive runner.

The exact routed image is top `4f160861d1391826b0ce3185b7450209e927ab34`, BlackParrot `5273cfd57e2ac5e012bb7905b3594b5868f24b94`, and bitstream SHA-256 `3c5b4ccfae4833b7210ebef2466c189419a732ea610bcd9c53914622cd970eec`. The ELF SHA-256 is `f55d7619e0a2653ab40078ab0288104b809dbbe0f74a928109c9b1aa1f87301f`.

The board run passed all eight values, the guest ELF hash, native exit zero, `CORE[0] PASS`, and runner exit zero. This proves the CTZ arithmetic and its immediate load dependency on FPGA. It does not prove that an immediately following early context-switch CSR sees the result; the ready-selection experiment isolates that separate dependency.
