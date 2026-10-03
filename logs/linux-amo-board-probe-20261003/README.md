This probe checks whether a Linux U-mode `AMOSWAP` result can feed `ctz` without a software bubble on the qualified old FPGA image. It is a dependency control, not a context-switch benchmark.

The exact ELF SHA-256 is `4d9727ce8d9c4fb4c4af0bedc603981b4be28870c74aee41bbf0696ca87d6b85`. All five adjacent sequences with zero through four NOPs returned the old word `2`, produced `ctz(2) = 1`, left the word at `1`, and passed guest hash, native exit, and `CORE[0] PASS` checks. Therefore the AMO-to-integer dependency alone does not require a bubble.

The run used bitstream SHA-256 `3c5b4ccfae4833b7210ebef2466c189419a732ea610bcd9c53914622cd970eec` and Linux NBF SHA-256 `af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3`.
