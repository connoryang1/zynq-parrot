#!/usr/bin/env python3
"""One sequential0→15 complete qualification; explicit reviewed admission SHA required."""
import argparse
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time
from common import *
from canonical import extract, equivalent

sys.path.insert(0, str(NATURAL))
from protocol import parse, PASS
from verify_finalized_trace import framing


def constraints(a):
    require(a['state'] == 'FROZEN-awaiting-root-checkpoint-review-no-target-run', 'not frozen admission')
    require(a['mode_order'] == [0,15] and a['budget'] == dict(native_seconds=1800,
            host_seconds=1980,FST_bytes_per_arm=CAP,max_pair_FST_bytes=2*CAP,attempts_per_mode=1),
            'qualification resource/order changed')
    require(a['proposal']['sha256'] == PROPOSAL_SHA and a['original_model']['sha256'] == MODEL_SHA,
            'wrong reviewed model/proposal')
    require(len(a['leaves']) == 252 and a['leaves'] == proposal()['filter_leaves'], 'leaf union changed')


def mode_admitted(mode, rows):
    require((mode == 0 and not rows) or
            (mode == 15 and len(rows) == 1 and rows[0]['mode'] == 0 and
             rows[0]['state'] == 'PASS-complete-output-and-all252-leaf-byte-equivalence'),
            'mode0 prerequisite missing or duplicate attempt')


def claim_once(path, admission, output):
    with Path(path).open('x') as claim:
        json.dump(dict(admission=bind(admission),output=str(output),pid=os.getpid(),
                       state='one-attempt-claimed-no-retry'),claim)
        claim.flush(); os.fsync(claim.fileno())


def validate(a, actual_sha):
    require(actual_sha == bind(a['_path'])['sha256'], 'root-reviewed admission hash differs')
    constraints(a)
    for r in a['frozen_inputs'].values(): verify(r)
    build = json.loads(Path(a['build']['path']).read_text())
    require(build['state'] == 'BUILT-NOT-TARGET-QUALIFIED' and
            build['binary'] == a['copied_model'] and build['baseline_relink']['sha256'] == MODEL_SHA,
            'not the qualified host-only build')
    require(identities(tree(Path(a['copied_model']['path']).parent)) == identities(a['source_files']),
            'copied model objects/sources changed')
    require(identities(tree(Path(proposal()['original_generated_root']))) ==
            identities(proposal()['original_generated_files']), 'original generated model changed')


def target_rows(text):
    return [s for s in text.replace('\r','').splitlines()
            if s.startswith('RETAINED_RESUME_') or s == PASS or
            'CORE PASS' in s or 'Returning from ps_main with RC:' in s or s.endswith('BSG PASS')]


def complete_output(text, mode, rc, reference_text, reference_guest):
    guest = parse(text, mode, rc)
    require(guest == reference_guest, 'complete guest observations differ')
    require(target_rows(text) == target_rows(reference_text), 'target/CORE/host protocol bytes differ')
    return guest


def limits():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP))


def loader(binary, env):
    result = subprocess.run(['ldd', binary], env=env, capture_output=True, text=True, timeout=10)
    require(result.returncode == 0 and 'not found' not in result.stdout, 'native loader preflight failed')
    records = []
    for line in result.stdout.splitlines():
        for word in line.split():
            if word.startswith('/') and Path(word).is_file(): records.append(bind(word))
    return result.stdout, records


