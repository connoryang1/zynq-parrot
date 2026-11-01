#!/usr/bin/env python3
"""Extract accepted target L2 requests and target DMA misses from an FST."""

import argparse
import subprocess


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fst")
    ap.add_argument("--target", type=lambda x: int(x, 0), default=0x80008000)
    args = ap.parse_args()
    targets = {args.target + 64 * i for i in range(64)}
    proc = subprocess.Popen(["fst2vcd", "-f", args.fst], stdout=subprocess.PIPE,
                            text=True)
    scopes = []
    names = {}
    for line in proc.stdout:
        if line.startswith("$scope "):
            scopes.append(line.split()[2])
        elif line.startswith("$upscope "):
            scopes.pop()
        elif line.startswith("$var "):
            fields = line.split()
            names[".".join(scopes + [fields[4]])] = fields[3]
        elif line.startswith("$enddefinitions "):
            break

    root = "TOP.bsg_nonsynth_zynq_testbench.dut.top_fpga_inst.blackparrot.processor.u.unicore.slices[0].l2s"
    controller = root + ".cache_controller"
    sig = {
        "clk": names[controller + ".clk_i"],
        "req": names[controller + ".cache_pkt_v_lo"],
        "yumi": names[controller + ".cache_pkt_yumi_li"],
        "addr": names[controller + ".fsm_fwd_addr_li"],
        "bank": names[controller + ".fwd_pkt_bank_lo"],
        "hint": names[controller + ".bank_response.fwd_prefetch"],
    }
    for bank in range(2):
        prefix = root + f".bank[{bank}].cache"
        sig[f"dma{bank}"] = names[prefix + ".dma_pkt_v_o"]
        sig[f"dma_yumi{bank}"] = names[prefix + ".dma_pkt_yumi_i"]
        sig[f"dma_pkt{bank}"] = names[prefix + ".dma_pkt_o"]
    values = {identifier: "0" for identifier in sig.values()}
    current_time = 0
    clock_rise = False
    request_seen = set()
    dma_seen = set()

    def number(name):
        bits = values[sig[name]]
        return int(bits, 2) if all(c in "01" for c in bits) else None

    def process():
        if not clock_rise:
            return
        addr = number("addr")
        if number("req") == 1 and number("yumi") == 1 and addr in targets:
            key = (current_time, addr)
            if key not in request_seen:
                print(f"L2REQ time={current_time} addr={addr:#x} bank={number('bank')} hint={number('hint')}")
                request_seen.add(key)
        for bank in range(2):
            if number(f"dma{bank}") != 1 or number(f"dma_yumi{bank}") != 1:
                continue
            packet = number(f"dma_pkt{bank}")
            if packet is None:
                continue
            write = packet >> 41
            daddr = (packet >> 8) & ((1 << 33) - 1)
            # In this one-CCE, one-slice endpoint, the hash encoder preserves
            # these address bit positions after selecting the bank.
            paddr = daddr
            if paddr in targets:
                key = (current_time, bank, paddr, write)
                if key not in dma_seen:
                    print(f"DMA time={current_time} addr={paddr:#x} bank={bank} write={write}")
                    dma_seen.add(key)

    for line in proc.stdout:
        if line.startswith("#"):
            process()
            current_time = int(line[1:])
            clock_rise = False
        elif line.startswith("b"):
            bits, identifier = line[1:].split()
            if identifier in values:
                values[identifier] = bits
        elif line and line[0] in "01xXzZ":
            identifier = line[1:].strip()
            if identifier in values:
                values[identifier] = line[0]
                if identifier == sig["clk"] and line[0] == "1":
                    clock_rise = True
    process()
    if proc.wait():
        raise SystemExit("fst2vcd failed")


if __name__ == "__main__":
    main()
