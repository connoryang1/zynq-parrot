#!/usr/bin/env python3
"""Count D-cache preview handshakes at the UCE clock in a closed FST trace."""
import json
import subprocess
import sys


def analyze(path):
    process = subprocess.Popen(["fst2vcd", "-f", path], stdout=subprocess.PIPE,
                               text=True, bufsize=1024 * 1024)
    prefix = "TOP.bsg_nonsynth_zynq_testbench.dut.top_fpga_inst.blackparrot"
    wanted = {
        "clk": prefix + ".dcache_uce.clk_i",
        "preview_req": prefix + ".dcache_preview_req",
        "preview_accept": prefix + ".dcache_preview_accept",
        "normal_accept": prefix + ".dcache_normal_req_accept",
        "metadata": prefix + ".dcache_uce_metadata_v",
        "enqueue": prefix + ".dcache_uce.preview_enqueue",
        "dequeue": prefix + ".dcache_uce.preview_dequeue",
        "queued": prefix + ".dcache_uce.preview_count_r",
        "issue": prefix + ".dcache_uce.prefetch_issue",
        "response": prefix + ".dcache_uce.prefetch_response_yumi",
    }
    scope, ids = [], {}
    for line in process.stdout:
        if line.startswith("$scope "):
            scope.append(line.split()[2])
        elif line.startswith("$upscope "):
            scope.pop()
        elif line.startswith("$var "):
            fields = line.split()
            full = ".".join(scope) + "." + fields[4]
            if full in wanted.values():
                ids[full] = fields[3]
        elif line.startswith("$enddefinitions"):
            break
    missing = set(wanted.values()) - set(ids)
    if missing:
        process.terminate()
        raise RuntimeError("missing trace signals: " + ", ".join(sorted(missing)))
    by_name = {name: ids[full] for name, full in wanted.items()}
    by_id = {identifier for identifier in by_name.values()}
    values = {}
    counts = {name: 0 for name in wanted if name not in ("clk", "queued")}
    samples = []
    max_queued = 0
    timestamp = None
    clock_rise = False

    def sample():
        nonlocal max_queued
        if not clock_rise or timestamp == 0:
            return
        active = []
        for name in counts:
            if values.get(by_name[name]) == "1":
                counts[name] += 1
                active.append(name)
        queue_bits = values.get(by_name["queued"], "0")
        if set(queue_bits) <= {"0", "1"}:
            max_queued = max(max_queued, int(queue_bits, 2))
        if active and len(samples) < 24:
            samples.append({"time_ps": timestamp, "signals": active})

    for line in process.stdout:
        if line.startswith("#"):
            sample()
            timestamp = int(line[1:])
            clock_rise = False
        elif line and line[0] in "01xz":
            identifier, value = line[1:].strip(), line[0]
            if identifier in by_id:
                if identifier == by_name["clk"] and value == "1" and values.get(identifier) != "1":
                    clock_rise = True
                values[identifier] = value
        elif line.startswith("b"):
            fields = line.split()
            if len(fields) == 2 and fields[1] in by_id:
                values[fields[1]] = fields[0][1:]
    sample()
    if process.wait() != 0:
        raise RuntimeError("fst2vcd failed")
    return {"fst": path, "sample_clock": wanted["clk"], "counts": counts,
            "max_queued": max_queued, "first_events": samples}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: analyze_adapter_wave.py TRACE.fst")
    print(json.dumps(analyze(sys.argv[1]), indent=2))
