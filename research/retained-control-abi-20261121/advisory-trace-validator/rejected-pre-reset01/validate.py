#!/usr/bin/env python3
"""Validate selected closed-FST advisory publication, retained hits and real L1 writes.

This is a synthetic whole-core correctness gate. It makes no application
performance, useful-capacity, lower-memory drain or FPGA claim.
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import threading

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREFIX = "unicore_lite."
CODE = 0x80001000
DATA = 0x80012000
PASS = "[BSG-PASS] retained advisory full-line I/D checked all words completed"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def binding(path):
    path = Path(path).resolve()
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": h.hexdigest()}


def selections():
    """key -> (unique suffix, expected width), exact accepted 64B/8-way geometry."""
    out = {"control": (PREFIX + "retained_control_r", 4),
           "be.clk": (PREFIX + "core_minimal.be.clk_i", 1)}
    # Read actual backend-connected packed ports as well as client aliases.
    for key, name in (("lv", "lookup_v_i"), ("lr", "lookup_ready_o"),
                      ("rv", "resp_v_o"), ("rr", "resp_ready_i"), ("rh", "resp_hit_o"),
                      ("iv", "insert_v_i"), ("ir", "insert_ready_o"),
                      ("done", "insert_done_o"), ("published", "insert_published_o")):
        out["store." + key] = (PREFIX + "retained_store.storage." + name, 2)
    for n, lane in enumerate(("i", "d")):
        for key, name, width in (("la", "lookup_addr_i", 34), ("rd", "resp_data_o", 512),
                                 ("ia", "insert_addr_i", 34), ("id", "insert_data_i", 512)):
            out["store." + lane + "." + key] = (
                PREFIX + "retained_store.storage.{}[{}]".format(name, n), width)
    for field, width in (("instret", 1), ("pc", 39), ("ctxtsw", 1), ("exception", 1)):
        out["be." + field] = (PREFIX + "core_minimal.be.commit_pkt." + field, width)
    for field, width in (("funct7", 7), ("rs2_addr", 5), ("rs1_addr", 5),
                         ("funct3", 3), ("rd_addr", 5), ("opcode", 7)):
        out["be.instr." + field] = (PREFIX + "core_minimal.be.commit_pkt.instr.t.rtype." + field, width)
    for lane in ("i", "d"):
        uce = PREFIX + lane + "cache_uce."
        cache = PREFIX + ("core_minimal.fe.icache." if lane == "i" else
                          "core_minimal.be.calculator.pipe_mem.dcache.")
        for key, signal, width in (
            ("bclk", "clk_i", 1), ("enable", "retained_enable_i", 1),
            ("demand_copy", "retained_demand_capture_i", 1),
            ("lv", "retained_lookup_v_o", 1), ("lr", "retained_lookup_ready_i", 1),
            ("la", "retained_lookup_addr_o", 34), ("rv", "retained_resp_v_i", 1),
            ("rr", "retained_resp_ready_o", 1), ("rh", "retained_resp_hit_i", 1),
            ("rd", "retained_resp_data_i", 512), ("iv", "retained_insert_v_o", 1),
            ("ir", "retained_insert_ready_i", 1), ("ia", "retained_insert_addr_o", 34),
            ("id", "retained_insert_data_o", 512), ("done", "retained_insert_done_i", 1),
            ("published", "retained_insert_published_i", 1),
            ("owned", "retained_insert_owned_r", 1), ("pf", "retained_insert_pf_r", 1),
            ("owned_addr", "retained_insert_addr_r", 34),
            ("state", "state_r", 5), ("req_addr", "cache_req_r.addr", 34),
        ):
            out[lane + "." + key] = (uce + signal, width)
        for key, signal, width in (
            ("cclk", "clk_i", 1), ("v", "data_mem_pkt_v_i", 1),
            ("yumi", "data_mem_pkt_yumi_o", 1), ("slow", "data_mem_slow_write", 8),
            ("mem_v", "data_mem_v_li", 8), ("mem_w", "data_mem_w_li", 8),
            ("critical", "cache_req_critical_i", 1), ("last", "cache_req_last_i", 1),
            ("tv", "tag_mem_pkt_v_i", 1), ("ty", "tag_mem_pkt_yumi_o", 1),
        ):
            out[lane + "." + key] = (cache + signal, width)
        for field, width in (("addr", 34), ("index", 6), ("way_id", 3),
                             ("data", 64), ("fill_index", 8), ("opcode", 2)):
            out[lane + ".pkt." + field] = (cache + "data_mem_pkt_cast_i." + field, width)
        for field, width in (("index", 6), ("way_id", 3), ("tag", 20),
                             ("opcode", 3), ("state", 3)):
            out[lane + ".tag." + field] = (cache + "tag_mem_pkt_cast_i." + field, width)
        for bank in range(8):
            for field, sig, width in (("addr", "addr", 9), ("data", "data", 64)):
                out[lane + ".mem.{}.{}".format(field, bank)] = (
                    cache + "data_mem_{}_li[{}]".format(sig, bank), width)
            if lane == "d":
                out[lane + ".mem.mask." + str(bank)] = (
                    cache + "data_mem_mask_li[{}]".format(bank), 8)
        if lane == "i":
            for field in ("abort_miss", "abort_miss_r", "miss_abort_i"):
                out[lane + "." + field] = (cache + field, 1)
    return out


def edge_samples(lines):
    """Group all changes at t; sample pre-t stable values on rising local clocks.

    FST stores settled timestamp values, not intra-evaluation ordering. Sampling
    values after the edge would observe next FSM state/beat and overcount writes.
    Unknown inactive values are allowed; any consulted unknown fails closed.
    """
    expected = selections()
    mapping, widths, values = {}, {}, {}
    current, changes, ended = None, {}, False
    clocks = ["be.clk", "i.bclk", "i.cclk", "d.bclk", "d.cclk"]

    def edges(t, update):
        rising = [key for key in clocks if values.get(mapping[key]) == 0
                  and update.get(mapping[key], values.get(mapping[key])) == 1]
        if rising:
            sample = {key: values.get(handle) for key, handle in mapping.items()}
            yield t, rising, sample
        values.update(update)

    for line in lines:
        parts = line.rstrip("\n").split("\t")
        if parts[0] == "#SIGNAL":
            require(current is None and len(parts) == 5, "late/bad signal declaration")
            _, key, width, handle, name = parts
            require(key in expected and key not in mapping, "unexpected/duplicate signal " + key)
            require(int(width) == expected[key][1], "wrong width: " + key)
            suffix = expected[key][0]
            require(name == suffix or name.endswith("." + suffix), "wrong signal path: " + key)
            mapping[key] = int(handle); widths[int(handle)] = int(width)
        elif parts[0] == "#FST":
            require(len(parts) == 4 and int(parts[2]) > int(parts[1]), "empty/bad FST interval")
        elif parts[0] == "#END":
            ended = True
        elif parts[0].startswith("#"):
            raise ValueError("unexpected reader record")
        else:
            require(not ended and len(parts) == 3, "bad event record")
            require(set(mapping) == set(expected), "missing selected signals")
            t, handle = int(parts[0]), int(parts[1])
            require(handle in widths, "unselected event handle")
            bits = parts[2].lower()
            require(len(bits) == widths[handle] and set(bits) <= set("01xz"), "bad event value")
            v = None if set(bits) & set("xz") else int(bits, 2)
            require(current is None or t >= current, "nonmonotonic events")
            if current is not None and t != current:
                yield from edges(current, changes)
                changes = {}
            current = t
            require(handle not in changes, "multiple values for one handle at timestamp")
            changes[handle] = v
    require(ended and current is not None, "reader incomplete/empty")
    yield from edges(current, changes)


class Validator:
    def __init__(self, words, markers):
        self.words, self.markers = words, markers
        self.marked, self.retired = {}, []
        self.lanes = {l: {"lookup": None, "insert": None, "publications": [],
                          "hits": [], "bursts": [], "active": None,
                          "discarded": []} for l in ("i", "d")}

    def sample(self, t, clocks, values):
        def get(key):
            v = values.get(key)
            require(v is not None, "missing/unknown sampled " + key)
            return v
        if "be.clk" in clocks and get("be.instret"):
            require(not get("be.ctxtsw") and not get("be.exception"), "invalid retirement")
            pc = get("be.pc")
            for name, address in self.markers.items():
                if pc == address:
                    require(name not in self.marked, "marker retired twice: " + name)
                    self.marked[name] = t
            if CODE <= pc < CODE + 64:
                instruction = 0
                for field, width in (("funct7", 7), ("rs2_addr", 5), ("rs1_addr", 5),
                                     ("funct3", 3), ("rd_addr", 5), ("opcode", 7)):
                    instruction = (instruction << width) | get("be.instr." + field)
                expected = (self.words["i"][(pc - CODE) // 8] >> ((pc & 7) * 8)) & 0xffffffff
                require(pc % 4 == 0 and instruction == expected, "cold instruction retirement payload mismatch")
                self.retired.append({"time": t, "pc": pc, "instruction": instruction})
        for lane, target in (("i", CODE), ("d", DATA)):
            st = self.lanes[lane]
            g = lambda key: get(lane + "." + key)
            line_value = sum(w << (64 * n) for n, w in enumerate(self.words[lane]))
            if lane + ".bclk" in clocks:
                lane_number = int(lane == "d")
                for key in ("lv", "lr", "rv", "rr", "rh", "iv", "ir", "done", "published"):
                    require(g(key) == ((get("store." + key) >> lane_number) & 1),
                            lane + " backend/client handshake mismatch: " + key)
                require(not g("published") or g("done"), lane + " publication without done")
                if g("iv") and g("ir"):
                    require(st["insert"] is None, lane + " overlapping insert ownership")
                    st["insert"] = {"time": t, "address": g("ia"), "data": g("id")}
                    require(g("ia") == get("store." + lane + ".ia")
                            and g("id") == get("store." + lane + ".id"), lane + " backend insert mismatch")
                if g("done"):
                    ins = st["insert"]
                    require(ins is not None, lane + " insert done without acceptance")
                    if g("published") and ins["address"] == target:
                        require(get("control") == 3 and g("enable") and not g("demand_copy"),
                                lane + " publication outside advisory-only control3")
                        require(g("owned") and g("pf") and g("owned_addr") == target,
                                lane + " publication not PF-owned")
                        require(ins["data"] == line_value, lane + " wrong published full line")
                        st["publications"].append({"time": t, "insert": ins})
                    st["insert"] = None
                if g("lv") and g("lr"):
                    require(st["lookup"] is None, lane + " overlapping lookup ownership")
                    st["lookup"] = {"time": t, "address": g("la")}
                    require(g("la") == get("store." + lane + ".la"), lane + " backend lookup mismatch")
                if g("rv") and g("rr"):
                    query = st["lookup"]
                    require(query is not None, lane + " response without accepted lookup")
                    require(g("rd") == get("store." + lane + ".rd"), lane + " backend response mismatch")
                    if g("rh") and query["address"] == target:
                        require(get("control") == 3 and not g("demand_copy"),
                                lane + " hit outside advisory-only control3")
                        require(st["publications"] and st["publications"][-1]["time"] < query["time"],
                                lane + " hit query precedes PF publication")
                        require(g("rd") == line_value, lane + " wrong accepted 512-bit hit payload")
                        st["hits"].append({"time": t, "lookup": query})
                    st["lookup"] = None
            if lane + ".cclk" not in clocks:
                continue
            aborted = lane == "i" and any(g(k) for k in (
                "abort_miss", "abort_miss_r", "miss_abort_i"))
            if st["active"] and aborted:
                st["active"]["aborted"] = True
            if not (g("v") and g("yumi") and g("state") == 22
                    and (g("pkt.addr") & ~63) == target):
                continue
            w = (g("pkt.addr") & 63) // 8
            if w == 0:
                require(st["active"] is None, lane + " restarted unfinished fill")
                require(st["hits"] and st["hits"][-1]["time"] < t,
                        lane + " retained fill without accepted hit")
                st["active"] = {"start": t, "way": g("pkt.way_id"), "beats": [],
                                "aborted": bool(aborted), "hit": st["hits"][-1],
                                "request_address": g("req_addr"), "errors": []}
            burst = st["active"]
            require(burst is not None, lane + " fill starts after word0")
            way = burst["way"]
            bank = (w + way) % 8
            checks = {
                "ascending distinct words": w == len(burst["beats"]),
                "packet address": g("pkt.addr") == target + 8 * w,
                "packet index": g("pkt.index") == ((target >> 6) & 63),
                "constant valid way": 0 <= way < 8 and g("pkt.way_id") == way,
                "word payload": g("pkt.data") == self.words[lane][w],
                "one-hot fill mask": g("pkt.fill_index") == 1 << w,
                "normal data-write opcode": g("pkt.opcode") == 0,
                "actual slow SRAM write": g("slow") == 1 << bank,
                "actual SRAM v/w": bool(g("mem_v") & (1 << bank)) and bool(g("mem_w") & (1 << bank)),
                "actual SRAM address": g("mem.addr." + str(bank)) == (((target >> 6) & 63) * 8 + w),
                "actual SRAM data": g("mem.data." + str(bank)) == self.words[lane][w],
                "critical word": g("critical") == int(w == ((burst["request_address"] >> 3) & 7)),
                "last beat": g("last") == int(w == 7),
            }
            if lane == "d":
                checks["D critical request offset3"] = burst["request_address"] == target + 24
                checks["actual D SRAM byte mask"] = g("mem.mask." + str(bank)) == 255
            if w == 0:
                checks["accepted ordinary L1 tag write"] = bool(g("tv") and g("ty"))
                checks["tag contents"] = (g("tag.opcode") == 1 and g("tag.index") == ((target >> 6) & 63)
                    and g("tag.way_id") == way and g("tag.tag") == target >> 12 and g("tag.state") == 6)
            burst["errors"].extend(name for name, ok in checks.items() if not ok)
            burst["beats"].append({"time": t, "word": w, "bank": bank,
                                    "address": g("pkt.addr"), "data": g("pkt.data")})
            if w == 7:
                burst["end"] = t
                if burst["aborted"]:
                    st["discarded"].append(burst)
                else:
                    require(len(burst["beats"]) == 8 and not burst["errors"],
                            lane + " invalid real L1 fill: " + ", ".join(burst["errors"]))
                    st["bursts"].append(burst)
                st["active"] = None

    def finish(self):
        require(set(self.marked) == set(self.markers), "missing retired fixture markers")
        require(self.marked["submit"] < self.marked["demand"] < self.marked["completed"],
                "retired marker ordering")
        for lane, st in self.lanes.items():
            require(st["publications"] and st["hits"] and st["bursts"],
                    lane + " missing PF publication, accepted hit, or real complete winning L1 fill")
            require(all(self.marked["submit"] <= p["insert"]["time"] < p["time"]
                        < self.marked["completed"] for p in st["publications"]), lane + " publication window")
            require(any(b["end"] < self.marked["completed"] for b in st["bursts"]),
                    lane + " fill does not precede completed marker")
        cold = [r for r in self.retired if self.lanes["i"]["publications"][-1]["time"]
                < r["time"] < self.marked["completed"]]
        require([r["pc"] for r in cold] == list(range(CODE, CODE + 64, 4)),
                "post-publication cold function did not retire all 16 instructions exactly once")
        return {"accepted": True, "scope": "synthetic advisory whole-core correctness only",
                "markers": self.marked, "cold_function_retirement": cold, "lanes": self.lanes,
                "limits": ["No application performance or FPGA result", "Markers are BE retirement boundaries, not FE request start",
                           "I hits may precede retired demand marker; complete non-aborted SRAM-writing burst required",
                           "Pre-edge settled sampling; no intra-timestamp simulator event-order proof",
                           "CSR/controller idle is not lower-L2/AXI/DRAM drain"]}


def elf_bytes(path, address, size):
    data = Path(path).read_bytes()
    require(data[:6] == b"\x7fELF\x02\x01", "expected ELF64 little-endian")
    phoff = struct.unpack_from("<Q", data, 32)[0]
    entsize, count = struct.unpack_from("<HH", data, 54)
    for n in range(count):
        kind, _, offset, va, _, filesz, _, _ = struct.unpack_from("<IIQQQQQQ", data, phoff + n * entsize)
        if kind == 1 and va <= address and address + size <= va + filesz:
            return data[offset + address - va:offset + address - va + size]
    raise ValueError("expected fixture bytes absent from ELF")


def source_bindings(source_list):
    compiled = json.loads(Path(source_list).read_text())["sources"]
    paths = ["bp_top/src/v/bp_unicore_lite.sv", "bp_me/src/v/cce/bp_uce.sv",
             "bp_common/src/v/bp_retained_line_store.sv", "bp_fe/src/v/bp_fe_icache.sv",
             "bp_be/src/v/bp_be_dcache/bp_be_dcache.sv"]
    result = []
    for suffix in paths:
        path = ROOT / "import/black-parrot" / suffix
        info = binding(path)
        require(str(path) in compiled and all(info[k] == compiled[str(path)][k]
                for k in ("bytes", "sha256")), "compiled/source mismatch: " + suffix)
        result.append(info)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fst", type=Path, required=True)
    p.add_argument("--reader", type=Path, required=True)
    p.add_argument("--model-source-list", type=Path, required=True,
                   help="closed actual-source-list.json from the consumed model build")
    p.add_argument("--fixture-manifest", type=Path, default=ROOT / "research/retained-control-abi-20261121/advisory-fixture/manifest.json")
    p.add_argument("--log", type=Path, required=True)
    p.add_argument("--exit-code", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--reader-timeout", type=int, default=600)
    a = p.parse_args()
    require(1 <= a.reader_timeout <= 1800, "reader timeout must be bounded 1..1800 seconds")
    a.out.mkdir(parents=True, exist_ok=False)
    before = binding(a.fst)
    sources = source_bindings(a.model_source_list)
    fixture = json.loads(a.fixture_manifest.read_text())
    elf = Path(fixture["elf"]["path"])
    require(binding(elf) == fixture["elf"], "fixture ELF identity mismatch")
    require(binding(fixture["source"]["path"]) == fixture["source"], "fixture source identity mismatch")
    require(fixture["targets"][0] == CODE and fixture["data_address"] == DATA, "wrong fixture layout")
    words = {lane: list(struct.unpack("<8Q", elf_bytes(elf, addr, 64)))
             for lane, addr in (("i", CODE), ("d", DATA))}
    expected = [(0xd176a0943bf52e81 ^ ((0x1728394a5b6c7d8 * (w + 1)) & ((1 << 64) - 1))) for w in range(8)]
    require(words["d"] == expected, "ELF/data WORD formula mismatch")
    spec = importlib.util.spec_from_file_location("check_run", ROOT / "testing/check_run.py")
    checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
    log = a.log.read_text()
    checker.check_transcript(log, a.exit_code)
    core_pass = checker.CORE_PASS.search(log)
    require(PASS in log and log.index(PASS) < core_pass.start(), "missing checked fixture return before CORE PASS")
    sel = a.out / "selection.tsv"
    sel.write_text("".join(key + "\t" + path + "\n" for key, (path, _) in selections().items()))
    command = [str(a.reader.resolve()), str(a.fst.resolve()), str(sel.resolve())]
    validator = Validator(words, fixture["markers"])
    with (a.out / "reader.stderr").open("w") as err, gzip.open(a.out / "selected-events.tsv.gz", "wt") as saved:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=err, text=True)
        timer = threading.Timer(a.reader_timeout, process.kill)
        timer.daemon = True
        timer.start()
        def lines():
            for line in process.stdout:
                saved.write(line)
                yield line
        try:
            for t, clocks, values in edge_samples(lines()):
                validator.sample(t, clocks, values)
            require(process.wait() == 0, "selected FST reader failed or timed out")
        except BaseException:
            process.kill(); process.wait(); raise
        finally:
            timer.cancel()
    report = validator.finish()
    require(binding(a.fst) == before, "FST changed during read; no closed trace")
    require(source_bindings(a.model_source_list) == sources, "critical source changed during analysis")
    report["bindings"] = {"fst": before, "fixture_manifest": binding(a.fixture_manifest),
                          "elf": binding(elf), "log": binding(a.log), "exit_code": a.exit_code,
                          "reader": binding(a.reader), "analyzer": binding(__file__),
                          "compiled_source_list": binding(a.model_source_list), "critical_rtl": sources,
                          "selection": binding(sel), "events": binding(a.out / "selected-events.tsv.gz")}
    report["command"] = command
    (a.out / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: advisory PF publication -> actual I/D retained hit -> real full-line L1 writes + checked execution")


if __name__ == "__main__":
    main()
