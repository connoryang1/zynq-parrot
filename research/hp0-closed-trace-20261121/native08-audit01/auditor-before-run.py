#!/usr/bin/env python3
"""Audit one closed HP0 FST through selected FSTAPI signals; no target execution."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
import subprocess
import tempfile
import threading

import audit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
READER_DIR = HERE.with_name("retained-advisory-trace")


def binding(path):
    path = Path(path).resolve()
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""): h.update(b)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=h.hexdigest())


def read_text(path):
    return gzip.open(path, "rt").read() if Path(path).suffix == ".gz" else Path(path).read_text()


def selections(delay, uce):
    base = "top_fpga_inst."
    result = {"clk": (base + "aclk", 1), "resetn": (base + "aresetn", 1)}
    widths = dict(id=6, addr=32, len=8, size=3, burst=2, lock=1, cache=4, prot=3, qos=4)
    for channel in ("ar", "aw"):
        for field, width in dict(widths, valid=1, ready=1).items():
            result[channel + field] = (base + "hp0_axi_" + channel + field, width)
    for field, width in dict(valid=1, ready=1, id=6, data=64, strb=8, last=1).items():
        result["w" + field] = (base + "hp0_axi_w" + field, width)
    for field, width in dict(rvalid=1, rready=1, rid=6, rdata=64, rresp=2, rlast=1,
                             bvalid=1, bready=1, bid=6, bresp=2).items():
        result["ext." + field] = (base + "hp0_axi_" + field, width)
        direction = "o" if field.endswith("ready") else "i"
        result["core." + field] = (base + "blackparrot.m_axi_" + field + "_" + direction, width)
    if delay:
        for key, signal, width in (("delay", "active_delay", 9), ("cycle", "cycle_count", 32)):
            result["shim." + key] = (base + "hp0_delayed_response." + signal, width)
        for channel in ("r", "b"):
            for key, signal, width in (("occupancy", "occupancy", 10), ("full", "full", 1),
                                       ("full_stalls", "full_stall_cycles", 32)):
                result["shim." + channel + "." + key] = (
                    base + "hp0_delayed_response." + channel + "_" + signal, width)
    if uce:
        for lane in ("i", "d"):
            prefix = "unicore_lite." + lane + "cache_uce."
            signals = (("clk", "clk_i", 1), ("reset", "reset_i", 1),
                ("reqv", "cache_req_v_i", 1), ("reqy", "cache_req_yumi_o", 1),
                ("reqaddr", "cache_req_cast_i.addr", 34), ("reqtype", "cache_req_cast_i.msg_type", 4),
                ("datav", "data_mem_pkt_v_o", 1), ("datay", "data_mem_pkt_yumi_i", 1),
                ("dataaddr", "data_mem_pkt_cast_o.addr", 34), ("opcode", "data_mem_pkt_cast_o.opcode", 2),
                ("fill", "data_mem_pkt_cast_o.fill_index", 8), ("last", "cache_req_last_o", 1),
                ("state", "state_r", 5), ("detachedv", "detached_prefetch_v_i", 1),
                ("detachedready", "detached_prefetch_ready_and_o", 1), ("detachedaddr", "detached_prefetch_addr_i", 34),
                ("previewv", "preview_v_i", 1), ("previewready", "preview_ready_o", 1),
                ("previewaddr", "preview_paddr_i", 34), ("published", "retained_insert_published_i", 1),
                ("done", "retained_insert_done_i", 1), ("owned", "retained_insert_owned_r", 1),
                ("pf", "retained_insert_pf_r", 1), ("owned_addr", "retained_insert_addr_r", 34))
            for key, signal, width in signals:
                result[lane + "." + key] = (prefix + signal, width)
            if lane == "i":
                result["i.aborted"] = ("unicore_lite.core_minimal.fe.icache.abort_inflight", 1)
    return result


def edge_samples(lines, expected, metadata=None):
    mapping, widths, values, changes = {}, {}, {}, {}
    current, ended = None, False
    clocks = [key for key in expected if key == "clk" or key.endswith(".clk")]
    def group(time, update):
        rising = [key for key in clocks if values.get(mapping[key]) == 0
                  and update.get(mapping[key], values.get(mapping[key])) == 1]
        if rising:
            yield time, rising, {key: values.get(handle) for key, handle in mapping.items()}
        values.update(update)
    for line in lines:
        p = line.rstrip("\n").split("\t")
        if p[0] == "#SIGNAL":
            _, key, width, handle, name = p
            audit.require(current is None and key in expected and key not in mapping, "invalid signal declaration")
            audit.require(int(width) == expected[key][1] and (name == expected[key][0] or name.endswith("." + expected[key][0])), "signal path/width mismatch: " + key)
            mapping[key], widths[int(handle)] = int(handle), int(width)
        elif p[0] == "#FST":
            audit.require(int(p[2]) > int(p[1]), "empty FST")
            if metadata is not None:
                metadata.update(start=int(p[1]), end=int(p[2]), timescale_exponent=int(p[3]))
        elif p[0] == "#END":
            ended = True
        elif p[0].startswith("#"):
            raise ValueError("unexpected FST reader record")
        else:
            audit.require(not ended and set(mapping) == set(expected), "incomplete selected declarations")
            time, handle, bits = int(p[0]), int(p[1]), p[2].lower()
            audit.require(handle in widths and len(bits) == widths[handle] and set(bits) <= set("01xz"), "invalid event bits")
            audit.require(current is None or time >= current, "unordered FST timestamps")
            if current is not None and current != time:
                yield from group(current, changes)
                changes = {}
            audit.require(handle not in changes, "repeated handle at one timestamp")
            changes[handle] = None if set(bits) & set("xz") else int(bits, 2)
            current = time
    audit.require(ended and current is not None, "partial selected event stream")
    yield from group(current, changes)


def snapshot_sources(document, out, delay):
    records = document.get("sources", document)
    names = {"top_zynq.sv", "blackparrot.sv", "bsg_nonsynth_zynq_testbench.sv",
             "bsg_nonsynth_axi_mem.sv", "bp_nonsynth_axi_mem_pipelined.sv",
             "bp_axi_response_delay.sv", "bp_axi_response_delay_fifo.sv"}
    result = []
    (out / "source").mkdir()
    for filename, record in records.items():
        path = Path(filename)
        if path.name not in names: continue
        raw, method = None, "current exact bytes"
        if path.exists() and binding(path)["sha256"] == record["sha256"]:
            raw = path.read_bytes()
        elif str(path).startswith(str(ROOT) + "/"):
            relative = str(path.relative_to(ROOT))
            r = subprocess.run(["git", "show", "HEAD:" + relative], cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            if r.returncode == 0 and hashlib.sha256(r.stdout).hexdigest() == record["sha256"]:
                raw, method = r.stdout, "exact HEAD Git object"
        audit.require(raw is not None and len(raw) == record["bytes"], "cannot recover compiled source " + filename)
        target = out / "source" / path.name
        audit.require(not target.exists(), "duplicate snapshot basename")
        target.write_bytes(raw)
        result.append(dict(compiled_path=filename, method=method, snapshot=binding(target)))
    found = {Path(b["compiled_path"]).name for b in result}
    audit.require({"top_zynq.sv", "bsg_nonsynth_zynq_testbench.sv", "bsg_nonsynth_axi_mem.sv"} <= found, "missing actual common-path source bindings")
    if delay:
        audit.require({"bp_axi_response_delay.sv", "bp_axi_response_delay_fifo.sv"} <= found, "delay source not compiled")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fst", type=Path, required=True)
    p.add_argument("--model-source-list", type=Path, required=True)
    p.add_argument("--log", type=Path, required=True)
    p.add_argument("--exit-code", type=int, required=True)
    p.add_argument("--delay", type=int, required=True)
    p.add_argument("--proof", type=Path, help="optional independent accepted advisory trace proof")
    p.add_argument("--no-uce", action="store_true")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    input_binding = binding(a.fst)
    source_list = json.loads(read_text(a.model_source_list))
    sources = snapshot_sources(source_list, a.out, a.delay)
    spec = importlib.util.spec_from_file_location("check_run", ROOT / "testing/check_run.py")
    checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
    checker.check_transcript(read_text(a.log), a.exit_code)
    proof = json.loads(a.proof.read_text()) if a.proof else None
    if proof: audit.require(proof["accepted"], "independent run proof rejected")
    expected = selections(a.delay, not a.no_uce)
    selection = a.out / "selection.tsv"
    selection.write_text("".join(key + "\t" + path + "\n" for key, (path, _) in expected.items()))
    observed = audit.Auditor(a.delay)
    metadata = {}
    endpoints = {l: audit.UceEndpoints(l) for l in ("i", "d")} if not a.no_uce else {}
    with tempfile.TemporaryDirectory(prefix="hp0-closed-fst-", dir="/dev/shm") as tmp:
        temp = Path(tmp)
        raw = a.fst
        if a.fst.suffix == ".xz":
            raw = temp / "closed.fst"
            with lzma.open(a.fst, "rb") as src, raw.open("wb") as dst:
                for block in iter(lambda: src.read(1024*1024), b""): dst.write(block)
        raw_binding = binding(raw)
        if proof:
            audit.require(all(raw_binding[k] == proof["bindings"]["fst"][k] for k in ("sha256", "bytes")), "raw FST differs from run proof")
        reader = temp / "fst_events"
        build = ["python3", str(READER_DIR / "build_reader.py"), "--output", str(reader)]
        result = subprocess.run(build, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=150)
        (a.out / "reader-build-command.log").write_text(result.stdout)
        audit.require(result.returncode == 0, "reader compile failed")
        for suffix in (".build.json", ".build.log"):
            (a.out / ("reader" + suffix)).write_bytes(reader.with_suffix(suffix).read_bytes())
        command = [str(reader), str(raw), str(selection.resolve())]
        with (a.out / "reader.stderr").open("w") as err, gzip.open(a.out / "selected-events.tsv.gz", "wt") as saved:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=err, text=True)
            timer = threading.Timer(600, process.kill); timer.daemon = True; timer.start()
            def lines():
                for line in process.stdout:
                    saved.write(line); yield line
            try:
                for time, clocks, values in edge_samples(lines(), expected, metadata):
                    if "clk" in clocks: observed.step(time, values)
                    for lane, endpoint in endpoints.items():
                        if lane + ".clk" in clocks: endpoint.step(time, values)
                audit.require(process.wait() == 0, "reader failed/timed out")
            except BaseException:
                process.kill(); process.wait(); raise
            finally:
                timer.cancel()
        report = observed.finish()
        report["FST_timebase"] = metadata
        report["UCE_endpoints"] = {lane: endpoint.finish() for lane, endpoint in endpoints.items()}
        transactions = {"external_reads": observed.external.reads, "external_writes": observed.external.writes,
            "BP_facing_reads": observed.core.reads, "BP_facing_writes": observed.core.writes,
            "R_shift": observed.streams[0].completed, "B_shift": observed.streams[1].completed,
            "UCE": {lane: endpoint.completed for lane, endpoint in endpoints.items()}}
        with gzip.open(a.out / "transactions.json.gz", "wt") as f: json.dump(transactions, f)
        audit.require(binding(a.fst) == input_binding, "closed input changed during audit")
        report["bindings"] = dict(compressed_or_raw_FST=input_binding, raw_FST=raw_binding,
            source_list=binding(a.model_source_list), source_snapshots=sources,
            log=binding(a.log), exit_code=a.exit_code,
            implementation=[binding(HERE / name) for name in ("run.py", "audit.py")],
            selection=binding(selection), selected_events=binding(a.out / "selected-events.tsv.gz"),
            transactions=binding(a.out / "transactions.json.gz"))
        if proof: report["bindings"]["independent_run_proof"] = binding(a.proof)
        report["reader_command"] = command
        (a.out / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: report[k] for k in ("accepted", "clock_period_FST_ticks", "external", "BP_facing", "R_stream", "B_stream")}, indent=2))


if __name__ == "__main__": main()
