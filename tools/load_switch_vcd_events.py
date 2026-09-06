#!/usr/bin/env python3
"""Extract clocked load, refill, switch and target events from an FST's VCD stream.

This diagnostic samples pre-rising-edge inputs and emits raw evidence, not a
speedup verdict. PC arguments select the program's load/switch/target boundaries.
Usage: fst2vcd dump.fst | python3 tools/load_switch_vcd_events.py --pc 0x80000400
The default period is 50,000 trace ticks (20 MHz with the normal 1 ps timescale).
"""
import argparse
import json
import sys

p = argparse.ArgumentParser()
p.add_argument('--pc', action='append', type=lambda s: int(s, 0), default=[])
p.add_argument('--min-cycle', type=int, default=0)
p.add_argument('--period', type=int, default=50000)
a = p.parse_args()
if a.period <= 0:
    p.error('--period must be positive')
watch = {
    'clk': 'be.clk_i',
    'dv': 'be.scheduler.dispatch_pkt_cast_o.v',
    'dq': 'be.scheduler.dispatch_pkt_cast_o.queue_v',
    'pc': 'be.scheduler.dispatch_pkt_cast_o.pc',
    'tid': 'be.scheduler.dispatch_pkt_cast_o.thread_id',
    'ctxtsw': 'be.scheduler.dispatch_pkt_cast_o.ctxtsw_v',
    'cv': 'be.calculator.commit_pkt_cast_o.instret',
    'cp': 'be.calculator.commit_pkt_cast_o.pc',
    'cs': 'be.calculator.commit_pkt_cast_o.ctxtsw',
    'critical': 'be.calculator.pipe_mem.dcache.critical_recv',
    'complete': 'be.calculator.pipe_mem.dcache.complete_recv',
    'miss': 'be.calculator.pipe_mem.dcache.blocking_sent',
    'fill_addr': 'be.calculator.pipe_mem.dcache.fill_paddr_r',
    'addr': 'be.calculator.pipe_mem.dcache.paddr_tv_r',
    'fill_tid': 'be.calculator.pipe_mem.dcache.fill_thread_id_r',
    'late': 'be.calculator.pipe_mem.late_wb_v_o',
    'late_tid': 'be.calculator.pipe_mem.late_wb_pkt_cast_o.thread_id',
    'late_rd': 'be.calculator.pipe_mem.late_wb_pkt_cast_o.rd_addr',
    'late_data': 'be.calculator.pipe_mem.late_wb_pkt_cast_o.rd_data',
    'busy': 'be.calculator.mem_busy_o',
    'ordered': 'be.calculator.mem_ordered_o',
}
scope, codes, found = [], {}, {}
for line in sys.stdin:
    t = line.split()
    if not t:
        continue
    if t[0] == '$scope':
        scope.append(t[2])
    elif t[0] == '$upscope':
        scope.pop()
    elif t[0] == '$var':
        name = '.'.join(scope + [t[4]])
        for label, suffix in watch.items():
            if name.endswith('.' + suffix):
                found[label] = name
                codes.setdefault(t[3], []).append(label)
    elif t[0] == '$enddefinitions':
        break
missing = watch.keys() - found.keys()
if missing:
    sys.exit('Missing required signals: ' + ', '.join(sorted(missing)))
print(json.dumps(found), file=sys.stderr)
vals, before, time = {}, {}, 0

def sample():
    if vals.get('clk') != 1 or before.get('clk') != 0:
        return
    if time // a.period < a.min_cycle:
        return
    v = before
    selected = ((v.get('dv') and v.get('pc') in a.pc)
                or (v.get('cv') and v.get('cp') in a.pc)
                or any(v.get(k) for k in ('cs', 'critical', 'complete', 'miss', 'late')))
    if selected:
        print(json.dumps(dict(time_ticks=time, cycle=time // a.period, **v)), flush=True)

for line in sys.stdin:
    if line.startswith('#'):
        sample()
        before = vals.copy()
        time = int(line[1:])
    elif line[:1] in ('b', 'B'):
        bits, code = line[1:].split()
        if code in codes:
            for label in codes[code]:
                vals[label] = int(bits, 2) if set(bits) <= {'0', '1'} else None
    elif line[:1] in ('0', '1', 'x', 'z'):
        code = line[1:].strip()
        if code in codes:
            for label in codes[code]:
                vals[label] = int(line[0]) if line[0] in '01' else None
sample()
