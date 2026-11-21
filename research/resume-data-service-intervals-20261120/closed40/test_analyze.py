import copy
import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('intervals',Path(__file__).with_name('analyze.py'))
A=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(A)


def guest():
    return {'warm_begin':1,'timed_begin':10,'timed_end':30,'complete_ring_cycles':20,
            'regions':[{'context':c,'base':hex(0x1000+c*0x1000),'bytes':1024}for c in range(4)]}


def event(kind,time,**fields):
    domain='be'if kind in ('begin','end')else'dcache'
    return dict(event=kind,domain=domain,global_cycle=time,cycle=time+(1001 if domain=='be' else 1000),**fields)


def miss(start,first,line=0x4000,target=False,phase=None,epoch=None):
    rows=[event('reference',start,address=hex(line+8),line=hex(line),context=0,thread=0,
                operation='load',outcome='miss',l1_resident=False,target=target,phase=phase,epoch=epoch)]
    # Rotated fill order must remain valid; complete occurs with the last beat.
    masks=(16,32,64,128,1,2,4,8)
    rows += [event('fill_beat',first+i,line=hex(line),way=3,mask=mask)for i,mask in enumerate(masks)]
    rows += [event('fill_complete',first+7,line=hex(line),way=3)]
    return rows


def audit(rows,requests=None):
    refs=[r for r in rows if r['event']=='reference']
    return {'validation':'passed','requests':requests or [],'stats':{
        'accepted_cached_references':len(refs),'accepted_cached_loads':sum(r['operation']=='load'for r in refs),
        'accepted_cached_stores':sum(r['operation']=='store'for r in refs),
        'ordinary_misses':sum(r['outcome']=='miss'for r in refs),'normal_l1_hits':sum(r['outcome']=='l1_hit'for r in refs),
        'matched_normal_fill_beats':sum(r['event']=='fill_beat'for r in rows),
        'matched_complete_normal_refills':sum(r['event']=='fill_complete'for r in rows),
        'actual_replacement_evictions':sum(r['event']=='eviction'for r in rows)}}


