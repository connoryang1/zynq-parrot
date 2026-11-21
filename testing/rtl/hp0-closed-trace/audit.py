"""Clocked AXI HP0 protocol, timing and opaque response-stream checks.

Cycle counts use the observed AXI clock. They are simulator observations, not
physical calibration, DRAM latency settings or application projections.
"""
from collections import Counter, defaultdict, deque


def require(condition, message):
    if not condition:
        raise ValueError(message)


R_FIELDS = ("rid", "rdata", "rresp", "rlast")
B_FIELDS = ("bid", "bresp")
REQUEST_FIELDS = ("id", "addr", "len", "size", "burst", "lock", "cache", "prot", "qos")


def distribution(values):
    counts = Counter(values)
    return {"count": len(values), "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
            "histogram": {str(k): counts[k] for k in sorted(counts)}}


class Bus:
    """AR/R FIFO per RID; AW/W/B FIFO per ID (including W-before-AW)."""
    def __init__(self, name):
        self.name = name
        self.reads, self.writes = [], []
        self.rq, self.bq, self.wq = defaultdict(deque), defaultdict(deque), defaultdict(deque)
        self.held = {}
        self.max_reads = self.max_writes = self.same_id_overlap = 0
        self.max_reads_per_id = 0
        self.rbeats, self.bbeats = [], []
        self.stalls = Counter()

    def stable(self, channel, valid, ready, payload):
        if channel in self.held:
            require(valid and payload == self.held[channel], self.name + " held " + channel + " changed")
        if valid and not ready:
            self.held[channel] = payload
            self.stalls[channel] += 1
        else:
            self.held.pop(channel, None)

    def step(self, cycle, time, s, response_prefix):
        def get(key):
            value = s.get(key)
            require(value is not None, "unknown initialized AXI signal " + key)
            return value
        def response(key):
            return get(response_prefix + "." + key)
        for channel, queue, records in (("ar", self.rq, self.reads), ("aw", self.bq, self.writes)):
            valid, ready = get(channel + "valid"), get(channel + "ready")
            fields = {field: get(channel + field) for field in REQUEST_FIELDS} if valid else {}
            self.stable(channel, valid, ready, tuple(fields.values()))
            if valid and ready:
                require(0 <= fields["len"] <= 255 and 0 <= fields["size"] <= 3,
                        "invalid HP0 length/size")
                require(fields["burst"] in (0, 1, 2), "reserved AXI burst")
                if channel == "ar" and queue[fields["id"]]:
                    self.same_id_overlap += 1
                request = dict(fields, sequence=len(records), request_cycle=cycle,
                    request_time=time, first_offer=None, first_accept=None, complete=None,
                    offered_last=None, beats=[], wbeats=[])
                records.append(request); queue[fields["id"]].append(request)
        valid, ready = get("wvalid"), get("wready")
        wpayload = tuple(get(key) for key in ("wid", "wdata", "wstrb", "wlast")) if valid else ()
        self.stable("w", valid, ready, wpayload)
        if valid and ready:
            self.wq[wpayload[0]].append(dict(cycle=cycle, time=time, id=wpayload[0],
                                            data=wpayload[1], strb=wpayload[2], last=wpayload[3]))
        for ident, waiting in self.wq.items():
            for request in self.bq[ident]:
                while waiting and len(request["wbeats"]) < request["len"] + 1:
                    beat = waiting.popleft()
                    require(beat["last"] == int(len(request["wbeats"]) == request["len"]),
                            self.name + " WLAST/length mismatch")
                    request["wbeats"].append(beat)
        valid, ready = response("rvalid"), response("rready")
        payload = tuple(response(key) for key in R_FIELDS) if valid else ()
        self.stable("r", valid, ready, payload)
        if valid:
            ident, data, resp, last = payload
            require(self.rq[ident], self.name + " R without accepted AR for RID")
            request = self.rq[ident][0]
            require(resp == 0, self.name + " read response error")
            require(last == int(len(request["beats"]) == request["len"]),
                    self.name + " RLAST/ARLEN mismatch")
            if request["first_offer"] is None:
                request["first_offer"] = cycle
            if last and request["offered_last"] is None:
                request["offered_last"] = cycle
            if ready:
                if request["first_accept"] is None:
                    request["first_accept"] = cycle
                beat = dict(cycle=cycle, time=time, id=ident, data=data, resp=resp,
                            last=last, request_sequence=request["sequence"])
                request["beats"].append(beat); self.rbeats.append(beat)
                if last:
                    request["complete"] = cycle
                    self.rq[ident].popleft()
        valid, ready = response("bvalid"), response("bready")
        payload = tuple(response(key) for key in B_FIELDS) if valid else ()
        self.stable("b", valid, ready, payload)
        if valid:
            ident, resp = payload
            require(self.bq[ident], self.name + " B without accepted AW for BID")
            request = self.bq[ident][0]
            require(len(request["wbeats"]) == request["len"] + 1, self.name + " B before complete W burst")
            require(resp == 0, self.name + " write response error")
            if request["first_offer"] is None:
                request["first_offer"] = cycle
            if ready:
                request["first_accept"] = request["complete"] = cycle
                self.bbeats.append(dict(cycle=cycle, time=time, id=ident, resp=resp,
                                       request_sequence=request["sequence"]))
                self.bq[ident].popleft()
        self.max_reads = max(self.max_reads, sum(map(len, self.rq.values())))
        self.max_reads_per_id = max([self.max_reads_per_id] + [len(q) for q in self.rq.values()])
        self.max_writes = max(self.max_writes, sum(map(len, self.bq.values())))

    def finish(self):
        require(not any(self.rq.values()) and not any(self.bq.values()) and not any(self.wq.values()),
                self.name + " closed trace has unfinished AXI transactions")
        reads = self.reads
        return {"AR_transactions": len(reads), "AW_transactions": len(self.writes),
            "accepted_R_beats": len(self.rbeats), "accepted_B_responses": len(self.bbeats),
            "ARLEN": distribution([r["len"] for r in reads]),
            "read_bytes_per_beat": distribution([1 << r["size"] for r in reads]),
            "read_ID": distribution([r["id"] for r in reads]),
            "AR_to_first_R_offer_cycles": distribution([r["first_offer"] - r["request_cycle"] for r in reads]),
            "AR_to_first_R_accept_cycles": distribution([r["first_accept"] - r["request_cycle"] for r in reads]),
            "AR_to_RLAST_complete_cycles": distribution([r["complete"] - r["request_cycle"] for r in reads]),
            "AW_to_B_offer_cycles": distribution([r["first_offer"] - r["request_cycle"] for r in self.writes]),
            "AW_to_B_accept_cycles": distribution([r["complete"] - r["request_cycle"] for r in self.writes]),
            "WLAST_to_B_accept_cycles": distribution([r["complete"] - r["wbeats"][-1]["cycle"] for r in self.writes]),
            "within_burst_R_accept_gaps_cycles": distribution([b["cycle"]-a["cycle"] for r in reads
                for a, b in zip(r["beats"], r["beats"][1:])]),
            "max_outstanding_reads_after_edge": self.max_reads,
            "max_same_ID_outstanding_reads_after_edge": self.max_reads_per_id,
            "same_ID_AR_accepted_while_pending": self.same_id_overlap,
            "max_outstanding_writes_after_edge": self.max_writes, "stalled_cycles": dict(self.stalls)}


