"""Declared-math fixtures are entirely synthetic and never physical admissions."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import analyze_retained29_cost_cohort as a


def boots(ratio=None):
    rows=[]
    hardware=dict(cfg='TEST_ONLY',l1i_bytes=32768,l1d_bytes=32768,l2_bytes=16384)
    for visit in a.promotion.canonical_visits():
        plan=visit['plan'];commands=[]
        for position,case in enumerate(plan['cases']):
            cells=[]
            for repeat in range(plan['repeats']):
                off=10**(repeat+2)
                value=1 if ratio is None else ratio(visit,case,repeat)
                on=int(off*value)
                for order in range(2):
                    enabled=(repeat&1)^order
                    cells.append(dict(repeat=repeat,order=order,enabled=enabled,whole=on if enabled else off,
                        steady=(on if enabled else off)//2,resource={k:repeat+enabled for k in a.RESOURCE},
                        control=dict(TEST_ONLY=True,retained_control_writes=str(2*enabled)),prefix={'TEST_ONLY':True},replay={'TEST_ONLY':True}))
            commands.append(dict(case=case,complete_cells=2*plan['repeats'],cells=cells))
        rows.append(dict(visit_id=visit['id'],boot_order=visit['order'],round=visit['round'],rotation=plan['rotation'],
            acquisition_boot_id=str(uuid.UUID(int=visit['order']+1,version=4)),role=plan['role'],workload=plan['workload'],
            session=dict(TEST_ONLY=True,path='synthetic-'+visit['id'],sha256='0'*64,bytes=0),
            started_utc='TEST_ONLY',released_utc='TEST_ONLY',hardware=hardware,
            artifacts=dict(TEST_ONLY=True),programs=dict(TEST_ONLY=True),commands=commands))
    return rows


class Math(unittest.TestCase):
    def test_neutral_complete_cohort_is_valid(self):
        r=a.estimate(boots());self.assertEqual(r['primary']['ratio'],1)
        self.assertEqual(r['counts'],dict(performance_boots=15,pilot_boots=1,configurations=10,
            performance_cells=720,performance_pairs=360,primary_joint_pairs=120))
        self.assertEqual(len(r['raw_cells']),744)
        self.assertIn('No bootstrap',r['uncertainty'])
    def test_exact_repeat_boot_configuration_hierarchy_not_ratio_of_sums(self):
        def ratio(visit,case,repeat):
            if case['mask']!=15:return 1
            return (1,4,1,4)[repeat] * (1 if visit['round'] is None else (1,2,4)[visit['round']]) * (1 if case['kib']==32 else 4)
        r=a.estimate(boots(ratio))
        self.assertAlmostEqual(r['primary']['ratio'],8,places=10)
        joint32=next(x for x in r['configurations'] if x['mask']==15 and x['workload']=='scan' and x['kib']==32)
        self.assertAlmostEqual(joint32['endpoints']['whole']['ratio'],4,places=10)
        first=joint32['endpoints']['whole']['boots'][0]
        self.assertAlmostEqual(first['ratio'],2,places=10)
        self.assertNotAlmostEqual(first['ratio'],first['on_sum']/first['off_sum'],places=4)
        self.assertEqual(first['all_cell_sum'],first['on_sum']+first['off_sum'])
    def test_all10_configurations_equal_weight_not_cycle_or_workload_weighted(self):
        def ratio(visit,case,repeat):return 1024 if case['mask']==15 and case['workload']=='scan' and case['kib']==32 else 1
        r=a.estimate(boots(ratio));self.assertAlmostEqual(r['primary']['ratio'],2,places=10)
    def test_boot_cluster_keeps_footprints_and_masks_together(self):
        def ratio(visit,case,repeat):
            if visit['round'] is None:return 1
            return (1,4,1)[visit['round']] if case['kib']==32 else (4,1,1)[visit['round']]
        r=a.estimate(boots(ratio));clusters=[x for x in r['boot_clusters'] if x['workload']=='scan']
        self.assertEqual(len(clusters),3)
        self.assertTrue(all(len(c['members'])==6 for c in clusters))
        vectors=[[(m['kib'],m['mask'],round(m['endpoints']['whole']['ratio'],8)) for m in c['members']] for c in clusters]
        self.assertEqual({x[2] for x in vectors[0] if x[0]==32},{1})
        self.assertEqual({x[2] for x in vectors[0] if x[0]==128},{4})
        row=next(x for x in r['configurations'] if x['workload']=='scan' and x['kib']==32 and x['mask']==15)
        self.assertEqual([round(b['ratio'],8) for b in row['endpoints']['whole']['boots']],[1,4,1])
        self.assertEqual([round(x,8) for x in row['endpoints']['whole']['boot_ratio_range']],[1,4])
        self.assertEqual(len({p['boot_id'] for p in r['paired_repeats'] if p['phase']=='performance'}),15)
    def test_diagnostics_and_steady_never_replace_primary(self):
        def ratio(visit,case,repeat):return 2 if case['mask']==15 else .5
        r=a.estimate(boots(ratio));self.assertAlmostEqual(r['primary']['ratio'],2)
        self.assertEqual((r['primary']['mask'],r['primary']['endpoint']),(15,'whole'))
        self.assertTrue(all(s['role']!='primary' for s in r['summaries'] if s['endpoint']=='steady'))
        self.assertAlmostEqual(next(s['ratio'] for s in r['summaries'] if s['mask']==9 and s['endpoint']=='whole'),.5)
    def test_pilot_values_are_retained_but_not_aggregated(self):
        data=boots();pilot=data[0]
        for command in pilot['commands']:
            for cell in command['cells']:
                if cell['enabled']:cell['whole']*=1000
        r=a.estimate(data);self.assertEqual(r['primary']['ratio'],1)
        self.assertTrue(any(c['whole']>100000 for c in r['raw_cells'] if c['phase']=='pilot-functional-only'))
    def test_missing_boot_command_repeat_reused_uuid_and_wrong_geometry_reject(self):
        changes=[lambda b:b.pop(),lambda b:b[1]['commands'].pop(),lambda b:b[1]['commands'][0]['cells'].pop(),
            lambda b:b[1].update(acquisition_boot_id=b[0]['acquisition_boot_id']),
            lambda b:b[1].update(hardware=dict(l1i_bytes=32768,l1d_bytes=32768,l2_bytes=4096)),
            lambda b:b[1]['commands'][0]['cells'][0].update(whole=0),
            lambda b:[x['hardware'].update(l2_bytes=4096) for x in b],lambda b:b.reverse()]
        for change in changes:
            data=copy.deepcopy(boots());change(data)
            with self.assertRaises(ValueError):a.estimate(data)


class Admission(unittest.TestCase):
    def test_complete_gate_is_recomputed_and_external_sha_required(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'gate.json';gate=dict(state='PASS complete fixed COST cohort admitted for primary analysis',primary_analysis_ready=True,cohort={},ledger={})
            path.write_text(json.dumps(gate));sha=a.promotion.binding(path)['sha256']
            with patch.object(a.promotion,'verify_complete',return_value=gate) as verify:
                a.load_complete(path,sha);verify.assert_called_once()
            with self.assertRaisesRegex(ValueError,'external complete'):a.load_complete(path,'0'*64)
            with patch.object(a.promotion,'verify_complete',side_effect=ValueError('subset/failure')):
                with self.assertRaises(ValueError):a.load_complete(path,sha)
            with patch.object(a.promotion,'verify_complete',return_value=dict(gate,primary_analysis_ready=False)):
                with self.assertRaisesRegex(ValueError,'changed'):a.load_complete(path,sha)
    def test_simulation_or_legacy_gate_never_substitutes_for_complete_promotion(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'gate.json';path.write_text(json.dumps(dict(state='PASS native/model/oldscope only',primary_analysis_ready=True)))
            with self.assertRaisesRegex(ValueError,'only complete promotion'):a.load_complete(path,a.promotion.binding(path)['sha256'])

    def test_mutated_bound_json_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'input.json';path.write_text('{}');record=a.promotion.binding(path);path.write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError,'bound JSON changed'):a.bound_json(record)
    def test_synthetic_exports_are_labeled_and_reproducible(self):
        report=dict(schema='bp-retained29-cost-analysis-v1',scope=a.TEST_SCOPE,inputs={'TEST_ONLY':'synthetic fixtures'},estimates=a.estimate(boots()))
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);a.write_outputs(report,root/'one');a.write_outputs(report,root/'two')
            for name in ('analysis.json','RESULTS.md','cells.csv','paired-repeats.csv','configurations.csv'):
                self.assertEqual((root/'one'/name).read_bytes(),(root/'two'/name).read_bytes())
            self.assertIn('TEST ONLY', (root/'one/RESULTS.md').read_text())
            with (root/'one/cells.csv').open() as f:rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),744);self.assertIn('minor_faults',rows[0]);self.assertIn('control_json',rows[0])
            for name in ('cells.csv','paired-repeats.csv','configurations.csv'):
                with (root/'one'/name).open() as f:self.assertTrue(all(row['scope']==a.TEST_SCOPE for row in csv.DictReader(f)))
            with self.assertRaises(FileExistsError):a.write_outputs(report,root/'one')


class Integration(unittest.TestCase):
    def test_synthetic_closed_promotion_to_analysis_uses_all_runs_and_labels_exports(self):
        import test_retained29_cost_cohort as fixtures
        fixtures.Complete.setUpClass()
        fixture=fixtures.Complete(methodName='test_all16_actual_console_rows_boots_and_recovery_required')
        fixture.setUp()
        try:
            path=Path(fixture.cohort['path'])
            fixture.cohort=fixtures.write(path,dict(TEST_ONLY=True,physical_qualification={'TEST_ONLY':'no physical proof'}))
            ledger=fixture.build();gate=fixture.verify(ledger)
            gate_path=fixture.root/'complete.json';gate_path.write_text(json.dumps(gate))
            # Only absent physical admissions are mocked. The complete gate,
            # real source parser over synthetic closed consoles, source bindings,
            # extraction and estimator execute normally. No board/model/reader.
            with patch.object(a.promotion,'static_admission',side_effect=fixture.static),patch.object(a.promotion.cost,'acquisition_ready'):
                report=a.analyze(gate_path,a.promotion.binding(gate_path)['sha256'])
            report['scope']=a.TEST_SCOPE
            self.assertEqual(report['estimates']['counts']['performance_boots'],15)
            self.assertEqual(len(report['estimates']['boot_clusters']),16)
            self.assertEqual(report['inputs']['sessions'],gate['sessions'])
            out=fixture.root/'TEST_ONLY-analysis';a.write_outputs(report,out)
            self.assertIn('TEST ONLY',(out/'RESULTS.md').read_text())
            self.assertEqual(json.loads((out/'analysis.json').read_text())['scope'],a.TEST_SCOPE)
        finally:fixture.tearDown()


if __name__=='__main__':unittest.main()
