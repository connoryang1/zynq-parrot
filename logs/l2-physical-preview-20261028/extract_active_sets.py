#!/usr/bin/env python3
"""List L2 bank set indices reached by accepted DRAM cache operations in an FST."""

import argparse
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fst")
    args = parser.parse_args()
    root = ("TOP.bsg_nonsynth_zynq_testbench.dut.top_fpga_inst."
            "blackparrot.processor.u.unicore.slices[0].l2s.")
    wanted = {}
    for bank in range(2):
        prefix = root + f"bank[{bank}].cache."
        for signal in ("clk_i", "v_i", "yumi_o", "addr_index", "cache_pkt.addr"):
            wanted[prefix + signal] = None

    proc = subprocess.Popen(["fst2vcd", "-f", args.fst],
                            stdout=subprocess.PIPE, text=True)
    scopes = []
    for line in proc.stdout:
        if line.startswith("$scope "):
            scopes.append(line.split()[2])
        elif line.startswith("$upscope "):
            scopes.pop()
        elif line.startswith("$var "):
            fields = line.split()
            name = ".".join(scopes + [fields[4]])
            if name in wanted:
                wanted[name] = fields[3]
        elif line.startswith("$enddefinitions "):
            break
    missing = [name for name, ident in wanted.items() if ident is None]
    if missing:
        proc.kill()
        raise SystemExit("missing waveform signals: " + ", ".join(missing))

    values = {ident: "x" for ident in wanted.values()}
    active_sets = [set(), set()]
    clock_id = wanted[root + "bank[0].cache.clk_i"]
    rising = False

    def value(name):
        bits = values[wanted[name]]
        return int(bits, 2) if all(bit in "01" for bit in bits) else None

    def sample():
        if not rising:
            return
        for bank in range(2):
            prefix = root + f"bank[{bank}].cache."
            if value(prefix + "v_i") != 1 or value(prefix + "yumi_o") != 1:
                continue
            addr = value(prefix + "cache_pkt.addr")
            if addr is not None and addr >= 0x80000000:
                active_sets[bank].add(value(prefix + "addr_index"))

    for line in proc.stdout:
        if line.startswith("#"):
            sample()
            rising = False
        elif line.startswith("b"):
            bits, ident = line[1:].split()
            if ident in values:
                values[ident] = bits
        elif line and line[0] in "01xXzZ":
            ident = line[1:].strip()
            if ident in values:
                values[ident] = line[0]
                if ident == clock_id and line[0] == "1":
                    rising = True
    sample()
    if proc.wait():
        raise SystemExit("fst2vcd failed")
    for bank, indices in enumerate(active_sets):
        print(f"bank={bank} active_dram_sets={sorted(indices)}")


if __name__ == "__main__":
    main()
