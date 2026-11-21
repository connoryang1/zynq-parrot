#!/usr/bin/env python3
"""Read only the same closed08/10 PF timing; no model/target execution."""
import gzip
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "testing/rtl/hp0-closed-trace"))
import run as hp


def main():
    fields = ["clk_i", "reset_i", "prefetch_issue", "fsm_fwd_v_lo", "fsm_fwd_last_lo",
        "fsm_fwd_header_lo.addr", "fsm_fwd_header_lo.payload.prefetch",
        "mem_fwd_v_o", "mem_fwd_ready_and_i", "fwd_pump_out.msg_header_cast_o.addr",
        "fwd_pump_out.msg_header_cast_o.msg_type", "prefetch_response", "prefetch_response_yumi",
        "prefetch_response_addr", "fsm_rev_last_li", "prefetch_install_state_r",
        "prefetch_install_full", "prefetch_install_available", "prefetch_install_safe_to_wait",
        "retained_insert_published_i", "retained_insert_done_i", "credit_count_lo"]
    results = {}
    cases = [("native08-audit02", ROOT / "research/large-retained-capacity-20261121/advisory-full-system08/trace.fst.xz"),
             ("delay200-10-audit01", ROOT / "research/hp0-response-path-20261121/full-system-delay200-10/trace.fst.xz")]
    for case, archive in cases:
        out = HERE / case
        out.mkdir(exist_ok=False)
        old = HERE.parent / case
        proof = json.loads((old / "verification.json").read_text())
        admit = {lane: s["advisory_publications"][0]["advisory"]["time"] for lane,s in proof["UCE_endpoints"].items()}
        pub = {lane: s["advisory_publications"][0]["time"] for lane,s in proof["UCE_endpoints"].items()}
        start, end = min(admit.values())-2000000, max(pub.values())+1000000
        selection = out / "selection.tsv"
        requests = {lane + "." + f: "unicore_lite." + lane + "cache_uce." + f for lane in ("i","d") for f in fields}
        for lane in ("i","d"):
            requests[lane + ".clk"] = requests.pop(lane + ".clk_i")
        for f in ("aclk", "aresetn", "axi_araddr", "hp0_axi_araddr", "hp0_axi_arvalid", "hp0_axi_arready", "dram_base_li"):
            requests["root." + f] = "top_fpga_inst." + f
        selection.write_text("".join(k+"\t"+v+"\n" for k,v in requests.items()))
        with tempfile.TemporaryDirectory(prefix="closed-pf-localize-", dir="/dev/shm") as temp:
            temp = Path(temp)
            raw = temp / "closed.fst"
            with lzma.open(archive,"rb") as src, raw.open("wb") as dst:
                for block in iter(lambda: src.read(1024*1024), b""): dst.write(block)
            assert hp.binding(raw)["sha256"] == proof["bindings"]["raw_FST"]["sha256"]
            reader = temp / "fst_events"
            subprocess.run(["python3", str(hp.READER_DIR / "build_reader.py"), "--output", str(reader)],check=True,timeout=150)
            cmd = [str(reader), str(raw), str(selection.resolve())]
            result = subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=120)
            (out / "reader.stderr").write_text(result.stderr)
            assert result.returncode == 0,result.stderr
            with gzip.open(out / "selected-events.tsv.gz","wt") as f: f.write(result.stdout)
            (out / "reader.build.json").write_bytes(reader.with_suffix(".build.json").read_bytes())
        expected = {}
        for line in result.stdout.splitlines():
            if line.startswith("#SIGNAL"):
                p=line.split("\t"); expected[p[1]]=(requests[p[1]],int(p[2]))
        assert set(expected) == set(requests)
        log, last_state = {lane:[] for lane in ("i","d")}, {}
        reset_seen = set()
        translated = []
        for time,clocks,s in hp.edge_samples(iter(result.stdout.splitlines(keepends=True)),expected):
            if not start <= time <= end: continue
            # Every UCE reset was already checked in the accepted complete
            # auditor. This subwindow is strictly after its initialized epoch.
            if s["root.hp0_axi_arvalid"] and s["root.hp0_axi_arready"]:
                item={"time":time,"BP_PA":s["root.axi_araddr"],"HP0_address":s["root.hp0_axi_araddr"],"base":s["root.dram_base_li"]}
                if not translated or translated[-1] != item: translated.append(item)
            for lane in ("i","d"):
                if lane+".clk" not in clocks: continue
                g=lambda f:s[lane+"."+f]
                assert g("reset_i") == 0
                event={"time":time}
                if g("prefetch_issue"):
                    assert g("fsm_fwd_v_lo") and g("fsm_fwd_last_lo") and g("fsm_fwd_header_lo.payload.prefetch")
                    event["PF_FSM_issue_PA"]=g("fsm_fwd_header_lo.addr")
                if g("mem_fwd_v_o") and g("mem_fwd_ready_and_i"):
                    event["accepted_memory_forward_PA"]=g("fwd_pump_out.msg_header_cast_o.addr")
                    event["accepted_memory_forward_type"]=g("fwd_pump_out.msg_header_cast_o.msg_type")
                if g("prefetch_response"):
                    event.update(PF_reply_PA=g("prefetch_response_addr"),PF_reply_accepted=g("prefetch_response_yumi"),PF_reply_last=g("fsm_rev_last_li"))
                state=g("prefetch_install_state_r")
                if state != last_state.get(lane):
                    event.update(installer_state=state,full=g("prefetch_install_full"),available=g("prefetch_install_available"),safe=g("prefetch_install_safe_to_wait"),credits=g("credit_count_lo"))
                    last_state[lane]=state
                if g("retained_insert_published_i"): event["published"]=g("retained_insert_done_i")
                if len(event)>1: log[lane].append(event)
        tx=json.load(gzip.open(old/"transactions.json.gz","rt"))
        overlapping = {}
        for kind,rows in (("AR",tx["BP_facing_reads"]),("AW",tx["BP_facing_writes"])):
            overlapping[kind]=[]
            for req in rows:
                first=req["request_time"]+(req["first_offer"]-req["request_cycle"])*50000
                finish=req["request_time"]+(req["complete"]-req["request_cycle"])*50000
                if req["request_time"]<end and finish>start:
                    overlapping[kind].append(dict(sequence=req["sequence"],address=req["addr"],request_time=req["request_time"],first_offer=first,complete=finish))
        results[case]=dict(admit=admit,publication=pub,UCE_PF_events=log,HP0_translations=translated,overlapping_HP0=overlapping,
            base_proof=hp.binding(old/"verification.json"),input_FST_archive=hp.binding(archive),selection=hp.binding(selection),events=hp.binding(out/"selected-events.tsv.gz"),command=cmd)
    (HERE/"localization.json").write_text(json.dumps(dict(scope="same closed traces; no target run",script=hp.binding(__file__),cases=results),indent=2)+"\n")
    for case,report in results.items():
        print(case)
        print(json.dumps(report,indent=2))


if __name__ == "__main__": main()