class IntervalTests(unittest.TestCase):
    def test_rotated_eight_beats_pair_and_distinguish_first_complete(self):
        rows=miss(2,7)
        report,pairs=A.analyze(rows,guest(),audit(rows))
        self.assertEqual(pairs[0]['miss_to_first_accepted_beat_cycles'],5)
        self.assertEqual(pairs[0]['miss_to_complete_cycles'],12)
        self.assertEqual(pairs[0]['beat_masks'],[16,32,64,128,1,2,4,8])
        self.assertEqual(report['domain_edge_minus_global_offsets'],{'dcache':1000})

    def test_carry_in_and_out_are_clipped_and_full_latencies_retained(self):
        rows=miss(0,12)+miss(28,31,line=0x8000)
        report,_=A.analyze(rows,guest(),audit(rows))
        clipped=report['timed_ring']['all_pending_to_complete_clipped']
        self.assertEqual(clipped['union_pending_cycles'],11) # [10,19)+[28,30)
        self.assertEqual(clipped['carry_in_intervals'],1)
        self.assertEqual(clipped['carry_out_intervals'],1)
        self.assertEqual(report['timed_ring']['misses_accepted_in_window']['miss_to_complete_cycles']['max'],10)

    def test_pending_union_overlap_is_not_sum_or_critical_stall(self):
        result=A.union_intervals([(0,10),(1,18),(5,8)])
        self.assertEqual(result['sum_individual_pending_cycles'],30)
        self.assertEqual(result['union_pending_cycles'],18)
        self.assertEqual(result['cycles_with_at_least_two_pending'],9)
        self.assertEqual(result['multiplicity_excess_cycles'],12)
        self.assertEqual(result['max_pending'],3)

    def test_touching_and_zero_intervals_do_not_create_overlap(self):
        result=A.union_intervals([(0,5),(5,9),(4,4)])
        self.assertEqual(result['union_pending_cycles'],9)
        self.assertEqual(result['cycles_with_at_least_two_pending'],0)
        self.assertEqual(result['max_pending'],1)

    def test_distinct_line_overlap_pairs_by_line(self):
        rows=miss(0,3,line=0x4000)+miss(1,11,line=0x8000)
        rows=sorted(rows,key=lambda row:row['global_cycle'])
        report,pairs=A.analyze(rows,guest(),audit(rows))
        self.assertEqual(len(pairs),2)
        self.assertEqual(report['all_program']['pending_to_complete']['max_pending'],2)
        self.assertEqual(report['all_program']['pending_to_complete']['union_pending_cycles'],18)

    def test_same_line_later_miss_gets_distinct_pair(self):
        rows=miss(0,3)+miss(40,42)
        report,pairs=A.analyze(rows,guest(),audit(rows))
        self.assertEqual([r['miss_id']for r in pairs],[1,2])
        self.assertEqual(report['all_program']['misses'],2)

    def test_target_timed_subset_and_BE_offset(self):
        rows=[event('begin',11,context=0,epoch=8,phase='timed',pc='0x100')]
        rows+=miss(12,15,line=0x1000,target=True,phase='timed',epoch=8)
        rows+=[event('end',23,context=0,epoch=8,phase='timed',pc='0x104')]
        report,_=A.analyze(rows,guest(),audit(rows,[{'phase':'timed','stats':{'ordinary_misses':1}}]))
        self.assertEqual(report['target_timed']['misses'],1)
        self.assertEqual(report['domain_edge_minus_global_offsets']['be'],1001)

    def test_zero_miss_negative_control_is_valid(self):
        row=event('reference',15,address='0x4000',line='0x4000',context=0,thread=0,operation='load',
                  outcome='l1_hit',l1_resident=True,target=False,phase=None,epoch=None)
        report,pairs=A.analyze([row],guest(),audit([row]))
        self.assertEqual(pairs,[])
        self.assertIsNone(report['all_program']['miss_to_complete_cycles']['mean'])
        self.assertEqual(report['timed_ring']['all_pending_to_complete_clipped']['union_pending_cycles'],0)

    def test_unmatched_duplicate_incomplete_and_wrong_way_fills_rejected(self):
        original=miss(0,3)
        variants=[original[1:],original[:-1],original+[copy.deepcopy(original[-1])],
                  original[:3]+[copy.deepcopy(original[2])]+original[3:]]
        wrong=copy.deepcopy(original);wrong[4]['way']=4;variants.append(wrong)
        early=copy.deepcopy(original);early[-1]['global_cycle']=9;early[-1]['cycle']=1009;variants.append(early)
        for rows in variants:
            with self.subTest(rows=len(rows)),self.assertRaises(ValueError):A.analyze(rows,guest(),audit(rows))

    def test_address_mask_chronology_and_domain_consistency_rejected(self):
        original=miss(0,3)
        changes=(lambda r:r[0].update(address='0x4040'),lambda r:r[0].update(line='0x4001'),
                 lambda r:r[1].update(mask=3),lambda r:r[2].update(global_cycle=2),
                 lambda r:r[2].update(cycle=999),lambda r:r[1].update(line='0x8000'))
        for change in changes:
            rows=copy.deepcopy(original);change(rows)
            with self.assertRaises(ValueError):A.analyze(rows,guest(),audit(rows))

    def test_source_count_and_guest_bounds_mismatch_rejected(self):
        rows=miss(0,3);wrong=audit(rows);wrong['stats']['ordinary_misses']+=1
        with self.assertRaisesRegex(ValueError,'count differs'):A.analyze(rows,guest(),wrong)
        bounds=guest();bounds['complete_ring_cycles']=21
        with self.assertRaisesRegex(ValueError,'bounds'):A.analyze(rows,bounds,audit(rows))

    def test_ambiguous_same_line_pending_miss_rejected(self):
        rows=miss(0,3);rows.insert(1,copy.deepcopy(rows[0]))
        with self.assertRaisesRegex(ValueError,'ambiguous'):A.analyze(rows,guest(),audit(rows))

    def test_target_phase_or_corpus_mismatch_rejected(self):
        rows=miss(12,15,line=0x8000,target=True,phase='timed',epoch=8)
        with self.assertRaisesRegex(ValueError,'own corpus'):A.analyze(rows,guest(),audit(rows))


if __name__=='__main__':unittest.main()
