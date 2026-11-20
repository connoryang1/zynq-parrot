#!/usr/bin/env python3
"""Conditional I/D miss-stream capacity and shared-response service model.

This is an event model, not an RTL simulator or Linux execution predictor.
Physical recorder inputs contain misses only. Their arrivals remain fixed;
missing cache hits, dependencies and completion timestamps are not invented.
"""
from __future__ import annotations

import argparse
from collections import Counter, OrderedDict, deque
from dataclasses import asdict, dataclass, field
import hashlib
import heapq
import json
import lzma
from pathlib import Path
from itertools import zip_longest


LINE_BYTES = 64
SIDES = ("I", "D")
MODES = ("base", "demand-retained", "retained-prefix", "preseed", "continuous")


@dataclass(frozen=True)
class Access:
    cycle: int
    side: str
    address: int


@dataclass(frozen=True)
class Trace:
    path: str
    sha256: str
    elapsed: int
    accesses: tuple[Access, ...]
    post_boundary_records: int = 0


@dataclass(frozen=True)
class Timing:
    first_response: int = 41
    beats: int = 8
    cycles_per_beat: int = 1
    install: int = 19
    replay_slots: int = 4
    trigger_cost: int = 0

    def __post_init__(self):
        if min(self.first_response, self.install, self.trigger_cost) < 0:
            raise ValueError("latency, installation and trigger cost must be nonnegative")
        if min(self.beats, self.cycles_per_beat, self.replay_slots) < 1:
            raise ValueError("beats, beat interval and replay slots must be positive")


@dataclass
class Transaction:
    side: str
    address: int
    replay: bool
    issue: int
    waiters: list[Access] = field(default_factory=list)
    response_end: int | None = None
    consumed: bool = False


class SideStore:
    """Equal-capacity per-side fully associative LRU approximation.

    The archived RTL is banked, whereas this deliberately isolates capacity.
    No claim about exact RTL collision/replacement behavior follows.
    """
    def __init__(self, capacities):
        self.capacities = capacities
        self.entries = {side: OrderedDict() for side in SIDES}

    def lookup(self, side, address):
        entries = self.entries[side]
        if address not in entries:
            return False
        entries.move_to_end(address)
        return True

    def fill(self, side, address, origin=None):
        if not self.capacities[side]:
            return
        entries = self.entries[side]
        entries.pop(address, None)
        entries[address] = origin
        while len(entries) > self.capacities[side]:
            entries.popitem(last=False)


def parse_trace(path):
    """Fail closed on truncated/overflow input; exclude recorder disarm tail."""
    path = Path(path)
    stored = path.read_bytes()
    raw = lzma.decompress(stored) if path.suffix == ".xz" else stored
    header = None
    accesses = []
    passed = False
    for line in raw.decode().replace("\r", "").splitlines():
        if line.startswith("TRACE_HEADER "):
            if header is not None:
                raise ValueError("multiple TRACE_HEADER records")
            header = dict(item.split("=", 1) for item in line.split()[1:])
        elif line.startswith("TRACE_RECORD "):
            fields = dict(item.split("=", 1) for item in line.split()[1:])
            side = fields["side"]
            if side not in SIDES:
                raise ValueError("unknown demand side")
            address = int(fields["paddr"], 0)
            accesses.append(Access(int(fields["relative"], 0), side,
                                   address & ~(LINE_BYTES - 1)))
        elif line.startswith("TRACE_PASS "):
            passed = True
        elif line.startswith("TRACE_TRUNCATED"):
            raise ValueError("truncated trace")
    if header is None or not passed:
        raise ValueError("missing complete trace header/PASS")
    for key in ("i_overflow", "d_overflow", "armed"):
        if int(header[key], 0):
            raise ValueError("trace overflow or recorder still armed")
    expected = int(header["i_count"]) + int(header["d_count"])
    if expected != len(accesses):
        raise ValueError("trace record count mismatch")
    for side, key in (("I", "i_count"), ("D", "d_count")):
        if sum(a.side == side for a in accesses) != int(header[key]):
            raise ValueError("trace side count mismatch")
    if accesses != sorted(accesses, key=lambda a: a.cycle):
        raise ValueError("demand arrivals must be ordered")
    elapsed = int(header["elapsed"])
    if elapsed <= 0 or any(a.cycle < 0 for a in accesses):
        raise ValueError("invalid trace interval")
    kept = tuple(a for a in accesses if a.cycle <= elapsed)
    return Trace(str(path), hashlib.sha256(raw).hexdigest(), elapsed,
                 kept, len(accesses) - len(kept))