class DelayStream:
    def __init__(self, channel, delay):
        self.channel, self.delay = channel, delay
        self.pending, self.completed = deque(), []
        self.last_pop = -1
        self.max_occupancy = self.full_cycles = self.input_stalls = self.output_stalls = 0

    def step(self, cycle, s):
        channel = self.channel
        fields = R_FIELDS if channel == "r" else B_FIELDS
        get = lambda key: s[key]
        vi, ri = get("ext." + channel + "valid"), get("ext." + channel + "ready")
        vo, ro = get("core." + channel + "valid"), get("core." + channel + "ready")
        pi = tuple(get("ext." + key) for key in fields) if vi else ()
        po = tuple(get("core." + key) for key in fields) if vo else ()
        if self.delay == 0:
            require(vi == vo and ri == ro and (not vi or pi == po), "native response wire mismatch")
            if vi and ri:
                self.completed.append(dict(input_cycle=cycle, first_offer_cycle=cycle, output_cycle=cycle, payload=pi))
            return
        prefix = "shim." + channel + "."
        occupancy = len(self.pending)
        require(get(prefix + "occupancy") == occupancy, channel + " shim occupancy/conservation mismatch")
        require(get(prefix + "full") == int(occupancy == 512), channel + " shim full flag mismatch")
        require(get(prefix + "full_stalls") == min(self.input_stalls, 0xffffffff), channel + " full-stall counter mismatch")
        self.max_occupancy = max(self.max_occupancy, occupancy)
        self.full_cycles += int(occupancy == 512)
        self.input_stalls += int(vi and not ri)
        self.output_stalls += int(vo and not ro)
        if vi and ri:
            self.pending.append(dict(input_cycle=cycle, first_offer_cycle=None, payload=pi))
        if vo:
            require(self.pending, channel + " output without accepted input")
            head = self.pending[0]
            require(po == head["payload"], channel + " opaque response payload/order changed")
            require(cycle - head["input_cycle"] >= self.delay, channel + " response offered before N-cycle age")
            if head["first_offer_cycle"] is None:
                head["first_offer_cycle"] = cycle
                deadline = max(head["input_cycle"] + self.delay, self.last_pop + 1)
                require(cycle == deadline, channel + " eligible head has an extra/missing offer cycle")
            if ro:
                head["output_cycle"] = cycle
                self.completed.append(self.pending.popleft())
                self.last_pop = cycle
        elif self.pending:
            deadline = max(self.pending[0]["input_cycle"] + self.delay, self.last_pop + 1)
            require(cycle < deadline, channel + " eligible head failed to offer independently of READY")

    def finish(self):
        require(not self.pending, self.channel + " closed trace has buffered undelivered responses")
        return {"beats": len(self.completed), "minimum_age_setting": self.delay,
            "input_accept_to_first_output_offer_cycles": distribution([
                b["first_offer_cycle"]-b["input_cycle"] for b in self.completed]),
            "input_accept_to_output_accept_cycles": distribution([
                b["output_cycle"]-b["input_cycle"] for b in self.completed]),
            "max_occupancy": self.max_occupancy, "full_cycles": self.full_cycles,
            "full_input_stall_cycles": self.input_stalls, "downstream_output_stall_cycles": self.output_stalls}


