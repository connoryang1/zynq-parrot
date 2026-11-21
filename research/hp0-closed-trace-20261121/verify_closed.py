#!/usr/bin/env python3
"""Verify compact closed HP0 proofs and parent archive/model bindings; no runs."""
from collections import defaultdict
import gzip
import hashlib
import json
import lzma
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def require(ok, message):
    if not ok: raise ValueError(message)


def binding(path):
    path = Path(path)
    raw = path.read_bytes()
    return dict(path=str(path.resolve()), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def decoded(path, opener):
    h, size = hashlib.sha256(), 0
    with opener(path, "rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block); size += len(block)
    return dict(sha256=h.hexdigest(), bytes=size)


def main():
    host = json.loads((HERE / "host21/verification.json").read_text())
    require(host["accepted"], "host gate not accepted")
    for b in host["sources"]:
        require(binding(b["path"]) == b, "host-tested source changed")
    result = {"accepted": True, "scope": "closed simulator HP0 timing/stream integrity only",
              "review_script": binding(__file__), "host_proof": binding(HERE / "host21/verification.json"), "cases": {}}
    cases = [("native08-audit02", ROOT / "research/large-retained-capacity-20261121/advisory-full-system08", 0),
             ("delay200-10-audit01", ROOT / "research/hp0-response-path-20261121/full-system-delay200-10", 200)]
    for name, parent, delay in cases:
        directory = HERE / name
        proof = json.loads((directory / "verification.json").read_text())
        require(proof["accepted"] and proof["static_response_beat_minimum_age_cycles"] == delay, "wrong accepted case")
        for b in proof["bindings"]["implementation"]:
            require(binding(b["path"]) == b, "auditor source changed")
        for key in ("source_list", "log", "selection", "selected_events", "transactions", "independent_run_proof"):
            b = proof["bindings"][key]
            require(binding(b["path"]) == b, "audit binding changed: " + key)
        source_doc = Path(proof["bindings"]["source_list"]["path"])
        source_doc = json.loads(gzip.open(source_doc, "rt").read() if source_doc.suffix == ".gz" else source_doc.read_text())
        source_records = source_doc.get("sources", source_doc)
        for b in proof["bindings"]["source_snapshots"]:
            require(binding(b["snapshot"]["path"]) == b["snapshot"], "source snapshot changed")
            record = source_records[b["compiled_path"]]
            require(all(record[k] == b["snapshot"][k] for k in ("bytes", "sha256")), "snapshot differs from compiled source")
        archive = json.loads((parent / "archive.json").read_text())
        trace = archive["files"]["trace.fst.xz"]
        require(binding(parent / "trace.fst.xz")["sha256"] == trace["sha256"], "compressed FST changed")
        require(decoded(parent / "trace.fst.xz", lzma.open) == {"bytes": trace["raw_bytes"], "sha256": trace["raw_sha256"]}, "FST roundtrip changed")
        require(all(proof["bindings"]["raw_FST"][k] == {"bytes": trace["raw_bytes"], "sha256": trace["raw_sha256"]}[k]
                    for k in ("bytes", "sha256")), "audit/parent FST mismatch")
        admission = json.loads(gzip.open(parent / "admission.json.gz", "rt").read())
        model = (ROOT / "research/large-retained-capacity-20261121/full-system-64-scoped06/Vbsg_nonsynth_zynq_testbench.gz"
                 if delay == 0 else parent / "Vbsg_nonsynth_zynq_testbench.gz")
        require(decoded(model, gzip.open)["sha256"] == admission["model"]["sha256"], "model/archive mismatch")
        independent = json.loads(Path(proof["bindings"]["independent_run_proof"]["path"]).read_text())
        require(independent["accepted"] and independent["bindings"]["fst"]["sha256"] == trace["raw_sha256"], "independent correctness proof mismatch")
        transactions = json.loads(gzip.open(directory / "transactions.json.gz", "rt").read())
        for channel, fields in (("R", ("id", "data", "resp", "last")), ("B", ("id", "resp"))):
            shifted = transactions[channel + "_shift"]
            for beat in shifted:
                require(beat["first_offer_cycle"]-beat["input_cycle"] == delay
                        and beat["output_cycle"]-beat["input_cycle"] == delay, "observed stream age not exact")
            before = [beat for req in transactions["external_reads"] for beat in req["beats"]] if channel == "R" else [
                dict(id=req["id"], resp=0) for req in transactions["external_writes"]]
            require(len(before) == len(shifted), "response count changed")
            # Actual traces have one outstanding request; row order is actual stream order here.
            require([tuple(b[k] for k in fields) for b in before] == [tuple(b["payload"]) for b in shifted], "opaque stream mismatch")
        period = proof["clock_period_FST_ticks"]
        uce = {}
        for lane, rows in transactions["UCE"].items():
            groups = defaultdict(list)
            for row in rows: groups[tuple(row["source_states"])].append(row)
            uce[lane] = {str(states): {"count": len(group),
                "first_ACK_clock_periods": sorted({(r["first_accept"]-r["request_time"])/period for r in group}),
                "full_ACK_clock_periods": sorted({(r["complete"]-r["request_time"])/period for r in group})}
                for states, group in groups.items()}
        changes = defaultdict(int)
        for req in transactions["external_reads"] + transactions["external_writes"]:
            changes[req["request_cycle"]] += 1; changes[req["complete"]] -= 1
        pending, peak = 0, 0
        for cycle in sorted(changes): pending += changes[cycle]; peak = max(peak,pending)
        result["cases"][name] = {"audit_proof": binding(directory / "verification.json"),
            "parent_archive": binding(parent / "archive.json"), "admission": binding(parent / "admission.json.gz"),
            "parent_model_archive": binding(model), "consumed_model_sha256": admission["model"]["sha256"],
            "raw_FST": proof["bindings"]["raw_FST"], "delay": delay,
            "AXI_clock_FST_ticks": period, "max_combined_read_write_outstanding_after_edge": peak,
            "UCE_by_actual_refill_state": uce,
            "limits": "All observed loading/setup/runtime traffic. No platform concurrency limit, HP0 origin attribution, physical calibration or application comparison."}
    result["scope_limits"] = ["Native08 predates shim source; run10 verifies its static200 integration, not a matched optimization effect",
        "Future baseline/optimized arms require the same integrated source, geometry and N",
        "The FIFO/same-ID auditor supports concurrency and stalls, but these whole-core traces do not exercise them",
        "Actual per-beat age200 shifts full8-beat response once by200; not200 serialized per word"]
    (HERE / "closed-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print("PASS: native08 and delay20010 closed HP0 timing, opaque responses and consumed-model bindings")


if __name__ == "__main__": main()
