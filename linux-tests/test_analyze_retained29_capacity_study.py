"""Entirely synthetic two-image math/order fixtures; no physical admission."""
import copy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid
import analyze_retained29_capacity_study as a


def boots(image,ratio=None):
    hardware=dict(cfg='TEST_ONLY-SAME',l1i_bytes=32768,l1d_bytes=32768,l2_bytes=16384,
        retained=dict(i_lines=256 if image=='small' else 1792,d_lines=256 if image=='small' else 1792,set_log2=8))
    result=[]
    for visit in a.p.canonical_visits():
        plan=visit['plan'];commands=[]
        for case in plan['cases']:
            cells=[]
            for repeat in range(plan['repeats']):
                off=100*10**repeat;on=off*(1 if ratio is None else ratio(visit,case,repeat))
                for order in range(2):
                    enabled=(repeat&1)^order;cost=int(on if enabled else off)
                    cells.append(dict(repeat=repeat,order=order,enabled=enabled,whole=cost,steady=cost//2,
                        resource={k:repeat+enabled for k in a.within.RESOURCE},control=dict(TEST_ONLY=True),prefix=dict(TEST_ONLY=True),replay=dict(TEST_ONLY=True)))
            commands.append(dict(case=case,complete_cells=2*plan['repeats'],cells=cells))
        result.append(dict(visit_id=visit['id'],boot_order=visit['order'],round=visit['round'],rotation=plan['rotation'],
            acquisition_boot_id=str(uuid.UUID(int=visit['order']+1+(100 if image=='large' else 0),version=4)),
            role=plan['role'],workload=plan['workload'],started_utc='TEST_ONLY',released_utc='TEST_ONLY',
            session=dict(TEST_ONLY=True,path=image+'-'+visit['id'],bytes=0,sha256='0'*64),hardware=copy.deepcopy(hardware),
            artifacts=dict(TEST_ONLY=image),programs=dict(TEST_ONLY='SAME_UNEXECUTED_PROGRAMS'),commands=commands))
    return result


