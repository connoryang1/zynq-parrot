#!/usr/bin/env python3
"""Reverify closed07 rejection and closed08 synthetic restoration evidence.

Reads only closed artifacts; executes no target and changes no source/tests.
"""
import gzip
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RESEARCH = ROOT / "research"
CAP = RESEARCH / "large-retained-capacity-20261121"
ABI = RESEARCH / "retained-control-abi-20261121"
spec = importlib.util.spec_from_file_location("advisory_validate", ROOT / "testing/rtl/retained-advisory-trace/validate.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def read(path):
    return json.loads(Path(path).read_text())


def raw_binding(path, opener):
    digest, size = hashlib.sha256(), 0
    with opener(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block); size += len(block)
    return {"sha256": digest.hexdigest(), "bytes": size}


def match_record(path, record):
    b = v.binding(path)
    v.require(all(b[k] == record[k] for k in ("sha256", "bytes")), "binding mismatch: " + str(path))
    return b


def main():
    inputs = []
    def bound(path):
        info = v.binding(path); inputs.append(info); return info
    cold = ABI / "advisory-fixture-cold08"
    original = ABI / "advisory-fixture"
    proof_path = CAP / "advisory-full-system08/trace-audit01/verification.json"
    proof = read(proof_path); bound(proof_path)
    v.require(proof["accepted"] and proof["scope"] == "synthetic advisory whole-core correctness only", "08 not strict PASS")
    for name in ("fixture_manifest", "elf", "compiled_source_list", "selection", "events", "analyzer"):
        record = proof["bindings"][name]
        inputs.append(match_record(record["path"], record))
    for record in proof["bindings"]["critical_rtl"]:
        inputs.append(match_record(record["path"], record))
    fixture = read(cold / "manifest.json")
    old_fixture = read(original / "manifest.json")
    bound(original / "manifest.json")
    for name, manifest in (("original07.c", old_fixture), ("firsttouch08.c", fixture)):
        inputs.append(match_record(HERE / "source" / name, manifest["source"]))
    v.require(proof["bindings"]["fixture_manifest"]["path"] == str(cold / "manifest.json"), "wrong fixture manifest")
    for name in ("symbols.log", "disassembly.log"):
        record = next(b for b in fixture["logs"] if Path(b["path"]).name == name)
        inputs.append(match_record(cold / name, record))
    symbols = {}
    for line in (cold / "symbols.log").read_text().splitlines():
        fields = line.split()
        if len(fields) in (3, 4):
            symbols[fields[-1]] = int(fields[0], 16)
    start, end = symbols["__bss_start"], symbols["__bss_end"]
    v.require(fixture["data_address"] == v.DATA and fixture["data_bytes"] == 40960
              and start >= v.DATA + fixture["data_bytes"] and end > start,
              "data/BSS separation failed")
    # Verify the linked CRT, not merely the symbol names: t0 := gp-2000,
    # t1 := PC+0x1d000+710; then sd zero,0(t0), add8, unsigned loop to t1.
    elf_path = cold / "retained_advisory_full_line_test.elf"
    startup = v.elf_bytes(elf_path, 0x8000011e, 26)
    expected_startup = struct.pack("<IIIIIHI", 0x83018293, 0x0001d317,
                                  0x2c630313, 0x0062f763, 0x0002b023,
                                  0x02a1, 0xfe62ede3)
    v.require(startup == expected_startup and symbols["__global_pointer$"] - 2000 == start
              and 0x80000122 + 0x1d000 + 710 == end,
              "linked startup clear loop/address bounds changed")
    v.require(symbols["__tdata_size"] == symbols["__tbss_size"] == symbols["__tcb_size"] == 0
              and v.elf_bytes(elf_path, 0x80000274, 4) == struct.pack("<I", 0x00000613)
              and v.elf_bytes(elf_path, 0x80000296, 4) == struct.pack("<I", 0x00000613),
              "nonempty TLS initialization requires a new first-touch audit")
    words = {lane: list(struct.unpack("<8Q", v.elf_bytes(cold / "retained_advisory_full_line_test.elf", addr, 64)))
             for lane, addr in (("i", v.CODE), ("d", v.DATA))}
    code = [0x06500513] + [(n << 20) | (10 << 15) | 0x513 for n in range(1, 15)] + [0x8067]
    v.require(v.elf_bytes(cold / "retained_advisory_full_line_test.elf", v.CODE, 64)
              == struct.pack("<16I", *code), "wrong linked 16-instruction function")
    # Preserve the already-passed host gate and all six implementation/test sources.
    host = ABI / "advisory-trace-validator/host02-reset"
    host_proof = read(host / "verification.json"); bound(host / "verification.json")
    v.require(host_proof["accepted"], "host gate not accepted")
    for record in host_proof["sources"]:
        inputs.append(match_record(record["path"], record))
    reader = read(host / "reader.build.json"); bound(host / "reader.build.json")
    v.require(all(reader["executable"][k] == proof["bindings"]["reader"][k] for k in ("sha256", "bytes")),
              "consumed reader differs from tested reader")
    # Verify durable compressed inputs against their compressed and raw identities.
    run = CAP / "advisory-full-system08"
    archive = read(run / "archive.json"); bound(run / "archive.json")
    raw = {}
    for name, record in archive["files"].items():
        b = bound(run / name)
        v.require(b["sha256"] == record["sha256"], "compressed archive mismatch: " + name)
        raw[name] = raw_binding(run / name, lzma.open if name.endswith(".xz") else gzip.open)
        v.require(raw[name] == {"sha256": record["raw_sha256"], "bytes": record["raw_bytes"]},
                  "lossless raw archive mismatch: " + name)
    for key, name in (("fst", "trace.fst.xz"), ("log", "run.log.gz"), ("elf", "prog.riscv.gz")):
        v.require(raw[name] == {k: proof["bindings"][key][k] for k in ("sha256", "bytes")},
                  "archive/trace-proof mismatch: " + key)
    admission = json.loads(gzip.open(run / "admission.json.gz", "rt").read())
    process = json.loads(gzip.open(run / "process.json.gz", "rt").read())
    v.require(process == {"returncode": -6, "shell_exit_code": 134, "closed": True}, "actual process closure mismatch")
    v.require(admission["elf_sha256"] == raw["prog.riscv.gz"]["sha256"]
              and admission["nbf_sha256"] == raw["prog.nbf.gz"]["sha256"]
              and admission["source"] == fixture["source"], "runtime admission mismatch")
    checker_spec = importlib.util.spec_from_file_location("check_run", ROOT / "testing/check_run.py")
    checker = importlib.util.module_from_spec(checker_spec); checker_spec.loader.exec_module(checker)
    log = gzip.open(run / "run.log.gz", "rt").read()
    checker.check_transcript(log, process["shell_exit_code"])
    v.require(log.index(v.PASS) < checker.CORE_PASS.search(log).start(), "checked fixture marker ordering")
    # Same closed scoped06 hardware/model; no simulator rebuild for this software fixture.
    model = CAP / "full-system-64-scoped06"
    model_proof = read(model / "verification.json"); bound(model / "verification.json")
    v.require(model_proof["passed_complete_execution"] and model_proof["geometry"] == {
        "I_lines": 64, "D_lines": 64, "bytes_per_line": 64, "retained_sets": 64, "L1_unchanged": True}, "wrong model geometry")
    model_archive = bound(model / "Vbsg_nonsynth_zynq_testbench.gz")
    v.require(model_archive["sha256"] == model_proof["artifacts"]["Vbsg_nonsynth_zynq_testbench.gz"]["sha256"], "model archive changed")
    model_raw = raw_binding(model / "Vbsg_nonsynth_zynq_testbench.gz", gzip.open)
    v.require(model_raw["sha256"] == admission["model"]["sha256"], "consumed model binary mismatch")
    normalized = read(proof["bindings"]["compiled_source_list"]["path"])
    original_list = Path(normalized["original"]["path"])
    v.require(bound(original_list)["sha256"] == normalized["original"]["sha256"]
              and read(original_list) == normalized["sources"], "source-list normalization changed input records")
    # Independently recheck the accepted proof rows against ELF bytes and ordering.
    summary = {}
    for lane, addr in (("i", v.CODE), ("d", v.DATA)):
        st = proof["lanes"][lane]
        v.require(all(len(st[k]) == 1 for k in ("publications", "hits", "bursts")), "wrong qualifying event count")
        pub, hit, burst = st["publications"][0], st["hits"][0], st["bursts"][0]
        v.require(pub["insert"]["address"] == hit["lookup"]["address"] == addr
                  and pub["insert"]["data"] == sum(w << (n*64) for n, w in enumerate(words[lane])), "wrong published payload")
        v.require(proof["markers"]["submit"] < pub["time"] < hit["lookup"]["time"] < hit["time"]
                  < burst["start"] <= burst["end"] < proof["markers"]["completed"], "publication/hit/refill ordering")
        v.require(not burst["aborted"] and not burst["errors"] and len(burst["beats"]) == 8, "bad winning fill")
        for n, beat in enumerate(burst["beats"]):
            v.require(beat["word"] == n and beat["address"] == addr + n*8
                      and beat["data"] == words[lane][n] and beat["bank"] == (burst["way"]+n)%8, "bad winning SRAM beat")
        if lane == "d":
            v.require(burst["request_address"] == v.DATA + 24, "D critical word is not3")
        summary[lane] = {"physical_address": hex(addr), "publication_ps": pub["time"],
            "accepted_lookup_ps": hit["lookup"]["time"], "accepted_hit_ps": hit["time"],
            "first_actual_L1_write_ps": burst["start"], "last_actual_L1_write_ps": burst["end"],
            "way": burst["way"], "actual_write_beats": 8}
    retired = proof["cold_function_retirement"]
    v.require([r["pc"] for r in retired] == list(range(v.CODE, v.CODE+64, 4))
              and [r["instruction"] for r in retired] == code, "wrong cold instruction retirement")
    # Rejected07 remains rejected, with successful ordinary execution distinguished.
    rejected = CAP / "advisory-full-system07"
    attempt = read(rejected / "trace-audit03-child/attempt.json"); bound(rejected / "trace-audit03-child/attempt.json")
    localization = read(rejected / "replacement-localization05-child/localization.json")
    bound(rejected / "replacement-localization05-child/localization.json")
    diagnostic = read(rejected / "publication-diagnostic04-child/diagnostic.json")
    bound(rejected / "publication-diagnostic04-child/diagnostic.json")
    v.require(not attempt["accepted"] and attempt["analyzer_exit"] == 1, "07 rejection was lost")
    for lane in ("i", "d"):
        rows = [r for r in localization["refill_first_beats"] if r["lane"] == lane]
        v.require([r["line"] for r in rows] == list(range(10))
                  and [r["way"] for r in rows] == [1,2,3,4,5,6,7,0,4,2], "07 replacement localization mismatch")
        v.require(any(r["lane"] == lane and r["prefetch_install_state_r"] == 3
                      and r["prefetch_install_tag_match"] == 1 and r["prefetch_install_probe_way_r"] == 1
                      for r in diagnostic["history"]), "07 resident-drop proof missing")
    report = {"accepted": True, "scope": "closed07 rejection preserved; closed08 first-touch synthetic advisory I/D full-line restoration accepted",
        "review_script": v.binding(__file__), "bindings": inputs, "archive_raw": raw,
        "BSS": {"data_begin": hex(v.DATA), "data_end_exclusive": hex(v.DATA+fixture["data_bytes"]),
                "BSS_begin": hex(start), "BSS_end_exclusive": hex(end), "overlap": False,
                "linked_startup_clear_loop": {"begin_pc": "0x8000011e", "bytes": startup.hex(),
                    "decoded_start": hex(start), "decoded_end_exclusive": hex(end), "store_stride": 8},
                "TLS": {"tdata_bytes": 0, "tbss_bytes": 0, "tcb_bytes": 0,
                        "linked_memcpy_memset_size_arguments": 0}},
        "accepted08": {"fixture_manifest": str(cold / "manifest.json"), "elf_sha256": fixture["elf"]["sha256"],
            "events": summary, "cold_instructions_retired": 16, "actual_target_exit": 134,
            "exit_policy": "guest checked marker + CORE/HOST PASS; only documented subsequent GPIO finalization exception",
            "assertion_scope": model_proof["assertion_scope"]},
        "rejected07": {"fixture_manifest": str(original / "manifest.json"), "elf_sha256": old_fixture["elf"]["sha256"],
            "reason": "both target lines stayed ordinary-L1 way1; PF resident guard dropped completed hints before retained insertion"},
        "limits": proof["limits"] + ["Single first-touch synthetic protocol fixture on simulated64/64 geometry",
            "No practical FPGA capacity/fit/timing result", "No application benefit, whole-cost improvement or calibrated memory latency claim"]}
    (HERE / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: closed07 rejected; closed08 synthetic full-line I/D restoration and durable bindings verified")


if __name__ == "__main__":
    main()
