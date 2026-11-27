#!/usr/bin/env python3
"""Summarize replay benchmark runs: per cell cycles, speedup vs cold and the
share of the ideal (warm-switch) gain captured. Usage:
  tools/summarize.py <prefix> [<prefix> ...]
References come from <prefix>-h-ref / <prefix>-pp-ref (MODES=9: off + warm)
when present, else the delay-160 defaults measured on fix13/fix14."""
import glob, os, re, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBG = re.compile(r'(DTRACE|EV |UCEDBG|ICDBG|PFINST|PFREV|REPLAYSTATS|FEDBG|TRAPDBG|L2DIRTY)[^\n]*\n')
DEFAULT_H = {'off': (95.9, 380.1), 'warm': (7.9, None)}
DEFAULT_PP = {'off': (59.9, 59.9, 600.7), 'warm': (6.2, 6.2, None)}

def parse(path):
    try: t = open(path, errors='replace').read()
    except OSError: return None, {}
    t = DBG.sub('', t)
    out = {}
    for m in re.finditer(r'(HYBRID|PINGPONG) mode=(\w+) ([^\n]*)', t):
        if m.group(2) not in ('off', 'wake', 'early', 'warm'): continue
        kv = {k: int(v, 16) for k, v in re.findall(r'(\w+)=0x([0-9a-f]+)', m.group(3))}
        r = kv.get('rounds', 1) or 1
        out[(m.group(1), m.group(2))] = {k: v / r / 1000 for k, v in kv.items() if 'stat' not in k and k != 'rounds'}
    return ('PASS' if '[BSG-PASS]' in t else 'FAIL'), out

def refs(prefix):
    h, pp = dict(DEFAULT_H), dict(DEFAULT_PP)
    _, o = parse(f'{HERE}/{prefix}-h-ref/run.log')
    if ('HYBRID', 'off') in o: h['off'] = (o['HYBRID', 'off']['fg_cycles'], o['HYBRID', 'off']['bg_cycles'])
    if ('HYBRID', 'warm') in o: h['warm'] = (o['HYBRID', 'warm']['fg_cycles'], None)
    _, o = parse(f'{HERE}/{prefix}-pp-ref/run.log')
    if ('PINGPONG', 'off') in o: d = o['PINGPONG', 'off']; pp['off'] = (d['lat_a'], d['lat_b'], d['total'])
    if ('PINGPONG', 'warm') in o: d = o['PINGPONG', 'warm']; pp['warm'] = (d['lat_a'], d['lat_b'], None)
    return h, pp

for prefix in sys.argv[1:]:
    h, pp = refs(prefix)
    hc = sum(h['off']); hi = h['warm'][0] + h['off'][1]
    pc = pp['off'][2]; pi = pc - pp['off'][0] - pp['off'][1] + pp['warm'][0] + pp['warm'][1]
    print(f'## {prefix}  (hybrid cold {hc:.1f}k ideal {hi:.1f}k; pingpong cold {pc:.1f}k ideal {pi:.1f}k)')
    for d in sorted(glob.glob(f'{HERE}/{prefix}-*/')):
        cell = os.path.basename(d.rstrip('/'))[len(prefix) + 1:]
        st, o = parse(d + 'run.log')
        if st is None: continue
        if not o: print(f'  {cell:10s} {st}'); continue
        for (b, mode), v in sorted(o.items()):
            if b == 'HYBRID':
                w = v['fg_cycles'] + v['bg_cycles']
                extra = '' if mode in ('off', 'warm') else f' speedup {hc / w:.3f}x  {100 * (hc - w) / (hc - hi):5.1f}% of ideal'
                print(f'  {cell:10s} {st} {mode:5s} fg {v["fg_cycles"]:6.1f}k bg {v["bg_cycles"]:6.1f}k whole {w:6.1f}k{extra}')
            else:
                w = v['total']
                extra = '' if mode in ('off', 'warm') else f' speedup {pc / w:.3f}x  {100 * (pc - w) / (pc - pi):5.1f}% of ideal'
                print(f'  {cell:10s} {st} {mode:5s} sw-in {v["lat_a"]:5.1f}k/{v["lat_b"]:5.1f}k total {w:6.1f}k{extra}')