class Auditor:
    def __init__(self, delay):
        require(0 <= delay <= 384, "unsupported static delay")
        self.delay = delay
        self.reset_seen = False
        self.epochs, self.discarded = [], []
        self.clear()

    def clear(self):
        self.cycle = 0
        self.external, self.core = Bus("external"), Bus("BP-facing")
        self.streams = [DelayStream(channel, self.delay) for channel in ("r", "b")]
        self.times = []

    def step(self, time, s):
        resetn = s.get("resetn")
        if resetn is None:
            require(not self.reset_seen, "unknown AXI reset after initialization")
            return
        if not resetn:
            if not self.reset_seen or self.cycle:
                self.epochs.append({"reset_asserted_at": time})
                if self.cycle:
                    self.discarded.append({"cycles": self.cycle,
                        "AR_transactions": len(self.external.reads), "AW_transactions": len(self.external.writes),
                        "pending_AR": sum(map(len, self.external.rq.values())),
                        "buffered_R": len(self.streams[0].pending), "buffered_B": len(self.streams[1].pending)})
            self.reset_seen = True
            self.clear()
            return
        if not self.reset_seen:
            return
        if self.delay:
            require(s["shim.delay"] == self.delay and s["shim.cycle"] == (self.cycle & 0xffffffff),
                    "shim static delay/cycle identity mismatch")
        self.external.step(self.cycle, time, s, "ext")
        self.core.step(self.cycle, time, s, "core")
        for stream in self.streams:
            stream.step(self.cycle, s)
        self.times.append(time)
        self.cycle += 1

    def finish(self):
        require(self.reset_seen and self.cycle > 1, "missing observed AXI reset/clock interval")
        require(self.external.reads, "no accepted HP0 reads in final reset epoch")
        periods = [b-a for a, b in zip(self.times, self.times[1:])]
        require(len(set(periods)) == 1 and periods[0] > 0, "AXI clock period changed")
        return {"accepted": True, "scope": "closed simulator HP0 timing/response-integrity verification",
            "clock_period_FST_ticks": periods[0], "observed_cycles": self.cycle,
            "static_response_beat_minimum_age_cycles": self.delay,
            "external": self.external.finish(), "BP_facing": self.core.finish(),
            "R_stream": self.streams[0].finish(), "B_stream": self.streams[1].finish(),
            "reset_epochs": self.epochs, "discarded_on_actual_AXI_reset": self.discarded,
            "limits": ["AR-to-response is observed memory-path timing; N is age since shim beat acceptance, not DRAM latency",
                "Shared RID0 does not identify I/D demand or prefetch origin",
                "Per-ID FIFO response association follows AXI ordering; no external-memory data oracle",
                "Opaque before/after response equality checks every ID/data/response/LAST field",
                "No physical calibration, FPGA or application-performance projection"]}