class Mathematics(unittest.TestCase):
    def test_complete_neutral_study_and_pilot_exclusion(self):
        small,large=boots('small'),boots('large')
        for command in large[0]['commands']:
            for cell in command['cells']:cell['whole']*=10000
        result=a.estimate(small,large,1792)
        self.assertAlmostEqual(result['primary']['ratios']['enabled_large_over_small'],1)
        self.assertEqual(result['counts'],dict(performance_boots=30,pilot_boots=2,performance_primary_paired_repeats=120,equal_configurations=10))
        self.assertEqual(len(result['paired_repeats']),372)
        self.assertIn('no CI/P/bootstrap',result['uncertainty'])

    def test_exact_repeat_boot_equal10_hierarchy(self):
        def effect(v,c,r):return (1,4,1,4)[r]*(1 if v['round'] is None else (1,2,4)[v['round']])*(1 if c['kib']==32 else 4)
        result=a.estimate(boots('small'),boots('large',effect),1792)
        self.assertAlmostEqual(result['primary']['ratios']['enabled_large_over_small'],8,places=10)
        row=next(c for c in result['configurations'] if c['workload']=='scan' and c['kib']==32 and c['mask']==15)
        points=[b['ratios']['enabled_large_over_small'] for b in row['endpoints']['whole']['boots']]
        for got,want in zip(points,(2,4,8)):self.assertAlmostEqual(got,want)
        self.assertAlmostEqual(row['endpoints']['whole']['ratios']['enabled_large_over_small'],4)
        self.assertNotAlmostEqual(8,sum(c['whole'] for cmd in boots('large',effect)[1]['commands'] for c in cmd['cells'])/sum(c['whole'] for cmd in boots('small')[1]['commands'] for c in cmd['cells']))

    def test_one_configuration_cannot_gain_cycle_weight(self):
        def effect(v,c,r):return 1024 if c['workload']=='scan' and c['kib']==32 and c['mask']==15 else 1
        result=a.estimate(boots('small'),boots('large',effect),1792)
        self.assertAlmostEqual(result['primary']['ratios']['enabled_large_over_small'],2)

    def test_absolute_enabled_regression_cannot_be_replaced_by_favorable_onoff(self):
        small,large=boots('small'),boots('large')
        for boot in large:
            for command in boot['commands']:
                for cell in command['cells']:
                    multiplier=1.5 if cell['enabled'] else 2
                    cell['whole']=int(cell['whole']*multiplier);cell['steady']=int(cell['steady']*multiplier)
        metrics=a.estimate(small,large,1792)['primary']['ratios']
        self.assertAlmostEqual(metrics['enabled_large_over_small'],1.5)
        self.assertAlmostEqual(metrics['off_large_over_small'],2)
        self.assertAlmostEqual(metrics['within_large_on_over_off'],.75)
        self.assertAlmostEqual(metrics['ratio_of_ratios'],.75)

    def test_three_boot_points_and_cross_size_cluster_retained(self):
        def effect(v,c,r):return 1 if v['round'] is None else ((1,4,1) if c['kib']==32 else (4,1,1))[v['round']]
        result=a.estimate(boots('small'),boots('large',effect),1792)
        for row in result['configurations']:
            if row['workload']=='scan' and row['mask']==15:
                values=row['endpoints']['whole'];expected=(1,4,1) if row['kib']==32 else (4,1,1)
                self.assertEqual([round(b['ratios']['enabled_large_over_small'],6) for b in values['boots']],list(expected))
                self.assertEqual([round(x,6) for x in values['boot_ranges']['enabled_large_over_small']],[1,4])

    def test_missing_reused_wrong_geometry_policy_or_program_rejected(self):
        changes=[lambda s,l:l.pop(),lambda s,l:l[1]['commands'].pop(),lambda s,l:l[1]['commands'][0]['cells'].pop(),
            lambda s,l:l[1].update(acquisition_boot_id=s[1]['acquisition_boot_id']),
            lambda s,l:[b['hardware'].update(l2_bytes=4096) for b in l],
            lambda s,l:l[0]['hardware']['retained'].update(set_log2=6),
            lambda s,l:l[0]['programs'].update(TEST_ONLY='DIFFERENT_ELF'),lambda s,l:l.reverse()]
        for change in changes:
            s,l=boots('small'),boots('large');change(s,l)
            with self.subTest(change=change),self.assertRaises(ValueError):a.estimate(s,l,1792)

    def test_test_only_exports_preserve_all_raw_cells_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'TEST_ONLY'
            a.write_outputs(dict(scope=a.within.TEST_SCOPE,inputs=dict(TEST_ONLY=True),estimates=a.estimate(boots('small'),boots('large'),1792)),out)
            self.assertIn('TEST ONLY',(out/'RESULTS.md').read_text())
            self.assertEqual(len((out/'raw-cells.csv').read_text().splitlines()),1489)
            self.assertEqual(len((out/'configurations.csv').read_text().splitlines()),301)


