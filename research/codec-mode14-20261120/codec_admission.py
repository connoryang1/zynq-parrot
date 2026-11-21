#!/usr/bin/env python3
"""Strict codec-only closed-cohort admission and unchanged mode14 analysis."""
import argparse
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'linux-tests'))
import compare_scheduler_pipe_hint_mode14 as generic
from analyze_admitted_matrix import absolute_crosschecks, reverify_bindings
from audit_admitted_matrix import artifact, require, sha, timestamp, unique_file
from run_scheduler_pipe_hint import GUEST_ELF, GUEST_ZLIB, validate_transfer
from run_scheduler_tagged_replay import SHELL_PROMPT

ADMISSION = HERE/'admission.json'
ADMISSION_SHA = '731138cd7226294e02d85bfc7289dc9182f58fb702ad68186c57f56a05593fbd'


def verify_fixed_files(admission):
    records = [artifact(ADMISSION)]
    for binding in list(admission['files'].values())+list(admission['provenance'].values())+list(admission['frozen_analysis_sources'].values())+[admission['board_helper']]:
        require(artifact(Path(binding['path'])) == binding, 'fixed codec artifact changed: '+binding['path'])
        records.append(binding)
    for relative, digest in admission['host_sources'].items():
        require(sha(ROOT/relative) == digest, 'current source8 differs: '+relative)
    require(validate_transfer(Path(admission['files']['transfer']['path']),admission['identity']['elf_sha256']) is None,
            'codec ELF must retain its fixed gzip transfer')
    return records


