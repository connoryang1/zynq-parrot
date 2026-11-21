#!/usr/bin/env python3
"""Read-only cold08 reference preparation and frozen admission; never runs model."""
import argparse
import json
from pathlib import Path
import shutil
from common import *
from canonical import extract,MAX_CANONICAL_BYTES
from protocol import parse


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--build',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    require(not args.output.exists(),'preserve existing admission')
    p=proposal();build=json.loads(args.build.read_text());freeze=json.loads((HERE/'source-freeze.json').read_text())
    require(build['state']=='BUILT-NOT-TARGET-QUALIFIED' and build['baseline_relink']['sha256']==MODEL_SHA,
            'SP untouched-copy relink/build gates incomplete')
    verify(build['binary']);require(identities(tree(Path(build['binary']['path']).parent))==identities(build['final_files']),
                                  'copied SP build changed')
    require(shutil.disk_usage(HERE).free>RESERVE+ARTIFACT_ALLOCATION,'reserve/artifact budget unavailable')
    strict=json.loads((ORIGINAL/'advisory-strict01/verification.json').read_text())
    counters=json.loads((ORIGINAL/'advisory-counter01/verification.json').read_text())
    run=json.loads((ORIGINAL/'advisory/verification.json').read_text())
    integrity=json.loads((ORIGINAL/'integrity/verification.json').read_text())
    require(strict['accepted'] is True and counters['state'].startswith('PASS actual counter transitions') and
            run['state'].startswith('PASS complete scoped wholecore') and integrity['state'].startswith('PASS'),
            'original SP fixtures/audits incomplete')
    fixture_manifest=strict['bindings']['fixture_manifest'];verify(fixture_manifest)
    fixture=json.loads(Path(fixture_manifest['path']).read_text())
    records=[bind(PROPOSAL),bind(NATIVE),bind(args.build),bind(HERE/'source-freeze.json'),build['binary'],
       bind(ORIGINAL/'actual-source-list.json'),bind(ORIGINAL/'geometry.json'),bind(ORIGINAL/'session.json'),
       bind(ORIGINAL/'advisory-strict01/verification.json'),bind(ORIGINAL/'advisory-counter01/verification.json'),
       bind(ORIGINAL/'advisory/verification.json'),bind(ORIGINAL/'integrity/verification.json'),fixture_manifest,
       fixture['elf'],fixture['source']]
    reference={name:bind(ORIGINAL/'advisory'/file) for name,file in
               (('elf','prog.riscv'),('nbf','prog.nbf'),('trace','trace.fst'),('log','run.log'))}
    records+=list(reference.values());reference['returncode']=run['actual_returncode']
    reference['guest']=parse(Path(reference['log']['path']).read_text(),reference['returncode'])
    require(reference['elf']['sha256']==fixture['elf']['sha256'],'cold08 ELF source identity mismatch')
    reader=p['reader'];verify(reader);records.append(reader)
    paths=[SP/'testing/check_run.py',SP/'testing/rtl/retained-advisory-trace/validate.py',
        SP/'research/retained-use-observation-20261121/verify_counters.py',
        SP/'research/retained-use-observation-20261121/build_full.py',
        SP/'research/retained-use-observation-20261121/run_firsttouch.py',HERE/'framing.py']
    records += [bind(x) for x in paths]+[bind(x) for x in HERE.glob('*.py')]+freeze['linked_libraries']
    frozen={r['path']:r for r in records}
    for r in frozen.values():verify(r)
    for r in freeze['compiled_sources'].values():verify(r)
    out=HERE/'reference01';require(not out.exists(),'reference extraction must be fresh');out.mkdir()
    canonical={}
    for name,leaves in p['reader_domains'].items():
        require(len(leaves)<=256,'reader domain exceeds unchanged256-signal reader')
        canonical[name]=extract(reader['path'],reference['trace']['path'],leaves,out/name,False)
    save(out/'canonical.json',canonical)
    records=[bind(out/'canonical.json')]+[x['canonical_file'] for x in canonical.values()]
    frozen.update({r['path']:r for r in records})
    for r in frozen.values():verify(r)
    for r in freeze['compiled_sources'].values():verify(r)
    save(args.output,dict(state='FROZEN-SP-COLD08-awaiting-root-target-review',proposal=bind(PROPOSAL),
        native_identities=bind(NATIVE),build=bind(args.build),source_freeze=bind(HERE/'source-freeze.json'),
        original_model=freeze['model'],copied_model=build['binary'],source_files=build['final_files'],
        frozen_inputs=frozen,compiled_sources=freeze['compiled_sources'],original_generated_files=freeze['original_generated_files'],
        original_generated_root=str(Path(freeze['model']['path']).parent),reader=reader,domains=p['reader_domains'],
        writer_leaves=p['leaves'],original_canonical=canonical,reference=reference,fixture_manifest=fixture_manifest,
        environment=freeze['environment'],linked_libraries=freeze['linked_libraries'],
        qualifier_output=str(HERE/'qualification01'),one_shot_claim=str(HERE/'qualification-attempt01.json'),
        budget=dict(native_seconds=180,host_seconds=360,FST_bytes=CAP,attempts=1,reader_seconds_per_domain=600,
                    minimum_free_reserve_bytes=RESERVE,fixed_artifact_allocation_bytes=ARTIFACT_ALLOCATION,
                    canonical_bytes_per_file=MAX_CANONICAL_BYTES),
        scope='One unchanged static16KiB SP cold08 observation qualification only; no applications/modes/latencies/row runs. No old4KiB effect bridge.'))
    print(args.output,bind(args.output)['sha256'])


if __name__=='__main__':main()