class Admission(unittest.TestCase):
    def test_draft_exact_schedule_and_no_hardware_promotion(self):
        d=json.loads(a.DECLARATION.read_text());a.validate_declaration(d)
        self.assertEqual(a.APPROVED_CAPACITY_BRIDGES,{})
        with self.assertRaisesRegex(ValueError,'DRAFT UNLAUNCHABLE'):a.validate_declaration(d,approved=True)
        order=a.schedule();self.assertEqual(len(order),32)
        self.assertEqual([r['image'] for r in order[:6]],['small','large','small','large','large','small'])
        for image in a.IMAGES:self.assertEqual([r['cohort_index'] for r in order if r['image']==image],list(range(16)))
        for mutation in ('schedule','epoch','program','baseline'):
            bad=copy.deepcopy(d)
            if mutation=='schedule':bad['schedule'][2],bad['schedule'][3]=bad['schedule'][3],bad['schedule'][2]
            if mutation=='epoch':bad['fixed']['epoch_bits']=16
            if mutation=='program':bad['program_sha256']['plain']='0'*64
            if mutation=='baseline':bad['small_lines_per_side']=128
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):a.validate_declaration(bad)

    def test_external_study_sha_checked_before_other_inputs(self):
        with self.assertRaisesRegex(ValueError,'external study'):a.analyze(a.DECLARATION,'0'*64,None,None,None,None,None,None)

    def test_both_complete_gates_recomputed_before_mathematics(self):
        d=json.loads(a.DECLARATION.read_text());d['selected_large_lines_per_side']=1792
        sha=a.p.binding(a.DECLARATION)['sha256']
        with patch.object(a,'validate_declaration'),patch.object(a.within,'load_complete',side_effect=[({},{}),ValueError('large incomplete')]) as complete,patch.object(a,'estimate',side_effect=AssertionError('must not analyze subset')):
            with self.assertRaisesRegex(ValueError,'large incomplete'):a.analyze(a.DECLARATION,sha,'small','s','large','l',None,None)
            self.assertEqual(complete.call_args_list,[(('small','s'),),(('large','l'),)])

    def fixture(self,root):
        def write(name,value):
            path=root/name;path.write_text(json.dumps(value));return a.p.binding(path)
        gates={};cohorts={};clock=write('clock.json',dict(core_hz=20000000,axi_hz=20000000))
        for image in a.IMAGES:
            cohort=dict(hardware=boots(image)[0]['hardware'],program_sha256=a.p.cost.ELF_SHAS,
                artifacts=dict(bit=dict(sha256=image)),physical_qualification=dict(TEST_ONLY=True))
            cohorts[image]=write(image+'-cohort.json',cohort);gates[image]=dict(cohort=cohorts[image],sessions=[None]*16,acquisition_boot_ids=[None]*16)
        entries=[];start=datetime(2026,11,21,tzinfo=timezone.utc)
        for item in a.schedule():
            n=item['order'];image,index=item['image'],item['cohort_index'];record=write('result%d.json'%n,dict(started_utc=(start+timedelta(seconds=2*n)).isoformat(),release_after_recovery_utc=(start+timedelta(seconds=2*n+1)).isoformat()))
            identity=str(uuid.UUID(int=n+1,version=4));gates[image]['sessions'][index]=record;gates[image]['acquisition_boot_ids'][index]=identity
            entries.append(dict(item,state='PASS',result=record,boot_id=identity))
        d=dict(cohorts=cohorts,selected_large_lines_per_side=1792,declared_utc=(start-timedelta(seconds=1)).isoformat(),attempt_ledger_path=str(root/'matched-capacity-attempts.json'))
        study=write('study.json',d);ledger=dict(schema='bp-retained29-matched-capacity-attempt-ledger-v1',study=study,entries=entries)
        return d,study,gates,ledger,clock,write

    def test_global_order_failures_subsets_reused_uuid_and_recovery_gap_rejected(self):
        for mode in ('good','missing','failure','earlier-failure','wrong-order','reused-id','overlap'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
                d,study,gates,ledger,clock,write=self.fixture(Path(td))
                if mode=='missing':ledger['entries'].pop()
                if mode=='failure':ledger['entries'][5]['state']='FAIL'
                if mode=='earlier-failure':ledger['failed_attempts']=[dict(TEST_ONLY=True,state='FAIL')]
                if mode=='wrong-order':ledger['entries'][2],ledger['entries'][3]=ledger['entries'][3],ledger['entries'][2]
                if mode=='reused-id':
                    e=ledger['entries'][2];identity=ledger['entries'][0]['boot_id'];e['boot_id']=identity;gates[e['image']]['acquisition_boot_ids'][e['cohort_index']]=identity
                if mode=='overlap':
                    e=ledger['entries'][3];record=write('overlap.json',dict(started_utc='2026-11-21T00:00:00+00:00',release_after_recovery_utc='2026-11-21T00:00:01+00:00'));e['result']=record;gates[e['image']]['sessions'][e['cohort_index']]=record
                bound=write('matched-capacity-attempts.json',ledger)
                with patch.object(a,'validate_declaration'),patch.object(a.p,'physical_qualification',return_value=dict(clock_topology=clock)):
                    if mode=='good':a.verify_study(d,study,gates,bound)
                    else:
                        with self.assertRaises(ValueError):a.verify_study(d,study,gates,bound)


if __name__=='__main__':unittest.main()
