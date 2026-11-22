"""Future ROOT source-only preflight; no vendor/reader/model invocation."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTEXT_SHA = "e49b35502b2fe982f5157684dc42801ce833fff4cfb973e514d85f2e8f209f78"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check(record):
    data = Path(record["path"]).read_bytes()
    if len(data) != record["bytes"] or digest(data) != record["sha256"]:
        raise RuntimeError("source drift: " + record["path"])
    return data


def main():
    raw = (HERE / "source-context.json").read_bytes()
    if digest(raw) != CONTEXT_SHA:
        raise RuntimeError("fixed source-context identity")
    c = json.loads(raw)
    for key in ("native_metadata", "production397_bridge", "production_exclusion",
                "actual_FPGA_synth_Tcl", "actual_FPGA_generated_selector",
                "actual_native_include_search_record", "actual_existing_parameter_proof"):
        check(c[key])
    native = json.loads(check(c["native_metadata"]))["sources"]
    bridge = json.loads(check(c["production397_bridge"]))
    if len(native) != 398 or len(bridge) != 397:
        raise RuntimeError("exact consumed-source counts")
    by_path = {row["native"]: row for row in bridge}
    selected = c["selected_RTL_sources"]
    if len(selected) != 12:
        raise RuntimeError("minimal CSR dependency list")
    generated = c["actual_FPGA_generated_selector"]["path"]
    for row in selected:
        check(row)
        if row["path"] != generated:
            b = by_path[row["path"]]
            if (b["bytes"], b["sha256"]) != (row["bytes"], row["sha256"]):
                raise RuntimeError("production byte bridge")
    headers = [row for row in native.values()
               if Path(row["path"]).suffix in (".svh", ".vh", ".vi")
               or Path(row["path"]).name == "bsg_defines.sv"]
    if len(headers) != c["header_count"]:
        raise RuntimeError("header count")
    for row in headers:
        check(row)
        b = by_path[row["path"]]
        if (b["bytes"], b["sha256"]) != (row["bytes"], row["sha256"]):
            raise RuntimeError("production header bridge")
    defines = " ".join(c["exact_seven_defines"])
    synth = check(c["actual_FPGA_synth_Tcl"]).decode()
    if "set_property verilog_define {" + defines + "} [current_fileset]" not in synth:
        raise RuntimeError("actual final-BD defines")
    old = HERE.parent / "csr-single-writer-register-preparation-20261122"
    ram = (old / "store-ram.sv").read_bytes()
    ff = (old / "store-registers.sv").read_bytes()
    if digest(ram) != "e5a1518bd6a587157e73895c2e962dd467438e2c25565ea3223d2fb259e5f805":
        raise RuntimeError("closed RAM source")
    if digest(ff) != "17d7b4c69cf4e69f2f94d758684aea3c0cd9657a6c1f79c872e8acdf5e8b3e9e":
        raise RuntimeError("fixed register candidate")
    if ram.count(b'ram_style="distributed"') != 1 or ff != ram.replace(
            b'ram_style="distributed"', b'ram_style="registers"'):
        raise RuntimeError("attribute-only diff")
    construction = json.loads((HERE / "source-construction.json").read_bytes())
    top_rows = [r for r in native.values() if r["path"].endswith("/bp_be_top.sv")]
    if len(top_rows) != 1:
        raise RuntimeError("unique actual top source")
    top = check(top_rows[0])
    if digest(top) != construction["source_top_sha256"]:
        raise RuntimeError("literal top identity")
    wrapper = (HERE / "csr_native_consumer_wrapper.sv").read_bytes()
    for fragment in construction["literal_current_top_fragments"]:
        offset = sum(len(x) for x in top.splitlines(keepends=True)[:fragment["start_line"]-1])
        data = top[offset:offset+fragment["bytes"]]
        if digest(data) != fragment["sha256"] or data not in wrapper:
            raise RuntimeError("literal top fragment")
    print(json.dumps({"state": "PASS_SOURCE_BYTES_ONLY", "RTL": len(selected),
                      "headers": len(headers), "production_bridge": len(bridge),
                      "defines": c["exact_seven_defines"],
                      "elaboration_mapping_correctness": "NOT_EXECUTED"}, sort_keys=True))


if __name__ == "__main__":
    main()
