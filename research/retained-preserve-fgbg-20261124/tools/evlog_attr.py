#!/usr/bin/env python3
"""Attribute foreground switch-window misses from a BP_REPLAY_EVLOG run built
with -DEVMARK. Usage: tools/evlog_attr.py <run.log> [--lines]
Per measured round (fg window = marker edge 1 -> 2, trigger = edge 3):
  replay R: installs before fg start / during fg window / after it
  fg demand fills (I/D), each classified:
    lost    : replay-installed this round, then overwritten unused before use
    late    : footprint line whose replay install had not happened yet
    outside : never replay-installed (not in the recorded footprint)
  X writers: who overwrote unused replayed lines this round (replay installer
    vs demand fill), and when (before trigger, before fg, inside fg)."""
import re, sys
from collections import defaultdict, Counter
path = sys.argv[1]; show = '--lines' in sys.argv
ev = []
for line in open(path, errors='replace'):
    i = line.find('EV ')
    if i < 0: continue
    p = line[i:].split()
    if len(p) >= 3 and p[1] == 'C': ev.append((int(p[2]), 'C', None)); continue
    if len(p) < 4: continue
    if p[1] == 'M': ev.append((int(p[2]), 'M', int(p[3], 16))); continue
    if p[1] not in 'ID' or len(p) < 7: continue
    c, cyc, k, idx, way, tag = p[1], int(p[2]), p[3], int(p[4]), int(p[5]), p[6]
    ready = int(p[8].split('=')[1]) if k == 'X' and len(p) > 8 else None
    ev.append((cyc, k, (c, idx, tag, way, ready)))
ev.sort(key=lambda e: e[0])
marks = {}
for cyc, k, v in ev:
    if k == 'M' and 1 <= (v & 0xff) <= 4 and (v >> 16) <= 3: marks[(v >> 16, (v >> 8) & 0xff, v & 0xff)] = cyc
if len(marks) < 4:  # stray mscratch writes (startup code) are not window markers
    marks = {}
    # No -DEVMARK: the hybrid benchmark's own cycle-CSR reads give t0, t1, t2
    # per round, modes in the order of the HYBRID result lines. Edge 3 (wake
    # trigger) is taken as t2; early-trigger time is unknown in this mode.
    modes = [{'off': 0, 'wake': 1, 'early': 2, 'warm': 3}[m] for m in
             re.findall(r'HYBRID mode=(off|wake|early|warm)',
                        re.sub(r'(EV |REPLAYSTATS|DTRACE)[^\n]*\n', '', open(path, errors='replace').read()))]
    cs = [cyc for cyc, k, v in ev if k == 'C']
    nr = len(cs) // 3 // max(1, len(modes))
    for mi, m in enumerate(modes):
        for r in range(nr):
            b = (mi * nr + r) * 3
            marks[(m, r, 1)], marks[(m, r, 2)] = cs[b], cs[b + 1]
            if m == 1: marks[(m, r, 3)] = cs[b + 2]
footprint = {(v[0], v[1], v[2]) for cyc, k, v in ev if k == 'R'}
rounds = sorted({(m, r) for (m, r, e) in marks})
names = {0: 'off', 1: 'wake', 2: 'early', 3: 'warm'}
for m, r in rounds:
    t1, t2 = marks.get((m, r, 1)), marks.get((m, r, 2))
    if t1 is None or t2 is None: continue
    prev_end = marks.get((m, r - 1, 2), 0)          # end of previous fg window
    trig = marks.get((m, r - 1, 3)) if m in (1, 2) else None  # trigger for THIS window is in prev round
    installed, lost, evicted_by = {}, set(), Counter()
    rc = Counter(); fills = Counter(); cls = defaultdict(Counter); lines = []
    for cyc, k, v in ev:
        if cyc < prev_end or cyc > t2: continue
        if k in ('M', 'C'): continue
        key = (v[0], v[1], v[2])
        if k == 'R':
            installed[key] = cyc
            rc['before_fg' if cyc < t1 else 'in_fg'] += 1
        elif k == 'X':
            if key in installed: lost.add(key)
            when = 'before_trig' if trig is not None and cyc < trig else ('before_fg' if cyc < t1 else 'in_fg')
            evicted_by[('replay' if v[4] else 'demand', when)] += 1
        elif k == 'F' and t1 <= cyc <= t2:
            fills[v[0]] += 1
            c = 'lost' if key in lost else ('late' if key in footprint else 'outside')
            cls[v[0]][c] += 1
            if show: lines.append(f'    {cyc - t1:7d} {v[0]} {c:7s} idx={v[1]} tag={v[2]}')
    last_r = max([c for c in installed.values()], default=None)
    print(f'{names.get(m, m)} round {r}: fg window {t2 - t1} cyc;'
          f' trigger {"-" if trig is None else t1 - trig} cyc before fg;'
          f' replay R before fg {rc["before_fg"]}, during fg {rc["in_fg"]}'
          f'{"" if last_r is None else f", last at fg{last_r - t1:+d}"}')
    for c in 'ID':
        if fills[c]: print(f'  {c} fg demand fills {fills[c]}: ' + ', '.join(f'{k} {n}' for k, n in sorted(cls[c].items())))
    if evicted_by: print('  replayed lines overwritten unused: ' + ', '.join(f'{w} by {who} {n}' for (who, w), n in sorted(evicted_by.items())))
    for l in lines: print(l)