def prefixes(training, capacities):
    result = {side: [] for side in SIDES}
    seen = {side: set() for side in SIDES}
    for a in training:
        if a.address not in seen[a.side]:
            seen[a.side].add(a.address)
            if len(result[a.side]) < capacities[a.side]:
                result[a.side].append(a.address)
    return result


class Simulation:
    """One demand MSHR per I/D side, shared nonpreemptive response bus.

    First-response latency represents concurrent transport, independent of bus
    beat throughput. Ready demands have response priority, but cannot preempt
    an already-started replay burst. Installation is serial within each side.
    Demands join matching in-flight replay; replay admission suppresses hits
    and matching transactions. Every outstanding response is drained at end.
    """
    def __init__(self, timing, capacities, mode, training=()):
        if mode not in MODES:
            raise ValueError("unknown mechanism")
        if any(capacities[s] < 0 for s in SIDES):
            raise ValueError("negative side capacity")
        self.timing, self.mode = timing, mode
        self.store = SideStore(capacities if mode != "base" else dict.fromkeys(SIDES, 0))
        self.prefix = prefixes(training, capacities)
        if mode == "demand-retained":
            for a in training:
                self.store.fill(a.side, a.address)
        elif mode == "retained-prefix":
            # Identical tags/capacity to speculative prefix; the prior epoch
            # demand-populates and pins its first C unique lines. This is a
            # capacity/content control, not implemented retention hardware.
            for side in SIDES:
                for address in self.prefix[side]:
                    self.store.fill(side, address)
        self.events = []
        self.serial = 0
        self.now = 0
        self.stats = Counter()
        self.by_side = {s: Counter() for s in SIDES}
        self.waiting = {s: deque() for s in SIDES}
        self.demand_busy = dict.fromkeys(SIDES, False)
        self.install_free = dict.fromkeys(SIDES, 0)
        self.inflight = {}
        self.response_ready = []
        self.bus_busy = False
        self.replay_queue = deque()
        self.replay_active = 0
        self.replay_transactions = []
        self.last_demand = 0
        self.last_completion = 0
        self.last_replay = 0

    def event(self, when, kind, value=None):
        self.serial += 1
        heapq.heappush(self.events, (when, self.serial, kind, value))

    def issue(self, side, address, replay, access=None):
        tx = Transaction(side, address, replay, self.now,
                         [] if access is None else [access])
        self.inflight[side, address] = tx
        self.stats["replay_reads" if replay else "demand_reads"] += 1
        self.by_side[side]["replay_reads" if replay else "demand_reads"] += 1
        if replay:
            self.replay_active += 1
            self.replay_transactions.append(tx)
        if self.timing.first_response:
            self.event(self.now + self.timing.first_response, "response_ready", tx)
        else:
            self.response_ready.append(tx)

    def launch(self):
        self.stats["triggers"] += 1
        for pair in zip_longest(*(self.prefix[s] for s in SIDES)):
            for side, address in zip(SIDES, pair):
                if address is not None:
                    self.replay_queue.append((side, address))

    def pump_replay(self):
        # Round-robin lane order interleaves I/D launch entries; demand issue
        # happens before replay pumping at each timestamp.
        while self.replay_queue and self.replay_active < self.timing.replay_slots:
            side, address = self.replay_queue.popleft()
            if address in self.store.entries[side] or (side, address) in self.inflight:
                self.stats["suppressed_replay_reads"] += 1
                continue
            self.issue(side, address, True)

    def pump_demands(self):
        for side in SIDES:
            while self.waiting[side] and not self.demand_busy[side]:
                a = self.waiting[side].popleft()
                self.stats["demands"] += 1
                self.by_side[side]["demands"] += 1
                if self.store.lookup(side, a.address):
                    origin = self.store.entries[side][a.address]
                    if isinstance(origin, Transaction):
                        origin.consumed = True
                    self.stats["side_hits"] += 1
                    self.by_side[side]["side_hits"] += 1
                    self.complete_demand(a, self.now)
                    continue
                self.demand_busy[side] = True
                tx = self.inflight.get((side, a.address))
                if tx is not None:
                    tx.waiters.append(a)
                    self.stats["joined_replay"] += 1
                else:
                    self.issue(side, a.address, False, a)

    def pump_bus(self):
        if self.bus_busy or not self.response_ready:
            return
        # Oldest ready demanded transaction first; then oldest replay.
        self.response_ready.sort(key=lambda tx: (not bool(tx.waiters), tx.issue))
        tx = self.response_ready.pop(0)
        self.bus_busy = True
        tx.response_end = self.now + self.timing.beats * self.timing.cycles_per_beat
        self.stats["bus_busy_cycles"] += tx.response_end - self.now
        self.event(tx.response_end, "response_done", tx)

    def complete_demand(self, access, end):
        self.last_demand = max(self.last_demand, end)
        self.stats["demand_service_wait_cycles"] += end - access.cycle
        self.by_side[access.side]["demand_service_wait_cycles"] += end - access.cycle

    def run(self, accesses, elapsed, triggers=(0,)):
        # Only replay policies execute the trigger. Its CPU cost shifts all
        # observed arrivals at/after that trigger, including end-of-window.
        starts = tuple(triggers) if self.mode in ("preseed", "continuous") else ()
        if self.mode == "preseed":
            starts = starts[:1]
        for t in starts:
            self.event(t, "trigger")
        def shifted(t):
            return t + sum(t >= start for start in starts) * self.timing.trigger_cost
        for a in accesses:
            if a.side not in SIDES or a.cycle < 0:
                raise ValueError("invalid demand")
            shifted_a = Access(shifted(a.cycle), a.side, a.address)
            self.event(shifted_a.cycle, "demand", shifted_a)
        while self.events:
            self.now = self.events[0][0]
            while self.events and self.events[0][0] == self.now:
                _, _, kind, value = heapq.heappop(self.events)
                if kind == "trigger":
                    self.launch()
                elif kind == "demand":
                    self.waiting[value.side].append(value)
                elif kind == "response_ready":
                    self.response_ready.append(value)
                elif kind == "response_done":
                    self.bus_busy = False
                    begin = max(self.now, self.install_free[value.side])
                    end = begin + self.timing.install
                    self.install_free[value.side] = end
                    self.event(end, "installed", value)
                elif kind == "installed":
                    tx = value
                    self.inflight.pop((tx.side, tx.address))
                    # Current replay hardware admits only replay fills.
                    # Demand-LRU is the distinct equal-capacity counterfactual;
                    # prefix retention likewise pins learned demand contents.
                    if tx.replay or self.mode == "demand-retained":
                        self.store.fill(tx.side, tx.address, tx if tx.replay else None)
                    self.last_completion = max(self.last_completion, self.now)
                    if tx.replay:
                        self.replay_active -= 1
                        self.last_replay = max(self.last_replay, self.now)
                        if not tx.waiters:
                            self.stats["replay_completed_without_waiter"] += 1
                    if tx.waiters:
                        tx.consumed = True
                        for a in tx.waiters:
                            self.complete_demand(a, self.now)
                        self.demand_busy[tx.side] = False
            self.pump_demands()
            self.pump_replay()
            self.pump_bus()
        if any(self.waiting[s] for s in SIDES) or self.inflight or self.replay_queue:
            raise RuntimeError("model failed to drain")
        end = shifted(elapsed)
        self.stats["replay_fills_consumed"] = sum(tx.consumed for tx in self.replay_transactions)
        self.stats["replay_fills_not_consumed"] = sum(not tx.consumed for tx in self.replay_transactions)
        return {"mechanism": self.mode, "timing": asdict(self.timing),
                "capacities_lines": self.store.capacities,
                "fixed_arrival_window_cycles": elapsed,
                "window_plus_trigger_cycles": end,
                "last_demand_completion_cycle": self.last_demand,
                "last_replay_completion_cycle": self.last_replay,
                "drained_service_envelope_cycles": max(end, self.last_completion),
                "stats": dict(self.stats),
                "by_side": {s: dict(self.by_side[s]) for s in SIDES}}


