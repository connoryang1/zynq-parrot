#!/usr/bin/env python3
"""Compact closed SP proof only. Never runs a model or edits frozen inputs."""
import json
from pathlib import Path
import shutil
from common import *
from qualify import validate


def main():
    out=HERE/'closed-qualification01';require(not out.exists(),'preserve closure')
    admission=HERE/'admission.json';a=json.loads(admission.read_text());a['_path']=str(admission)
    validate(a,bind(admission)['sha256'])
    journal=HERE/'qualification01/qualification.json';q=json.loads(journal.read_text())
    require(q['state']=='PASS-SP-COLD08-complete-three-domain-literal-equivalence-and-real-strict-observer-proofs',
            'require actual complete SP qualification')
    out.mkdir();copies={}
    def copy(src,relative):
        target=out/relative;target.parent.mkdir(parents=True,exist_ok=True)
        before=bind(src);shutil.copy2(src,target);after=bind(target)
        require((before['bytes'],before['sha256'])==(after['bytes'],after['sha256']),'compact copy changed')
        copies[relative]=dict(original=before,copy=after)
    copy(journal,'qualification.json')
    for n in ('run.log','process.json','admission.json','verification.json','loader.log'):
        copy(HERE/'qualification01/runtime'/n,'runtime/'+n)
    copy(HERE/'qualification01/hierarchy.tsv','hierarchy.tsv')
    external=[q['trace'],a['reference']['trace']];domains={}
    for name,now in q['domains'].items():
        old=a['original_canonical'][name]
        for key in ('sha256','events','changes_by_index','first_tick','final_tick','timescale','clean_EOF'):
            require(old[key]==now[key],'closed canonical equality metadata changed')
        for r in (old['canonical_file'],now['canonical_file']):verify(r);external.append(r)
        domains[name]=dict(events=now['events'],sha256=now['sha256'],literal_complete_bytes_equal=True,
                           original=old,filtered=now)
        save(out/(name+'-canonical.json'),domains[name])
        copy(HERE/'qualification01'/name/'selection.tsv',name+'-selection.tsv')
    for name in ('strict','observer'):
        copy(HERE/'qualification01'/name/'verification.json',name+'-verification.json')
        copy(HERE/'qualification01'/name/'selection.tsv',name+'-selection.tsv')
        copy(HERE/'qualification01'/(name+'.log'),name+'.log')
    strict=json.loads((out/'strict-verification.json').read_text());obs=json.loads((out/'observer-verification.json').read_text())
    require(strict['accepted'] is True and obs['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8]),'semantic verifier failure')
    source=bind(__file__)
    result=dict(state='CLOSED-PASS-SP-STATIC16KiB-COLD08-OBSERVATION-EQUIVALENCE',journal=bind(journal),
        admission=bind(admission),source=source,build=a['build'],source_freeze=a['source_freeze'],
        original_model=a['original_model'],qualified_observation_model=a['copied_model'],
        original_FST_bytes=a['reference']['trace']['bytes'],filtered_FST_bytes=q['trace']['bytes'],
        exact_writer_leaves=400,reader_domain_counts={k:len(v) for k,v in a['domains'].items()},domains=domains,
        complete_checked_protocol_equal=True,finalized_original_endpoints_equal=True,
        final_all_sources_and_original_copied_inventories_equal=True,
        real_strict_full_payload_and_normal_SRAM_proof=bind(out/'strict-verification.json'),
        real_counter_transitions_and_actual_GP0_proof=bind(out/'observer-verification.json'),
        actual_per_lane=dict(i=dict(published=1,hits=1,normal_L1_write_beats=8),d=dict(published=1,hits=1,normal_L1_write_beats=8)),
        model_geometry=dict(retained_I_lines=1280,retained_D_lines=1280,retained_sets=256,line_bytes=64,
            L2_banks=2,L2_sets_per_bank=64,L2_ways=2,L2_bytes=16384,L1I_bytes=32768,L1D_bytes=32768,observe=1,delay=0),
        native_elapsed_seconds=q['elapsed_seconds'],native_returncode=q['returncode'],qualifier_exit=0,
        budgets=q['budget'],attempts=1,retries=0,extensions=0,copies=copies,external_raw_immutable=external,
        scope='One unchanged synthetic cold08 observation qualification only. No FPGA fit/timing, capacity coverage/unique-capacity, calibrated memory latency or application performance claim. No old4KiB effect bridge; no future target admission.',
        terminal='Native knownGPIO-finalization exit−6 after complete guest/CORE/hostPASS, exactly as original; qualifier exits0. Same original scoped assertion support/exclusions.')
    save(out/'manifest.json',result)
    paths=[str(p.relative_to(ROOT)) for p in out.rglob('*') if p.is_file()]
    paths += [str(Path(__file__).resolve().relative_to(ROOT)),str((HERE/'QUALIFICATION_CLOSED.md').relative_to(ROOT)),
              str((out/'checkpoint-whitelist.json').relative_to(ROOT))]
    save(out/'checkpoint-whitelist.json',sorted(paths))
    print(bind(out/'manifest.json'));print(bind(out/'checkpoint-whitelist.json'))


if __name__=='__main__':main()
