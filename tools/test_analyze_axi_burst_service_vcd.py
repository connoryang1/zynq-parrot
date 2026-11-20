#!/usr/bin/env python3
"""Check FIFO burst association, backpressure, clock identity and timing bounds."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('analyze_axi_burst_service_vcd.py')
spec = importlib.util.spec_from_file_location('burst_audit', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(clock_alias=True, wrong_id=False):
    header=['$timescale 1ps $end']
    codes={k:'v'+str(i) for i,k in enumerate(module.WATCH)}
    if clock_alias:codes['axi_clock']=codes['clock']
    for key,suffix in module.WATCH.items():
        parts=('top'+suffix).split('.')
        header.extend('$scope module '+p+' $end' for p in parts[:-1])
        header.append('$var wire 64 '+codes[key]+' '+parts[-1]+' $end')
        header.extend('$upscope $end' for _ in parts[:-1])
    header.append('$enddefinitions $end')
    for cycle in range(14):
        v={k:0 for k in module.WATCH}
        v.update(latency=4,queue_depth=4,arready=1,rready=1,arsize=3,arburst=1)
        if cycle in (0,12):v.update(commit_v=1,commit_pc=0x8000040c if cycle==0 else 0x80000414)
        if cycle in (1,2):v.update(arvalid=1,araddr=0x1000 if cycle==1 else 0x2000,arlen=3 if cycle==1 else 1,arid=cycle)
        if 5<=cycle<=11:
            v.update(rvalid=1,rready=int(cycle!=5),rid=(1 if cycle<=9 else 2),rlast=int(cycle in (9,11)))
        if wrong_id and cycle==10:v['rid']=3
        header.append('#'+str(cycle*10))
        for key,value in v.items():
            if key not in ('clock','axi_clock'):header.append('b'+format(value,'b')+' '+codes[key])
        header.append('0'+codes['clock'])
        if not clock_alias:header.append('0'+codes['axi_clock'])
        header.extend(['#'+str(cycle*10+5),'1'+codes['clock']])
        if not clock_alias:header.append('1'+codes['axi_clock'])
    header.append('#140')
    return '\n'.join(header)+'\n'


class BurstAuditTests(unittest.TestCase):
    def run_audit(self,**kwargs):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'result.json'
            p=subprocess.run([sys.executable,str(SCRIPT),'--output',str(out)],input=fixture(**kwargs),text=True,capture_output=True)
            return p,json.loads(out.read_text()) if out.exists() else None

    def test_complete_transactions_include_stall_and_queue_delay(self):
        p,r=self.run_audit();self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(r['timed_commit_window_cycles'],12)
        self.assertEqual(r['timed_accepted_ar'],2)
        self.assertEqual(r['max_outstanding_ar_entire_run'],2)
        self.assertEqual(r['timed_ar_to_first_r_offer_ticks'],{'4':1,'8':1})
        self.assertEqual(r['timed_ar_to_last_r_accept_ticks'],{'8':1,'9':1})
        self.assertEqual(r['timed_r_backpressure_cycles'],1)
        self.assertEqual(r['timed_accepted_beat_gap_ticks'],{'1':4})
        self.assertEqual([x['accepted_beats'] for x in r['timed_transactions']],[4,2])
        self.assertEqual(r['pending_at_trace_end'],0)
        self.assertEqual(r['issues'],[])

    def test_id_mismatch_is_visible(self):
        p,r=self.run_audit(wrong_id=True);self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('response id mismatch',[x['reason'] for x in r['issues']])

    def test_different_clock_alias_rejected(self):
        p,r=self.run_audit(clock_alias=False)
        self.assertNotEqual(p.returncode,0);self.assertIsNone(r)
        self.assertIn('identical BE and AXI clocks',p.stderr)


if __name__=='__main__':unittest.main()
