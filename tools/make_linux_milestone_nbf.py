#!/usr/bin/env python3
"""Create a one-shot, host-visible Linux reachability probe NBF.

The probe overwrites a small instruction window at a *physical* Linux PC with
an existing BlackParrot host-MMIO sequence.  If that PC is reached, the host
prints ``M<marker>`` and receives a successful finish packet.  This is intended
for binary-searching a silent early-Linux stall without rebuilding Linux or
changing RTL; it is not a performance test and must never be used as one.

The NBF loader has a known unsafe byte/halfword write path.  Like
patch_nbf_bytes.py, this utility reconstructs and emits only aligned 8-byte
writes for the modified instruction blocks.
"""

from __future__ import annotations

import argparse
from pathlib import Path


WIDTHS = {0: 1, 1: 2, 2: 4, 3: 8}
UNFREEZE = "02_0000000000200008_0000000000000000"
HOST_PUTC = 0x0010_1000
HOST_FINISH = 0x0010_2000
MARKER_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def parse_line(line: str) -> tuple[int, int, int]:
    fields = line.strip().split("_")
    if len(fields) != 3:
        raise ValueError(f"malformed NBF line: {line.rstrip()}")
    return tuple(int(field, 16) for field in fields)


def lui(rd: int, value: int) -> int:
    if value & 0xFFF:
        raise ValueError(f"lui value must be 4 KiB aligned: 0x{value:x}")
    return (value & 0xFFFFF000) | (rd << 7) | 0x37


def addi(rd: int, rs1: int, imm: int) -> int:
    if not -2048 <= imm <= 2047:
        raise ValueError(f"addi immediate out of range: {imm}")
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (rd << 7) | 0x13


def sw(rs2: int, rs1: int, imm: int = 0) -> int:
    if not -2048 <= imm <= 2047:
        raise ValueError(f"sw immediate out of range: {imm}")
    immediate = imm & 0xFFF
    return (
        ((immediate >> 5) << 25)
        | (rs2 << 20)
        | (rs1 << 15)
        | (0b010 << 12)
        | ((immediate & 0x1F) << 7)
        | 0x23
    )


def sltu(rd: int, rs1: int, rs2: int) -> int:
    return (rs2 << 20) | (rs1 << 15) | (0b011 << 12) | (rd << 7) | 0x33


