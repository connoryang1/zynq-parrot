import unittest

import audit
import run


def sample(**changes):
    s = {key: 0 for key in run.selections(0, False)}
    s.update(resetn=1, arready=1, awready=1, wready=1, arsize=3, awsize=3,
             arburst=1, awburst=1, wstrb=255)
    for prefix in ("ext", "core"):
        s[prefix + ".rready"] = s[prefix + ".bready"] = 1
    s.update(changes)
    return s


def native_response(s, **changes):
    for key, value in changes.items():
        s["ext." + key] = s["core." + key] = value
    return s


def native_reads():
    return [sample(arvalid=1, arid=0, araddr=0x1000, arlen=1),
            sample(arvalid=1, arid=0, araddr=0x2000, arlen=0),
            native_response(sample(), rvalid=1, rid=0, rdata=0xaa, rlast=0),
            native_response(sample(), rvalid=1, rid=0, rdata=0xbb, rlast=1),
            native_response(sample(), rvalid=1, rid=0, rdata=0xcc, rlast=1)]


def run_native(rows):
    a = audit.Auditor(0)
    initial = sample(resetn=0)
    initial["ext.rvalid"] = 1
    a.step(0, initial)
    for n, row in enumerate(rows): a.step((n+1)*50000, row)
    return a, a.finish()


class AxiTests(unittest.TestCase):
    def test_same_id_fifo_and_ARLEN_last_and_clock(self):
        a, d = run_native(native_reads())
        self.assertEqual(d["clock_period_FST_ticks"], 50000)
        self.assertEqual(d["external"]["AR_transactions"], 2)
        self.assertEqual(d["external"]["max_same_ID_outstanding_reads_after_edge"], 2)
        self.assertEqual([r["beats"][0]["data"] for r in a.external.reads], [0xaa, 0xcc])
        self.assertEqual(d["external"]["AR_to_RLAST_complete_cycles"]["histogram"], {"3": 2})

    def test_RLAST_mismatch(self):
        rows = native_reads()
        native_response(rows[2], rlast=1)
        with self.assertRaisesRegex(ValueError, "RLAST"):
            run_native(rows)

    def test_unknown_RID(self):
        rows = native_reads()
        native_response(rows[2], rid=7)
        with self.assertRaisesRegex(ValueError, "without accepted AR"):
            run_native(rows)

    def test_stalled_payload_cannot_change(self):
        rows = native_reads()
        native_response(rows[2], rready=0)
        with self.assertRaisesRegex(ValueError, "held r changed"):
            run_native(rows)

    def test_unfinished_read_fails(self):
        with self.assertRaisesRegex(ValueError, "unfinished"):
            run_native(native_reads()[:-1])

    def test_native_all_fields_and_ready_identity(self):
        for key in ("rdata", "rid", "rlast", "rresp", "rready"):
            rows = native_reads()
            rows[2]["core." + key] ^= 1
            with self.assertRaises(ValueError): run_native(rows)

    def test_W_before_AW_and_B_timing(self):
        rows = native_reads()
        rows[0].update(wvalid=1, wid=3, wdata=0x88, wlast=1)
        rows[1].update(awvalid=1, awid=3, awaddr=0x4000, awlen=0)
        native_response(rows[2], bvalid=1, bid=3, bresp=0)
        _, d = run_native(rows)
        self.assertEqual(d["external"]["AW_to_B_accept_cycles"]["minimum"], 1)
        self.assertEqual(d["external"]["WLAST_to_B_accept_cycles"]["minimum"], 2)

    def test_B_before_last_W_fails(self):
        rows = native_reads()
        rows[0].update(awvalid=1, awid=3, awaddr=0x4000, awlen=0)
        native_response(rows[1], bvalid=1, bid=3, bresp=0)
        with self.assertRaisesRegex(ValueError, "before complete W"):
            run_native(rows)

    def test_reset_must_be_observed(self):
        a = audit.Auditor(0)
        for n, row in enumerate(native_reads()): a.step(n*50000, row)
        with self.assertRaisesRegex(ValueError, "observed AXI reset"):
            a.finish()

    def test_request_payload_held_until_accept(self):
        rows = native_reads()
        rows[0]["arready"] = 0
        with self.assertRaisesRegex(ValueError, "held ar changed"):
            run_native(rows)

    def test_different_RIDs_can_complete_out_of_order(self):
        rows = native_reads()
        rows[1]["arid"] = 1
        native_response(rows[2], rid=1, rlast=1, rdata=0xcc)
        native_response(rows[3], rid=0, rlast=0, rdata=0xaa)
        native_response(rows[4], rid=0, rlast=1, rdata=0xbb)
        a, _ = run_native(rows)
        self.assertEqual([r["complete"] for r in a.external.reads], [4,2])

    def test_AXI_reset_flush_is_explicit_and_old_response_cannot_survive(self):
        a = audit.Auditor(0)
        a.step(0, sample(resetn=0))
        a.step(50000, sample(arvalid=1, arlen=0, araddr=0x1000))
        a.step(100000, sample(resetn=0))
        with self.assertRaisesRegex(ValueError, "without accepted AR"):
            a.step(150000, native_response(sample(), rvalid=1, rid=0, rlast=1))
        self.assertEqual(a.discarded[0]["pending_AR"], 1)