def qualify(admission, approval_sha, output):
    output = fresh_home(output)
    a = json.loads(Path(admission).read_text()); a['_path'] = str(Path(admission).resolve())
    validate(a, approval_sha)
    require(str(output) == a['qualification_output'], 'output differs from fixed admitted directory')
    require(shutil.disk_usage(output.parent).free > 2*CAP + 1024*1024*1024,
            'insufficient reserved qualification/audit disk')
    # An exclusive, durable local claim makes a fresh output path insufficient
    # to restart this admission after a failure. Never remove/reuse the claim.
    claim_once(a['one_shot_claim'],admission,output)
    output.mkdir()
    manifest = output/'qualification.json'
    state = dict(state='QUALIFYING-no-new-effect-sample', admission=bind(admission),
                 approval_sha256=approval_sha, budget=a['budget'], modes=[], source=bind(__file__))
    save(manifest,state)
    env = dict(os.environ)
    # No ambient runtime image patches, trace timeout or inherited delayed input.
    for key in list(env):
        if key.startswith(('BSG_RUNTIME_PATCH_','BSG_TRACE_')): env.pop(key)
    env.update(a['environment'])
    try:
        for mode in (0,15):
            mode_admitted(mode,state['modes'])
            validate(a, approval_sha)
            reference = a['references'][str(mode)]
            folder = output / ('mode%d' % mode); folder.mkdir()
            row = dict(mode=mode,state='REFERENCE-extraction-before-target')
            state['modes'].append(row); save(manifest,state)
            old_framing = framing(Path(reference['trace']['path']))
            original = extract(a['reader']['path'],reference['trace']['path'],a['leaves'],
                               folder/'original-canonical',False)
            row['original_canonical'] = original; save(manifest,state)
            runtime = folder/'runtime'; runtime.mkdir(); fst = runtime/'trace.fst'
            command = [a['copied_model']['path'],'+c_args='+reference['nbf']['path']+' 1800000',
                       '+bsg_trace='+str(fst)]
            stdout, libraries = loader(a['copied_model']['path'],env)
            (runtime/'loader-preflight.log').write_text(stdout)
            require(libraries == reference['linked_libraries'], 'linked native library identities differ')
            # Reference extraction can take minutes. Recheck frozen bytes at
            # the actual launch boundary as well as before/after each arm.
            validate(a,approval_sha)
            row.update(state='RUNNING-one-attempt',argv=command,cwd=str(runtime),libraries=libraries)
            save(manifest,state); start=time.monotonic()
            with (runtime/'run.log').open('wb') as log:
                result = subprocess.run(command,cwd=runtime,env=env,stdout=log,
                                        stderr=subprocess.STDOUT,timeout=HOST_SECONDS,preexec_fn=limits)
            row.update(returncode=result.returncode,elapsed_seconds=time.monotonic()-start,
                       log=bind(runtime/'run.log')); save(manifest,state)
            require(result.returncode == reference['returncode'], 'terminal returncode differs')
            guest = complete_output((runtime/'run.log').read_text(),mode,result.returncode,
                    Path(reference['log']['path']).read_text(),json.loads(Path(reference['guest']['path']).read_text()))
            save(runtime/'guest-observations.json',guest)
            require(0 < fst.stat().st_size < CAP, 'empty/capped FST')
            closed = framing(fst)
            require((closed['header_start_tick'],closed['header_end_tick']) ==
                    (old_framing['header_start_tick'],old_framing['header_end_tick']), 'complete FST endpoints differ')
            row.update(state='COMPLETE-checks-PASS-awaiting-event-equivalence',trace=bind(fst),
                       framing=closed,guest=bind(runtime/'guest-observations.json'))
            save(manifest,state)
            filtered = extract(a['reader']['path'],fst,a['leaves'],folder/'filtered-canonical',True)
            equivalent(original,filtered)
            validate(a,approval_sha)
            row.update(state='PASS-complete-output-and-all252-leaf-byte-equivalence',
                       filtered_canonical=filtered)
            save(manifest,state)
            print('mode',mode,row['state'],flush=True)
        state['state']='PASS-BOTH-original-arm-complete-output-and-all252-leaf-byte-equivalence'
    except BaseException as e:
        state.update(state='STOPPED-failure-preserved-no-retry-no-admission',error=repr(e))
        if state['modes'] and state['modes'][-1]['state'] != \
                'PASS-complete-output-and-all252-leaf-byte-equivalence':
            row=state['modes'][-1]; row['state']='FAIL-preserved'
            runtime=output/('mode%d'%row['mode'])/'runtime'
            for name in ('trace.fst','run.log'):
                if (runtime/name).is_file():row[name]=bind(runtime/name)
        raise
    finally:
        save(manifest,state)
        print(manifest,state['state'],flush=True)


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--admission',type=Path,required=True)
    ap.add_argument('--approval-sha',required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();qualify(args.admission,args.approval_sha,args.output)
