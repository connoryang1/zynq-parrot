#!/usr/bin/env python3
"""Summarize FGBG_CONFIG/FGBG_RESULT lines from one or more console logs.

For every case (config line) report medians of off and on cells and the
median of per-repeat paired speedups (off/on) for whole, fg_work and
fg_latency, plus min/max of the paired speedups. Only cases that print
FGBG_PASS are accepted; incomplete cases are listed separately.
"""
import re, statistics as st, sys, json

def parse(paths):
    cases = []
    for p in paths:
        cur = None
        for raw in open(p, errors='replace'):
            l = raw.replace('\r', '').strip()
            if l.startswith('FGBG_CONFIG'):
                cur = dict(config=dict(re.findall(r'(\w+)=(\S+)', l)), rows=[], passed=False, log=p)
                cases.append(cur)
            elif l.startswith('FGBG_RESULT') and cur:
                cur['rows'].append({k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', l)})
            elif l == 'FGBG_PASS' and cur:
                cur['passed'] = True
    return cases

def summarize(c):
    out = {}
    reps = {}
    for r in c['rows']:
        reps.setdefault(r['repeat'], {})[r['enabled']] = r
    for m in ('whole', 'fg_work', 'fg_latency', 'bg_work'):
        off = [r[m] for r in c['rows'] if r['enabled'] == 0]
        on = [r[m] for r in c['rows'] if r['enabled'] == 1]
        paired = [v[0][m] / v[1][m] for v in reps.values() if 0 in v and 1 in v and v[1][m]]
        out[m] = dict(off=st.median(off), on=st.median(on), speedup=st.median(paired),
                      lo=min(paired), hi=max(paired), n=len(paired))
    return out

if __name__ == '__main__':
    cases = parse(sys.argv[1:])
    rows = []
    for c in cases:
        k = c['config']
        name = f"{k['fg']}{k['fg_kib']}K/{k['bg']}{k['bg_kib']}K {k['policy']}"
        if not c['passed']:
            print(f'INCOMPLETE {name} ({len(c["rows"])} rows) {c["log"]}'); continue
        s = summarize(c)
        loops = int(k['loops'])
        print(f"{name:28s} whole {s['whole']['speedup']:.3f}x [{s['whole']['lo']:.3f},{s['whole']['hi']:.3f}]"
              f"  fg_latency {s['fg_latency']['speedup']:.3f}x  fg_work {s['fg_work']['speedup']:.3f}x"
              f"  (per-loop off/on whole {s['whole']['off']/loops:.0f}/{s['whole']['on']/loops:.0f},"
              f" fg_lat {s['fg_latency']['off']/loops:.0f}/{s['fg_latency']['on']/loops:.0f}) n={s['whole']['n']}")
        rows.append(dict(case=name, config=k, summary=s))
    json.dump(rows, open('fgbg-summary.json', 'w'), indent=1)