def simulate(accesses, elapsed, training=(), mode="base", i_lines=32, d_lines=32,
             timing=Timing(), triggers=(0,)):
    return Simulation(timing, {"I": i_lines, "D": d_lines}, mode, training).run(
        accesses, elapsed, triggers)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", type=Path, required=True)
    parser.add_argument("--trace", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--latencies", type=int, nargs="+", default=(41, 82, 164, 200))
    parser.add_argument("--capacities", type=int, nargs="+", default=(0, 4, 16, 32, 64, 128))
    parser.add_argument("--cycles-per-beat", type=int, default=1)
    parser.add_argument("--trigger-cost", type=int, default=32)
    parser.add_argument("--oracle", action="store_true",
                        help="explicitly permit training on the evaluated trace")
    args = parser.parse_args(argv)
    training = parse_trace(args.training)
    traces = [parse_trace(p) for p in args.trace]
    if not args.oracle and any(t.sha256 == training.sha256 for t in traces):
        parser.error("training equals evaluated trace; use separate history or explicit --oracle")
    output = {
        "oracle_training": args.oracle,
        "scope": "conditional fixed-arrival miss-stream service projection; not Linux speedup",
        "inputs": [dict(asdict(t), accesses=len(t.accesses)) for t in [training] + traces],
        "assumptions": [
            "Input events are physical L1 miss acceptances; unrecorded L1 hits are unknown.",
            "Base L1 state is not reconstructed; every input remains a base-L1 miss.",
            "Demand-retained side store is demand-populated LRU on the separate prior miss history.",
            "Replay uses the first unique prior miss lines, bounded separately by I/D side capacity.",
            "Retained-prefix uses identical prior-demand prefix tags and capacity, already present at window start without speculative reads.",
            "Demand-retained LRU admits all completed demands; retained-prefix pins the prior first C demand lines; replay modes admit only replay fills, matching the current side buffer contract.",
            "Demand-LRU and pinned-prefix controls have different selection policies; their difference is not pure prefetch effect.",
            "One outstanding ordinary miss per I/D side; matching replay joins that miss.",
            "First-response delay and shared nonpreemptive burst bandwidth vary independently.",
            "Demand responses have priority over ready replay responses; issued bursts cannot be cancelled.",
            "I/D install queues are independent and serial; slots free on full installation.",
            "Arrival timestamps are fixed, so service-envelope changes are not execution savings.",
            "Trigger CPU costs and all replay drain tails are included in service envelope.",
            "Single-window preseed and continuous replay are identical by construction; no recurrent FPGA epochs were captured.",
            "Independent fresh-boot physical windows are never concatenated into one measured execution.",
            "Recorder records after the stated end boundary are counted and excluded.",
            "D-side data are treated read-only; dirty state, stores, translation and coherency are not modeled.",
            "Fully associative side LRU approximates capacity, not banked RTL conflict behavior."],
        "rows": []}
    for trace in traces:
        for capacity in args.capacities:
            for latency in args.latencies:
                timing = Timing(first_response=latency, cycles_per_beat=args.cycles_per_beat,
                                trigger_cost=args.trigger_cost)
                for i_lines, d_lines in ((capacity, 0), (0, capacity), (capacity, capacity)):
                    for mode in MODES:
                        row = simulate(trace.accesses, trace.elapsed, training.accesses,
                                       mode, i_lines, d_lines, timing)
                        row["trace"] = trace.path
                        output["rows"].append(row)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(f"wrote {len(output['rows'])} conditional service rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
