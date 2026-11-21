#!/usr/bin/env python3
"""Inspect only existing closed08/10 lower-path gates; no target execution."""
import gzip, hashlib, json, lzma
from pathlib import Path
import subprocess, sys, tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'testing/rtl/hp0-closed-trace'))
import run as hp


def main():
    base='top_fpga_inst.blackparrot.'
    controller=base+'processor.u.unicore.slices[0].l2s.cache_controller.'
    bridge=base+'cache2axi.'
    fields={
        'clk':'top_fpga_inst.aclk','reset':'top_fpga_inst.aresetn',
        'num_cache':bridge+'num_cache_p','tag_slots':bridge+'tag_fifo_els_p',
        'rr_v':bridge+'read_rr_v_lo','rr_yumi':bridge+'read_rr_yumi_li',
        'rr_addr':bridge+'read_rr_dma_pkt.addr','rr_bank':bridge+'read_rr_tag_lo',
        'r_fence':bridge+'r_fence_lo','tag_ready':bridge+'axi_rx.tag_fifo_ready_lo',
        'ctrl_reset':controller+'reset_i','ctrl_state':controller+'state_r',
        'fwd_v':controller+'fsm_fwd_v_li','fwd_yumi':controller+'fsm_fwd_yumi_lo',
        'fwd_addr':controller+'fsm_fwd_addr_li','fwd_last':controller+'fsm_fwd_last_li',
        'bank':controller+'fwd_pkt_bank_lo','pkt_v':controller+'cache_pkt_v_o',
        'pkt_yumi':controller+'cache_pkt_yumi_i'}
    results={}
    for case,parent in [('native08-audit02',ROOT/'research/large-retained-capacity-20261121/advisory-full-system08'),
                        ('delay200-10-audit01',ROOT/'research/hp0-response-path-20261121/full-system-delay200-10')]:
        out=HERE/case;out.mkdir(exist_ok=False)
        proof=json.loads((HERE.parent/case/'verification.json').read_text())
        start=min(r['advisory_publications'][0]['advisory']['time'] for r in proof['UCE_endpoints'].values())-2000000
        end=max(r['advisory_publications'][0]['time'] for r in proof['UCE_endpoints'].values())+1000000
        selection=out/'selection.tsv';selection.write_text(''.join(k+'\t'+v+'\n' for k,v in fields.items()))
        with tempfile.TemporaryDirectory(prefix='lower-closed-gate-',dir='/dev/shm') as temp:
            temp=Path(temp);raw=temp/'closed.fst'
            with lzma.open(parent/'trace.fst.xz','rb') as src,raw.open('wb') as dst:
                for block in iter(lambda:src.read(1024*1024),b''):dst.write(block)
            assert hp.binding(raw)['sha256']==proof['bindings']['raw_FST']['sha256']
            reader=temp/'fst_events'
            subprocess.run(['python3',str(hp.READER_DIR/'build_reader.py'),'--output',str(reader)],check=True,timeout=150)
            command=[str(reader),str(raw),str(selection.resolve())]
            r=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=120)
            (out/'reader.stderr').write_text(r.stderr);assert r.returncode==0,r.stderr
            with gzip.open(out/'selected-events.tsv.gz','wt') as f:f.write(r.stdout)
            (out/'reader.build.json').write_bytes(reader.with_suffix('.build.json').read_bytes())
        expected={}
        for line in r.stdout.splitlines():
            if line.startswith('#SIGNAL'):
                p=line.split('\t');expected[p[1]]=(fields[p[1]],int(p[2]))
        assert set(expected)==set(fields)
        intervals=[];last=None;current=None;params={}
        for time,clocks,s in hp.edge_samples(iter(r.stdout.splitlines(keepends=True)),expected):
            if not start<=time<=end:continue
            assert not s['ctrl_reset'] and s['reset']
            params={k:s[k] for k in ['num_cache','tag_slots']}
            # All selected samples are on the actual AXI/controller positive clock.
            state={k:s[k] for k in fields if k not in ['clk','reset','ctrl_reset','num_cache','tag_slots']}
            if state!=last:
                current=dict(start=time,end_exclusive=time+50000,cycles=1,**state)
                intervals.append(current);last=state
            else:current['end_exclusive']=time+50000;current['cycles']+=1
        results[case]=dict(parameters=params,intervals=intervals,base_proof=hp.binding(HERE.parent/case/'verification.json'),
            input_archive=hp.binding(parent/'trace.fst.xz'),events=hp.binding(out/'selected-events.tsv.gz'),
            selection=hp.binding(selection),command=command)
    report=dict(scope='same closed traces; no target run',script=hp.binding(__file__),cases=results)
    (HERE/'gate.json').write_text(json.dumps(report,indent=2)+'\n')
    for case,d in results.items():
        print(case,d['parameters'])
        for r in d['intervals']:
            if r['cycles']>5 or r['rr_yumi']:print(r)


if __name__=='__main__':main()
