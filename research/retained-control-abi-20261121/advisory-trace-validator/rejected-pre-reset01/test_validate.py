import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("advisory_validate", Path(__file__).with_name("validate.py"))
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

WORDS = {"i": [0x1234000000000000 + w for w in range(8)],
         "d": [0x5678000000000000 + w for w in range(8)]}
MARKERS = {"submit": 0x8000b25c, "demand": 0x8000b26e, "completed": 0x8000b2da}


def fixture(aborted_first=False):
    samples = []
    def sample(t, clocks, changes):
        values = {key: 0 for key in v.selections()}
        values["control"] = 3
        values.update(changes)
        for n, lane in enumerate(("i", "d")):
            for key in ("lv", "lr", "rv", "rr", "rh", "iv", "ir", "done", "published"):
                values["store." + key] |= values[lane + "." + key] << n
            for key in ("la", "rd", "ia", "id"):
                values["store." + lane + "." + key] = values[lane + "." + key]
        samples.append((t, clocks, values))
    def retire(t, pc):
        data = {"be.instret": 1, "be.pc": pc}
        if v.CODE <= pc < v.CODE + 64:
            instruction = (WORDS["i"][(pc - v.CODE) // 8] >> ((pc & 7) * 8)) & 0xffffffff
            shift = 32
            for field, width in (("funct7", 7), ("rs2_addr", 5), ("rs1_addr", 5),
                                 ("funct3", 3), ("rd_addr", 5), ("opcode", 7)):
                shift -= width
                data["be.instr." + field] = (instruction >> shift) & ((1 << width) - 1)
        sample(t, ["be.clk"], data)
    retire(10, MARKERS["submit"])
    for lane, offset, address in (("i", 0, v.CODE), ("d", 1, v.DATA)):
        def put(t, changes, clock="bclk"):
            sample(t + offset, [lane + "." + clock], {lane + "." + k: val for k, val in changes.items()})
        payload = sum(x << (64 * w) for w, x in enumerate(WORDS[lane]))
        put(20, {"iv": 1, "ir": 1, "ia": address, "id": payload})
        put(30, {"done": 1, "published": 1, "owned": 1, "pf": 1,
                 "owned_addr": address, "enable": 1})
        def response(start):
            put(start, {"lv": 1, "lr": 1, "la": address})
            put(start + 10, {"rv": 1, "rr": 1, "rh": 1, "rd": payload})
        def burst(start, abort):
            way = 2 if lane == "i" else 5
            req = address if lane == "i" else address + 24
            for w in range(8):
                bank = (way + w) % 8
                data = {"v": 1, "yumi": 1, "state": 22,
                        "pkt.addr": address + 8 * w, "pkt.index": (address >> 6) & 63,
                        "pkt.way_id": way, "pkt.data": WORDS[lane][w],
                        "pkt.fill_index": 1 << w, "pkt.opcode": 0,
                        "slow": 0 if abort else 1 << bank, "req_addr": req,
                        "mem_v": 1 << bank, "mem_w": 1 << bank,
                        "mem.addr." + str(bank): ((address >> 6) & 63) * 8 + w,
                        "mem.data." + str(bank): WORDS[lane][w],
                        "mem.mask." + str(bank): 255,
                        "critical": int(w == ((req >> 3) & 7)), "last": int(w == 7),
                        "tv": int(w == 0), "ty": int(w == 0),
                        "tag.opcode": 1, "tag.index": (address >> 6) & 63,
                        "tag.way_id": way, "tag.tag": address >> 12, "tag.state": 6}
                if abort:
                    data["abort_miss_r"] = 1
                put(start + 10 * w, data, "cclk")
        response(40)
        burst(60, aborted_first and lane == "i")
        if aborted_first and lane == "i":
            response(140)
            burst(160, False)
    # FE backend HIT precedes retired BE demand marker by construction.
    retire(55, MARKERS["demand"])
    for n in range(16):
        retire(250 + n, v.CODE + n * 4)
    retire(300, MARKERS["completed"])
    return sorted(samples, key=lambda row: row[0])


def run(samples):
    check = v.Validator(WORDS, MARKERS)
    for row in samples:
        check.sample(*row)
    return check.finish()


class ValidationTests(unittest.TestCase):
    def test_good_both_lanes_actual_writes_and_early_fe_hit(self):
        report = run(fixture())
        self.assertTrue(report["accepted"])
        self.assertLess(report["lanes"]["i"]["hits"][0]["time"], report["markers"]["demand"])
        self.assertEqual(len(report["cold_function_retirement"]), 16)
        self.assertEqual([b["word"] for b in report["lanes"]["d"]["bursts"][0]["beats"]], list(range(8)))

    def test_aborted_ack_burst_discarded_then_real_winner(self):
        report = run(fixture(True))
        self.assertEqual(len(report["lanes"]["i"]["discarded"]), 1)
        self.assertEqual(len(report["lanes"]["i"]["bursts"]), 1)

    def test_only_aborted_ack_burst_cannot_pass(self):
        rows = fixture()
        for _, clocks, d in rows:
            if "i.cclk" in clocks:
                d["i.abort_miss_r"] = 1
                d["i.slow"] = 0
        with self.assertRaisesRegex(ValueError, "winning L1 fill"):
            run(rows)

    def test_corrupt_accepted_full_payload_fails(self):
        rows = fixture()
        next(d for _, _, d in rows if d["d.rv"])["d.rd"] ^= 1 << 511
        d = next(d for _, _, d in rows if d["d.rv"])
        d["store.d.rd"] = d["d.rd"]
        with self.assertRaisesRegex(ValueError, "512-bit"):
            run(rows)

    def test_demand_publication_not_advisory(self):
        rows = fixture()
        next(d for _, _, d in rows if d["i.published"])["i.pf"] = 0
        with self.assertRaisesRegex(ValueError, "PF-owned"):
            run(rows)

    def test_nonzero_demand_copy_fails(self):
        rows = fixture()
        next(d for _, _, d in rows if d["d.published"])["d.demand_copy"] = 1
        with self.assertRaisesRegex(ValueError, "advisory-only"):
            run(rows)

    def test_no_lookup_acceptance_fails(self):
        rows = fixture()
        next(d for _, _, d in rows if d["i.lv"])["i.lr"] = 0
        next(d for _, _, d in rows if d["i.lv"])["store.lr"] = 0
        with self.assertRaisesRegex(ValueError, "response without"):
            run(rows)

    def test_wrong_actual_sram_data_fails_even_correct_packet(self):
        rows = fixture()
        d = next(d for _, _, d in rows if d["d.pkt.fill_index"] == 8)
        bank = (d["d.pkt.way_id"] + 3) % 8
        d["d.mem.data." + str(bank)] ^= 1
        with self.assertRaisesRegex(ValueError, "actual SRAM data"):
            run(rows)

    def test_critical_d_word_zero_rejected(self):
        rows = fixture()
        for _, clocks, d in rows:
            if "d.cclk" in clocks:
                d["d.req_addr"] = v.DATA
                d["d.critical"] = int(d["d.pkt.fill_index"] == 1)
        with self.assertRaisesRegex(ValueError, "offset3"):
            run(rows)

    def test_missing_instruction_retirement_fails(self):
        rows = [r for r in fixture() if r[2]["be.pc"] != v.CODE + 20]
        with self.assertRaisesRegex(ValueError, "16 instructions"):
            run(rows)

    def test_corrupt_retired_instruction_fails(self):
        rows = fixture()
        next(d for _, _, d in rows if d["be.pc"] == v.CODE)["be.instr.opcode"] ^= 1
        with self.assertRaisesRegex(ValueError, "retirement payload"):
            run(rows)

    def test_backend_client_alias_mismatch_fails(self):
        rows = fixture()
        next(d for _, _, d in rows if d["d.rv"])["store.rh"] = 0
        with self.assertRaisesRegex(ValueError, "backend/client"):
            run(rows)

    def test_wrong_fill_mask_or_last_or_way_fails(self):
        for key in ("i.pkt.fill_index", "i.last", "i.pkt.way_id"):
            rows = fixture()
            d = next(d for _, _, d in rows if d["i.pkt.fill_index"] == 16)
            d[key] ^= 1
            with self.assertRaises(ValueError):
                run(rows)

    def test_missing_tag_write_fails(self):
        rows = fixture()
        next(d for _, _, d in rows if d["i.tv"])["i.ty"] = 0
        with self.assertRaisesRegex(ValueError, "tag write"):
            run(rows)

    def test_unknown_actual_write_fails(self):
        rows = fixture()
        next(d for _, _, d in rows if d["i.tv"])["i.slow"] = None
        with self.assertRaisesRegex(ValueError, "unknown"):
            run(rows)

    def test_timestamp_grouping_uses_preedge_not_postedge_and_aliases(self):
        selection = v.selections()
        handles = {key: n + 1 for n, key in enumerate(selection)}
        # Alias clocks, as the actual FST does.
        handles["be.clk"] = handles["i.bclk"] = handles["i.cclk"]
        lines = ["#FST\t0\t20\t-12\n"]
        for key, (suffix, width) in selection.items():
            lines.append("#SIGNAL\t{}\t{}\t{}\tTOP.{}\n".format(key, width, handles[key], suffix))
        sent = set()
        for key, (_, width) in selection.items():
            if handles[key] not in sent:
                sent.add(handles[key])
                lines.append("0\t{}\t{}\n".format(handles[key], "0" * width))
        lines += ["5\t{}\t0011\n".format(handles["control"]),
                  "10\t{}\t1\n".format(handles["i.cclk"]),
                  "10\t{}\t0000\n".format(handles["control"]), "#END\n"]
        samples = list(v.edge_samples(lines))
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0][2]["control"], 3)
        self.assertEqual(set(samples[0][1]), {"be.clk", "i.bclk", "i.cclk"})
        with self.assertRaisesRegex(ValueError, "incomplete"):
            list(v.edge_samples(lines[:-1]))


if __name__ == "__main__":
    unittest.main()