def stream_rows(stall=False):
    rows = []
    for cycle in range(8 if stall else 6):
        s = sample()
        s.update({"shim.r.full": 0, "shim.r.full_stalls": 0})
        if cycle < 3:
            s.update({"ext.rvalid": 1, "ext.rdata": 10+cycle,
                      "ext.rid": cycle, "ext.rlast": int(cycle == 2)})
        if stall:
            occupancy = [0,1,2,3,3,3,2,1][cycle]
            output = {3:0, 4:0, 5:0, 6:1, 7:2}.get(cycle)
            s["core.rready"] = int(cycle not in (3,4))
        else:
            occupancy = [0,1,2,3,2,1][cycle]
            output = cycle-3 if cycle >= 3 else None
        s["shim.r.occupancy"] = occupancy
        if output is not None:
            s.update({"core.rvalid": 1, "core.rdata": 10+output,
                      "core.rid": output, "core.rlast": int(output == 2)})
        rows.append(s)
    return rows


class StreamTests(unittest.TestCase):
    def test_full_512_queue_backpressure_and_counter_conservation(self):
        stream = audit.DelayStream("r", 384)
        for cycle in range(1413):
            row = sample()
            occupancy = cycle if cycle < 512 else (512 if cycle <= 901 else 1413-cycle)
            row.update({"shim.r.occupancy": occupancy, "shim.r.full": int(occupancy == 512),
                        "shim.r.full_stalls": min(max(cycle-512,0),388),
                        "ext.rvalid": int(cycle <= 900), "ext.rready": int(cycle < 512 or cycle >= 900),
                        "core.rready": int(cycle >= 900)})
            if cycle <= 900:
                word = min(cycle,512)
                row.update({"ext.rid": word%64, "ext.rdata": word*123+7, "ext.rlast": int(word%8 == 7)})
            if cycle >= 384:
                word = max(cycle-900,0)
                row.update({"core.rvalid":1,"core.rid":word%64,"core.rdata":word*123+7,
                            "core.rlast":int(word%8 == 7)})
            stream.step(cycle,row)
        summary = stream.finish()
        self.assertEqual(summary["beats"], 513)
        self.assertEqual(summary["max_occupancy"], 512)
        self.assertEqual(summary["full_input_stall_cycles"], 388)
        self.assertEqual(summary["downstream_output_stall_cycles"], 516)

    def test_exact_age_preserves_every_opaque_field_and_spacing(self):
        s = audit.DelayStream("r", 3)
        for cycle, row in enumerate(stream_rows()): s.step(cycle, row)
        d = s.finish()
        self.assertEqual(d["input_accept_to_first_output_offer_cycles"]["histogram"], {"3": 3})
        self.assertEqual([b["output_cycle"] for b in s.completed], [3,4,5])

    def test_READY_does_not_delay_offer_but_delays_accept_and_following_head(self):
        s = audit.DelayStream("r", 3)
        for cycle, row in enumerate(stream_rows(True)): s.step(cycle, row)
        d = s.finish()
        self.assertEqual(s.completed[0]["first_offer_cycle"], 3)
        self.assertEqual(s.completed[0]["output_cycle"], 5)
        self.assertEqual(s.completed[1]["first_offer_cycle"], 6)
        self.assertEqual(d["downstream_output_stall_cycles"], 2)

    def test_each_opaque_field_corruption_rejected(self):
        for key in audit.R_FIELDS:
            rows = stream_rows()
            rows[3]["core." + key] ^= 1
            s = audit.DelayStream("r", 3)
            with self.assertRaisesRegex(ValueError, "payload/order"):
                for cycle, row in enumerate(rows): s.step(cycle, row)

    def test_early_and_late_offer_rejected(self):
        rows = stream_rows()
        rows[3]["core.rvalid"] = 0
        s = audit.DelayStream("r", 3)
        with self.assertRaisesRegex(ValueError, "eligible head failed"):
            for cycle, row in enumerate(rows): s.step(cycle, row)
        rows = stream_rows()
        rows[2].update({"core.rvalid":1,"core.rdata":10})
        s = audit.DelayStream("r", 3)
        with self.assertRaisesRegex(ValueError, "before N"):
            for cycle, row in enumerate(rows): s.step(cycle, row)

    def test_occupancy_and_counter_wrong_rejected(self):
        for key in ("shim.r.occupancy", "shim.r.full_stalls", "shim.r.full"):
            rows = stream_rows()
            rows[2][key] ^= 1
            s = audit.DelayStream("r", 3)
            with self.assertRaises(ValueError):
                for cycle, row in enumerate(rows): s.step(cycle, row)

    def test_B_all_fields_exact_age(self):
        s = audit.DelayStream("b", 2)
        for cycle in range(3):
            row = sample()
            row.update({"shim.b.occupancy": int(cycle > 0), "shim.b.full":0,"shim.b.full_stalls":0})
            if cycle == 0: row.update({"ext.bvalid":1,"ext.bid":5,"ext.bresp":2})
            if cycle == 2: row.update({"core.bvalid":1,"core.bid":5,"core.bresp":2})
            s.step(cycle, row)
        self.assertEqual(s.finish()["beats"],1)

    def test_preedge_FST_grouping_with_alias_clock(self):
        expected = {"clk":("x.clk",1),"i.clk":("x.alias",1),"value":("x.value",2)}
        lines = ["#FST\t0\t20\t-12\n", "#SIGNAL\tclk\t1\t1\tTOP.x.clk\n",
                 "#SIGNAL\ti.clk\t1\t1\tTOP.x.alias\n", "#SIGNAL\tvalue\t2\t2\tTOP.x.value\n",
                 "0\t1\t0\n","0\t2\t01\n","10\t1\t1\n","10\t2\t10\n","#END\n"]
        rows = list(run.edge_samples(lines, expected))
        self.assertEqual(rows[0][2]["value"],1)
        self.assertEqual(set(rows[0][1]),{"clk","i.clk"})

    def test_UCE_endpoint_ACK_does_not_become_HP0_source_claim(self):
        endpoint = audit.UceEndpoints("i")
        fields = {key:0 for key in run.selections(0,True)}
        fields["i.reset"] = 1
        endpoint.step(0,fields)
        fields.update({"i.reset":0,"i.reqv":1,"i.reqy":1,"i.reqtype":0,"i.reqaddr":0x80001000})
        endpoint.step(10,fields)
        fields.update({"i.reqv":0,"i.reqy":0,"i.aborted":1,"i.datav":1,"i.datay":1,"i.opcode":0})
        for word in range(8):
            fields.update({"i.dataaddr":0x80001000+word*8,"i.fill":1<<word,"i.last":int(word==7)})
            endpoint.step(20+word,fields)
        summary=endpoint.finish()
        self.assertEqual(summary["completed_requests"],1)
        self.assertEqual(summary["aborted_I_ACK_bursts"],1)
        self.assertIn("No HP0 source-class association",summary["limits"])


if __name__ == "__main__": unittest.main()