def audit(acquisition_path):
    require(sha(ADMISSION) == ADMISSION_SHA, 'codec preregistration changed')
    admission = json.loads(ADMISSION.read_text())
    acquisition_path = acquisition_path.resolve()
    acquisition = json.loads(acquisition_path.read_text())
    require(acquisition.get('admission_sha256') == ADMISSION_SHA, 'acquisition has wrong codec preregistration')
    require(acquisition.get('all_attempts_declared') is True, 'complete attempt declaration required')
    require(not acquisition.get('failed_attempts'), 'failed/replacement attempts require a prospective coordinator amendment')
    visits = acquisition.get('primary', [])
    require(len(visits) == 4, 'codec primary requires exactly four chronological ABBA sessions')
    require('pilot_session_manifest' in acquisition, 'excluded baseline functional pilot required')
    records = verify_fixed_files(admission)+[artifact(acquisition_path)]
    scheduled = [dict(admission['pilot'],session_manifest=acquisition['pilot_session_manifest'])]
    for actual, expected in zip(visits,admission['primary_plan']):
        require(actual.get('label') == expected['label'], 'codec primary label/order differs from ABBA')
        scheduled.append(dict(expected,session_manifest=actual['session_manifest']))
    rows, seen = [], set()
    previous_end = timestamp(admission['created_utc'])
    # Complete provenance/configuration for every session precedes reading any
    # transcript or calculating any image contrast.
    for index, visit in enumerate(scheduled):
        pilot = index == 0
        path = Path(visit['session_manifest'])
        require(path.is_absolute(), 'session manifest path must be absolute')
        records.append(unique_file(path,seen,'session',content=True))
        session = json.loads(path.read_text())
        require(session.get('state') == 'complete', 'codec session incomplete')
        require(session.get('reservation') == admission['reservation_lock']
                and session.get('all_three_acknowledged') is True, 'codec reservation/acknowledgment differs')
        require(session.get('host') == admission['host'], 'codec host differs')
        start,end = timestamp(session['started_utc']),timestamp(session['released_utc'])
        require(previous_end <= start < end, 'codec sessions overlap/reverse/precede preregistration')
        previous_end = end
        require(session.get('host_source_sha256') == admission['host_sources'], 'codec frozen source8 differs')
        for relative,digest in admission['host_sources'].items():
            snapshot = path.parent/'host-sources'/relative
            require(snapshot.is_file() and not snapshot.is_symlink() and sha(snapshot) == digest,
                    'codec source8 snapshot changed: '+relative)
            records.append(artifact(snapshot))
        cells = session.get('plan',[])
        require(len(cells) == 1, 'codec requires one boot/guest execution per reservation')
        cell = cells[0]
        config = dict(admission['config'])
        if pilot:
            config.update({key:admission['pilot'][key] for key in ('loops','warmup','repeats')})
        for key,value in config.items():
            if key not in ('configured_entries','complete_policy_scope','resource_stats','terminal_handshake'):
                require(cell.get(key) == value, 'codec wrapper plan config differs: '+key)
        require(cell.get('host') == admission['host'], 'codec planned host differs')
        for key,target in (('elf_sha256','elf_sha256'),('bitstream_sha256','bitstream_sha256'),('control_sha256','control_program_sha256')):
            require(cell.get(key) == admission['identity'][target], 'codec planned identity differs: '+key)
        nbf = admission['files']['baseline_nbf' if visit['image']=='A' else 'control_nbf']
        for key,binding in (('nbf',nbf),('transfer',admission['files']['transfer']),('zlib_library',admission['files']['zlib_library'])):
            require(cell.get(key) == binding['path'], 'codec planned exact artifact path differs: '+key)
        require(cell.get('embedded_zlib_library') is True and cell.get('retention_probe') is None
                and cell.get('legacy_four_arg_cli') is False and cell.get('legacy_no_terminal_handshake') is False
                and cell.get('runtime_ms') == admission['runtime_ms'], 'codec delivery/terminal shape differs')
        log = path.parent/'0-deflate32-futex-early.log'
        require(cell.get('log') == str(log), 'codec planned transcript path differs')
        records.append(unique_file(log,seen,'transcript',content=True))
        status_path = log.with_suffix('.log.status.json')
        records.append(unique_file(status_path,seen,'status'))
        status = json.loads(status_path.read_text())
        require(status.get('status') == 'PASS' and status.get('runner_exit') == 0, 'codec runner did not complete PASS/exit0')
        for key,value in dict(admission['identity'],nbf_sha256=nbf['sha256']).items():
            require(status.get(key) == value, 'codec exact runner identity differs: '+key)
        for key,value in config.items():
            if key not in ('configured_entries','resource_stats','complete_policy_scope'):
                require(status.get(key) == value, 'codec status config differs: '+key)
        command = admission['pilot']['guest_command'] if pilot else admission['guest_command']
        require(status.get('command') == command, 'codec exact LD_LIBRARY_PATH guest command differs')
        require(status.get('zlib_transfer_encoding') == 'embedded-copy-v1'
                and 'embedded_elf_source' not in status and 'transfer_encoding' not in status
                and status.get('legacy_four_arg_cli') is False, 'codec library/ELF delivery encoding differs')
        rows.append(dict(label=visit['label'],image=visit['image'],pilot=pilot,path=log,
                         config=config,session_manifest=artifact(path)))
    for row in rows:
        text = row['path'].read_text(errors='replace').replace('\r','').replace('\x00','')
        helper = list(re.finditer(r'^BOARD_RUNNER_SOURCE_SHA256=([0-9a-f]{64})$',text,re.M))
        require(text.count('BOARD_RUNNER_SOURCE_SHA256') == len(helper) == 1
                and helper[0][1] == admission['board_helper']['sha256'], 'codec requires executed de54 helper on every boot')
        require('RUNNER_CLEANUP_SYNC_FAILED' not in text, 'codec helper sync failed')
        for terminal in (r'^PIPE_HINT_PASS$',r'CORE(?:\[0\])? PASS',r'BSG PASS'):
            matches = list(re.finditer(terminal,text,re.M))
            require(matches and all(m.end()<helper[0].start() for m in matches), 'codec helper marker precedes required terminal')
        confirmations = []
        for digest,guest_path in ((admission['identity']['zlib_library_sha256'],GUEST_ZLIB),
                                  (admission['identity']['elf_sha256'],GUEST_ELF)):
            matches = list(re.finditer(r'^'+re.escape(digest+'  '+guest_path)+r'$',text,re.M))
            require(len(matches) == 1, 'actual guest '+guest_path+' hash missing/duplicated')
            confirmations.append(matches[0].start())
        library_banner = re.search(r'^PIPE_HINT_LIBRARY ',text,re.M)
        require(library_banner is not None and confirmations[0]<confirmations[1]<library_banner.start(),
                'codec actual library/ELF hashes must precede execution in that order')
        passed = re.search(r'^PIPE_HINT_PASS$',text,re.M)
        core = re.search(r'CORE(?:\[0\])? PASS',text)
        require(passed is not None and core is not None and passed.end()<core.start(), 'codec completion/CORE order differs')
        between = text[passed.end():core.start()]
        require(SHELL_PROMPT.search(between) is not None and 'poweroff -f' in between,
                'codec lacks normal shell return before CORE PASS')
        parsed = generic._load([row['path']])[0]
        require(parsed['config'] == row['config'], 'codec parsed fixed config differs')
        require(parsed.get('library') == admission['library_marker'], 'codec fixed runtime library banner differs')
        generic._runtime_46_bound(row['path'])
    images = generic.verify_reviewed_images('embedded46')
    for binding in records:
        require(artifact(Path(binding['path'])) == binding, 'codec input changed during admission')
    return dict(state='codec-protocol-accepted; image contrasts not calculated',admission=artifact(ADMISSION),
        acquisition=artifact(acquisition_path),audit_source=artifact(Path(__file__)),bindings=records,
        image_proof=images,pilot_excluded=dict(label='pilot-A',session=rows[0]['session_manifest']),
        sessions=[dict(label=r['label'],image=r['image'],session=r['session_manifest'],transcript=artifact(r['path'])) for r in rows[1:]],
        comparator_inputs=dict(baseline=[str(r['path']) for r in rows[1:] if r['image']=='A'],
                               control=[str(r['path']) for r in rows[1:] if r['image']=='B']))


def analyze(acquisition_path):
    accepted = audit(acquisition_path)
    paths = accepted['comparator_inputs']
    primary = generic.compare([Path(p) for p in paths['baseline']],[Path(p) for p in paths['control']],
                              20000,image_pair='embedded46')
    absolute = absolute_crosschecks(primary)
    reverify_bindings(accepted)
    return dict(state='codec-matched-kernel-comparison; interpretation-limited-no-automatic-optimization-claim',
        audit=accepted,primary=primary,absolute_whole_crosschecks=absolute,
        limits=json.loads(ADMISSION.read_text())['scope_limits'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('acquisition',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--analyze',action='store_true')
    args=parser.parse_args()
    if args.output.exists():
        parser.error('output must be new')
    try:
        result=analyze(args.acquisition) if args.analyze else audit(args.acquisition)
    except (OSError,ValueError,KeyError,TypeError) as error:
        print('Codec admission rejected: '+str(error),file=sys.stderr)
        return 1
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    return 0


if __name__=='__main__':
    sys.exit(main())