def probe_words(
    marker: int, disable_satp: bool, report_nonzero_reg: int | None
) -> list[int]:
    """Emit ``M<marker>`` through long-standing host channels, then finish."""
    # t0=x5, t1=x6.  marker is deliberately limited to ADDI's immediate so
    # the probe remains compact and its complete effect is obvious in a dump.
    prefix = [0x18001073, 0x12000073] if disable_satp else []
    report = []
    if report_nonzero_reg is not None:
        # Print V0 or V1 without changing the reported register.  This is
        # intentionally just a predicate: it remains safe at a marker site
        # with minimal register liveness assumptions and is enough to compare
        # control-flow selectors between FPGA images.
        report = [
            lui(5, HOST_PUTC),
            addi(6, 0, ord("V")),
            sw(6, 5),
            sltu(6, 0, report_nonzero_reg),
            addi(6, 6, ord("0")),
            sw(6, 5),
        ]
    return prefix + report + [
        # Do not use the newer signature or integer-print channels here.
        # Several archived PYNQ runners predate them, whereas putc exists in
        # every runner that can boot the shipped Linux image.  The two printable
        # bytes form a self-identifying marker in board transcripts.
        lui(5, HOST_PUTC),
        addi(6, 0, ord("M")),
        sw(6, 5),
        addi(6, 0, ord(MARKER_DIGITS[marker])),
        sw(6, 5),
        lui(5, HOST_FINISH),
        sw(0, 5),
        0x0000006F,  # jal x0, 0: a safe fallback if the host has not stopped us
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="original Linux NBF")
    parser.add_argument("output", type=Path, help="probe NBF to create")
    parser.add_argument(
        "--pc", required=True, type=lambda text: int(text, 0),
        help="physical PC at which to stop (for example 0x80200000)",
    )
    parser.add_argument(
        "--marker", required=True, type=lambda text: int(text, 0),
        help="numeric host marker, 0 through 35 (printed as M0 through Mz)",
    )
    parser.add_argument(
        "--expect-first-word", type=lambda text: int(text, 0),
        help="optional guard: refuse if the original instruction differs",
    )
    parser.add_argument(
        "--disable-satp", action="store_true",
        help="clear SATP and flush translations before reporting (post-MMU probes only)",
    )
    parser.add_argument(
        "--report-nonzero-reg", type=int,
        help="print V0/V1 for whether this integer register (0 through 31) is nonzero",
    )
    args = parser.parse_args()

    if not 0 <= args.marker < len(MARKER_DIGITS):
        parser.error(f"--marker must be in 0..{len(MARKER_DIGITS) - 1}")
    if args.report_nonzero_reg is not None and not 0 <= args.report_nonzero_reg < 32:
        parser.error("--report-nonzero-reg must be in 0..31")
    # Linux's handoff path uses compressed instructions.  IALIGN is therefore
    # 16 bits: an instruction can legitimately begin at address 2 mod 4 even
    # when the replacement instructions themselves are standard 32-bit words.
    if args.pc & 0x1:
        parser.error("--pc must be 2-byte instruction aligned")

    data = b"".join(
        word.to_bytes(4, "little")
        for word in probe_words(
            args.marker, args.disable_satp, args.report_nonzero_reg
        )
    )
    start = args.pc & ~0x7
    end = (args.pc + len(data) + 7) & ~0x7
    blocks = {address: bytearray(8) for address in range(start, end, 8)}
    covered = {address: [False] * 8 for address in blocks}

    lines = args.source.read_text(encoding="ascii").splitlines(keepends=True)
    saw_memory_write = False
    for line in lines:
        command, address, encoded_data = parse_line(line)
        if command not in WIDTHS:
            continue
        saw_memory_write = True
        encoded = encoded_data.to_bytes(WIDTHS[command], "little")
        for offset, byte in enumerate(encoded):
            byte_address = address + offset
            block_address = byte_address & ~0x7
            if block_address in blocks:
                index = byte_address - block_address
                blocks[block_address][index] = byte
                covered[block_address][index] = True

    if not saw_memory_write:
        parser.error("source contains no memory writes")
    if not all(all(mask) for mask in covered.values()):
        missing = [
            f"0x{block + offset:x}"
            for block, mask in covered.items()
            for offset, exists in enumerate(mask)
            if not exists
        ]
        parser.error("probe window is not fully backed by source NBF: " + ", ".join(missing))

    # A valid 32-bit instruction may start at either halfword within an
    # aligned NBF block.  In particular, an instruction at offset six spans
    # two 8-byte writes.  Assemble the guard word bytewise rather than using
    # one block slice, which would silently compare only two bytes there.
    original_first = int.from_bytes(
        bytes(
            blocks[(args.pc + offset) & ~0x7][(args.pc + offset) & 0x7]
            for offset in range(4)
        ),
        "little",
    )
    if args.expect_first_word is not None and original_first != args.expect_first_word:
        parser.error(
            f"first word mismatch at 0x{args.pc:x}: "
            f"got 0x{original_first:08x}, expected 0x{args.expect_first_word:08x}"
        )

    for offset, byte in enumerate(data):
        byte_address = args.pc + offset
        block_address = byte_address & ~0x7
        blocks[block_address][byte_address - block_address] = byte

    writes = [
        f"03_{address:016x}_{int.from_bytes(blocks[address], 'little'):016x}\n"
        for address in sorted(blocks)
    ]
    unfreeze_indices = [index for index, line in enumerate(lines) if line.strip() == UNFREEZE]
    if not unfreeze_indices:
        parser.error("source contains no recognized unfreeze command")
    insert = unfreeze_indices[-1]
    args.output.write_text("".join(lines[:insert] + writes + lines[insert:]), encoding="ascii")

    print(f"pc=0x{args.pc:x} original_first_word=0x{original_first:08x}")
    print(
        f"marker={args.marker} disable_satp={int(args.disable_satp)} "
        f"report_nonzero_reg={args.report_nonzero_reg} "
        f"overwritten_bytes={len(data)} aligned_writes={len(writes)}"
    )
    print(
        "expected host output: M"
        f"{MARKER_DIGITS[args.marker]} immediately before CORE PASS"
    )


if __name__ == "__main__":
    main()
