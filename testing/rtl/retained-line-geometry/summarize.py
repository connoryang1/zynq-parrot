#!/usr/bin/env python3
"""Review CLOSED source-bound boundary gates without running any model."""
import json
from pathlib import Path
from service import PIN,artifact

HERE=Path(__file__).resolve().parent


def verify(binding):
    if artifact(binding['path'])!=binding:raise ValueError('artifact binding mismatch: '+binding['path'])


def main():
    boundary=HERE/'evidence/boundary-01/summary.json'
    b=json.loads(boundary.read_text())
    if b['state']!='PASS-functional-boundary-cases' or len(b['results'])!=9:raise ValueError('incomplete boundary sequence')
    cases={};bindings=[]
    for entry in b['results']:
        verify(entry['manifest']);verify(entry['service'])
        manifest=Path(entry['manifest']['path']);m=json.loads(manifest.read_text())
        if m['state']!='PASS-retained-geometry':raise ValueError('unclosed model')
        if m['sources']['bp_retained_line_store.sv']['sha256']!=PIN:raise ValueError('backend changed')
        for name,s in m['sources'].items():
            if artifact(manifest.parent/'source'/name)['sha256']!=s['sha256']:raise ValueError('source snapshot mismatch')
        for c in m['commands']:
            if c['returncode']!=0:raise ValueError('command failure')
            verify(c['log'])
        for row in m['clock_results']:verify(row['fst'])
        a=json.loads(Path(entry['service']['path']).read_text())
        if a['input_manifest']!=entry['manifest']:raise ValueError('audit source binding')
        verify(a['analyzer']);verify(a['converter'])
        if a['state']!='PASS-closed-trace-service-audit':raise ValueError('audit failed')
        if len(a['runs'])!=2:raise ValueError('missing clock mode')
        for row in a['runs']:
            if not row['converter_clean_eof']:raise ValueError('incomplete trace')
            verify(row['fst']);verify(row['log'])
        post=manifest.parent/'post-audit.json';p=json.loads(post.read_text())
        if p['state']!='PASS' or p['analysis']!=entry['service'] or p['command']['returncode']!=0:raise ValueError('postaudit mismatch')
        verify(p['command']['log'])
        cases[(entry['sets'],entry['i_lines'],entry['d_lines'])]=a
        bindings.append(dict(manifest=entry['manifest'],service=entry['service'],post_audit=artifact(post)))
    for n,name in [(1280,'reuse64-1280-v2'),(1320,'reuse64-1320'),(1536,'reuse64-1536')]:
        p=HERE/'evidence'/name/'analysis.json';a=json.loads(p.read_text())
        if a['state']!='PASS-closed-trace-service-audit':raise ValueError('reuse audit failed')
        verify(a['input_manifest']);verify(a['analyzer']);verify(a['converter'])
        for row in a['runs']:
            if not row['converter_clean_eof']:raise ValueError('incomplete reuse trace')
            verify(row['fst']);verify(row['log'])
        cases[(64,n,n)]=a;bindings.append(dict(reused_service=artifact(p),original_manifest=a['input_manifest']))
    rows=[]
    for n in (1280,1320,1344,1408,1536):
        row=dict(lines_per_side=n,payload_bytes_per_side=n*64,geometries={})
        for sets in (64,256):
            a=cases[(sets,n,n)];s=a['runs'][0]['service_cycles']
            first={k.split('/')[1]:v for k,v in s.items() if k.startswith('lane0/')}
            for r in a['runs']:
                for lane in (0,1):
                    for k,v in first.items():
                        if r['service_cycles'][f'lane{lane}/{k}']!=v:raise ValueError('lane/clock service differs')
            row['geometries'][str(sets)]=dict(same_both_lanes_and_clocks=True,full_histograms=first)
        rows.append(row)
    checks=[]
    for sets,i,d in [(256,0,0),(256,259,517)]:
        a=cases[(sets,i,d)]
        checks.append(dict(sets=sets,i_lines=i,d_lines=d,runs=[dict(clock_mode=r['clock_mode'],counts=r['counts'],full_histograms=r['service_cycles']) for r in a['runs']]))
    report=dict(state='PASS-reviewed-closed-boundary-evidence',backend_sha256=PIN,geometry_cases=12,closed_clock_runs=24,
                new_clean_models=9,reused_closed_models=3,full_slot_payload_read_checks=56656,
                scope='Functional full64B slot correctness and accepted own-lane interface edge cost only. No application benefit, unique retained-capacity, physical fit, frequency, FPGA performance, or memory-service claim.',
                source=artifact(__file__),boundary_summary=artifact(boundary),input_bindings=bindings,balanced_comparison=rows,zero_and_partial=checks)
    (HERE/'evidence/closed-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    print('lines | sets64 hit min/median/max; miss; insert min/median/max | sets256 same')
    for row in rows:
        fields=[]
        for s in ('64','256'):
            h=row['geometries'][s]['full_histograms'];hit=h['all_slot_hit'];ins=h['fill_insert']
            fields.append(f"{hit['min']}/{hit['median']}/{hit['max']}; {h['full_set_miss']['median']}; {ins['min']}/{ins['median']}/{ins['max']}")
        print(row['lines_per_side'],' | '.join(fields))
    print('PASS12 geometries/24 clock runs; all hashes verified; no model execution')

if __name__=='__main__':main()