class UceEndpoints:
    """Separate per-lane cache request/refill endpoints; never joined to RID0."""
    def __init__(self, lane):
        self.lane = lane
        self.reset_seen = False
        self.pending, self.completed, self.advisories, self.publications = deque(), [], [], []

    def step(self, time, s):
        g = lambda key: s[self.lane + "." + key]
        if g("reset") is None:
            require(not self.reset_seen, "unknown UCE reset after initialization")
            return
        if g("reset"):
            self.reset_seen = True
            self.pending.clear(); self.completed.clear(); self.advisories.clear(); self.publications.clear()
            return
        if not self.reset_seen:
            return
        if g("reqv") and g("reqy"):
            if g("reqtype") in (0, 1):
                self.pending.append(dict(request_time=time, address=g("reqaddr"),
                    request_type=g("reqtype"), first_offer=None, first_accept=None,
                    complete=None, mask=0, beats=0, aborted=False, source_states=[]))
            elif g("reqtype") == 9:
                self.advisories.append(dict(time=time, address=g("reqaddr") & ~63, kind="cache-prefetch"))
        for kind in ("detached", "preview"):
            if g(kind + "v") and g(kind + "ready"):
                self.advisories.append(dict(time=time, address=g(kind + "addr") & ~63, kind=kind))
        if g("published") and g("done") and g("owned") and g("pf"):
            address = g("owned_addr")
            candidates = [r for r in self.advisories if r["address"] == address and r["time"] < time]
            self.publications.append(dict(time=time, address=address,
                advisory=candidates[-1] if candidates else None))
        if not self.pending:
            return
        request = self.pending[0]
        if self.lane == "i" and g("aborted"):
            request["aborted"] = True
        if not (g("datav") and g("opcode") == 0 and (g("dataaddr") & ~63) == (request["address"] & ~63)):
            return
        if request["first_offer"] is None:
            request["first_offer"] = time
        if not g("datay"):
            return
        if request["first_accept"] is None:
            request["first_accept"] = time
        mask = g("fill")
        require(mask and not (mask & (mask - 1)) and not (request["mask"] & mask), "UCE duplicate/non-word refill mask")
        request["mask"] |= mask
        request["beats"] += 1
        if g("state") not in request["source_states"]:
            request["source_states"].append(g("state"))
        if g("last"):
            require(request["mask"] == 255 and request["beats"] == 8, "UCE completed without full eight ACK beats")
            request["complete"] = time
            self.completed.append(self.pending.popleft())

    def finish(self):
        return {"completed_requests": len(self.completed), "unfinished_requests": list(self.pending),
            "request_to_first_ACK_FST_ticks": distribution([r["first_accept"]-r["request_time"] for r in self.completed]),
            "request_to_complete_ACK_FST_ticks": distribution([r["complete"]-r["request_time"] for r in self.completed]),
            "aborted_I_ACK_bursts": sum(r["aborted"] for r in self.completed),
            "advisory_publications": self.publications,
            "limits": "UCE ACK endpoint includes aborted instruction discards; real-writing retained fixture is separately trace-gated. No HP0 source-class association."}
