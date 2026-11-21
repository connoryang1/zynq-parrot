#!/usr/bin/env python3
"""Admit the fixed scoped mode-14 matrix before any image-effect comparison."""
import argparse
import difflib
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from compare_scheduler_pipe_hint_mode14 import _load, _runtime_46_bound, verify_reviewed_images
from run_scheduler_pipe_hint import GUEST_ELF, build_guest_command, parse_args, validate_transfer

ROOT = Path(__file__).resolve().parents[1]
ADMISSION = ROOT / 'research/complete-policy-scope-20261120/admission.json'
ADMISSION_SHA = '501d6b12eb0fa10b9f1d298a2be6cb365695c2be7aac96b0984ea4ffe5f4a360'
LOCK = '/home/coyang/fpga-artifacts/pynq-session.lock'
HELPER_REVIEW = ROOT / 'research/runner-cleanup-sync-20261120/protocol.json'
HELPER_REVIEW_SHA = '8325114ac9affefdfa6fe24811edcfa8b1feb7d7888d554ba5b29135dded833f'
HELPER_OLD_SHA = '8b0f12b655d3bfc071e96d5b05018971500dcc125ca88936ce28eae6f971c283'
HELPER_NEW_SHA = 'de54badda52bcf716daaed5155d9be8674b3f0c137e0e411be075c7685c1db90'
REMOTE_HELPER = '/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq/run-blackparrot-interactive'
HOST_SOURCES = {
    'linux-tests/run_resume_workload_session.py': '8d527a4884ff548c0d025ee297a4e0fdc240dadb98b175898b56554e500dd112',
    'linux-tests/run_scheduler_pipe_hint.py': 'ea5663812145fe37fd35dd569d218ecc59b58181e2203250c39fe93a3242aeb3',
    'linux-tests/run_scheduler_tagged_replay.py': '0725b8532711c9b791c3a40942efe0df7374d772bbc4d67b59b24764b8c0f286',
    'codex-skills/bp-fpga-synthesis/scripts/stage_pynq_artifacts.sh': 'f827e7c4851ae06bd8b3f85fbe2b00fa6ae8d2105ef189956eaea2a51eb33b20',
    'codex-skills/bp-fpga-synthesis/scripts/power_cycle_pynq.sh': '7b85c3ebd10eac5175f0ce67c4fa529c0f12683ec631b70408c4d47aff0c8271',
    'codex-skills/bp-fpga-synthesis/scripts/wait_pynq_ready.sh': '4684cda9302bf0e4cd55a73a95ec1555e9c832d1c7dd4ec948eecee220ef656a',
    'codex-skills/bp-fpga-synthesis/scripts/load_pynq_overlay.sh': '0d3736302864de21500639bb0fb5f49224df955746825aed6e61d469ad69594a',
    'codex-skills/bp-fpga-synthesis/scripts/run_pynq_interactive.sh': '3038d850c036cc5a50821b6e665a38b12a7740bf68ac9929c650106a54c5c2e5',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(data)
    return digest.hexdigest()


def artifact(path):
    return dict(path=str(path.resolve()), bytes=path.stat().st_size, sha256=sha(path))


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(result.tzinfo is not None, 'acquisition/session timestamps require explicit timezone')
    return result


def unique_file(path, seen, kind, content=False):
    require(path.is_file() and not path.is_symlink(), kind + ' must be a regular non-symlink file')
    stat = path.stat()
    keys = [('path', str(path.resolve())), ('inode', (stat.st_dev, stat.st_ino))]
    if content:
        keys.append(('content', sha(path)))
    for category, key in keys:
        tagged = (kind, category, key)
        require(tagged not in seen, 'duplicate ' + kind + ' ' + category)
        seen.add(tagged)
    return artifact(path)


def board_helper_protocol(acquisition, plan):
    """Admit only the reviewed explicit post-program helper transition."""
    record = acquisition.get('board_helper_protocol', {})
    require(record.get('review_sha256') == HELPER_REVIEW_SHA
            and sha(HELPER_REVIEW) == HELPER_REVIEW_SHA, 'board helper protocol review missing or changed')
    review = json.loads(HELPER_REVIEW.read_text())
    for name in ('original', 'cleanup_sync', 'diff', 'operational_addendum', 'inspection', 'known_owned_cleanup'):
        binding = review[name]
        require(artifact(Path(binding['path'])) == binding, 'board helper evidence changed: ' + name)
    require(review['original']['sha256'] == HELPER_OLD_SHA
            and review['cleanup_sync']['sha256'] == HELPER_NEW_SHA, 'board helper source versions changed')
    old, new = (Path(review[name]['path']).read_bytes() for name in ('original', 'cleanup_sync'))
    anchor = b'  rmdir "$lock" 2>/dev/null || true\n'
    addition = (b'  if ! sync; then\n    echo "RUNNER_CLEANUP_SYNC_FAILED" >&2\n'
                b'    if [[ "$rc" -eq 0 ]]; then rc=74; fi\n  fi\n'
                b'  source_sha=$(sha256sum "$0" | awk \'{print $1}\')\n'
                b'  printf \'BOARD_RUNNER_SOURCE_SHA256=%s\\n\' "$source_sha"\n  exit "$rc"\n')
    require(old.count(anchor) == 1 and new == old.replace(anchor, anchor + addition),
            'board helper change is not exactly reviewed post-program cleanup')
    cleanup_start, trap = old.index(b'cleanup() {\n'), old.index(b'trap cleanup EXIT')
    require(cleanup_start < old.index(anchor) < trap
            and old[trap:] == new[new.index(b'trap cleanup EXIT'):]
            and old[:cleanup_start] == new[:cleanup_start], 'board helper launch/guard bytes changed')
    expected_diff = ''.join(difflib.unified_diff(old.decode().splitlines(True), new.decode().splitlines(True),
                                                fromfile='original', tofile='cleanup-sync'))
    require(Path(review['diff']['path']).read_text() == expected_diff, 'board helper diff proof mismatch')
    versions = {visit['label']: HELPER_OLD_SHA if i < 3 else HELPER_NEW_SHA for i, visit in enumerate(plan)}
    require(record.get('visit_versions') == versions, 'board helper per-visit version mapping mismatch')
    installation = record.get('installation', {})
    installation_path = Path(installation['path'])
    require(installation_path.is_absolute() and sha(installation_path) == installation['sha256'],
            'board helper installation binding mismatch')
    installed = json.loads(installation_path.read_text())
    require(installed.get('before_sha256') == HELPER_OLD_SHA
            and installed.get('after_sha256') == HELPER_NEW_SHA
            and installed.get('active_programs') == [] and installed.get('reservation') == LOCK
            and installed.get('atomic_replace') is True and installed.get('remote_helper_path') == REMOTE_HELPER,
            'board helper installation identity/reservation mismatch')
    return dict(review=artifact(HELPER_REVIEW), evidence=review,
                installation=artifact(installation_path), verified_utc=installed['verified_utc'],
                visit_versions=versions, first_cleanup_sync_visit_index=3)


def audit(acquisition_path):
    """Validate provenance and completeness; never calculate an image contrast."""
    acquisition_path = Path(acquisition_path).resolve()
    admission_record, acquisition_record = artifact(ADMISSION), artifact(acquisition_path)
    require(admission_record['sha256'] == ADMISSION_SHA, 'fixed admission hash mismatch')
    admission = json.loads(ADMISSION.read_text())
    acquisition = json.loads(acquisition_path.read_text())
    require(acquisition.get('admission_sha256') == ADMISSION_SHA, 'acquisition admission mismatch')
    require(acquisition.get('host_sources') == HOST_SOURCES, 'acquisition frozen host-eight mismatch')
    created = timestamp(acquisition['created_utc'])
    visits = acquisition.get('visits', [])
    plan = admission['reservation_plan']
    require(len(visits) == len(plan) == 8, 'complete fixed study requires exactly eight visits')
    helper_protocol = board_helper_protocol(acquisition, plan)
    helper_installed = timestamp(helper_protocol['verified_utc'])
    sessions, logs, seen, files = [], [], set(), {}
    previous_end, common_host = created, None
    fixed_config = {key: admission[key] for key in
                    ('loops', 'repeats', 'warmup', 'policy', 'sync', 'profile',
                     'working_set_kib', 'terminal_handshake')}
    fixed_config.update(configured_entries=32, complete_policy_scope=1, resource_stats=1)
    fixed_identity = {key: admission[key] for key in
                      ('elf_sha256', 'transfer_sha256', 'bitstream_sha256', 'control_program_sha256')}
    # Inspect every session's provenance first. An incomplete matrix is rejected
    # before its guest transcripts are opened or numerical results are parsed.
    for visit_index, (visit, scheduled) in enumerate(zip(visits, plan)):
        require(visit.get('label') == scheduled['label'], 'visit label/order differs from fixed ABBA plan')
        session_path = Path(visit['session_manifest'])
        require(session_path.is_absolute(), 'session manifest paths must be absolute')
        session_record_file = unique_file(session_path, seen, 'session')
        session = json.loads(session_path.read_text())
        if 'session_sha256' in visit:
            require(sha(session_path) == visit['session_sha256'], 'recorded session hash mismatch')
        require(session.get('state') == 'complete', 'every admitted session must be complete')
        require(session.get('reservation') == LOCK and session.get('all_three_acknowledged') is True,
                'session reservation/acknowledgment mismatch')
        start, end = timestamp(session['started_utc']), timestamp(session['released_utc'])
        require(previous_end <= start < end, 'session chronology overlaps, reverses, or precedes freeze')
        require((end <= helper_installed if visit_index < 3 else helper_installed <= start),
                'board helper transition is not between old/new complete visits')
        previous_end = end
        require(session.get('host_source_sha256') == HOST_SOURCES, 'session frozen host-eight mismatch')
        snapshots = {}
        for relative, expected in HOST_SOURCES.items():
            snapshot = session_path.parent / 'host-sources' / relative
            require(snapshot.is_file() and not snapshot.is_symlink() and sha(snapshot) == expected,
                    'frozen source snapshot bytes mismatch: ' + relative)
            snapshots[relative] = artifact(snapshot)
        host = session.get('host')
        require(isinstance(host, str) and bool(host), 'session host missing')
        common_host = host if common_host is None else common_host
        require(host == common_host, 'session host mismatch')
        cells = session.get('plan', [])
        require(len(cells) == len(scheduled['workloads']) == 2, 'session must have exactly two planned cells')
        image_sha = admission['baseline_nbf_sha256' if scheduled['image'] == 'A' else 'control_nbf_sha256']
        session_record = dict(label=scheduled['label'], image=scheduled['image'],
                              board_helper_sha256=helper_protocol['visit_versions'][scheduled['label']],
                              manifest=session_record_file, host_sources=snapshots,
                              started_utc=session['started_utc'], released_utc=session['released_utc'], logs=[])
        for index, (cell, workload) in enumerate(zip(cells, scheduled['workloads'])):
            require(all(cell.get(key) == value for key, value in fixed_config.items()
                        if key not in ('configured_entries', 'complete_policy_scope', 'resource_stats', 'terminal_handshake')),
                    'wrapper plan parameters differ from fixed admission')
            require(cell.get('workload') == workload and cell.get('host') == host,
                    'wrapper workload/boot order differs from fixed plan')
            require(cell.get('elf_sha256') == admission['elf_sha256']
                    and cell.get('bitstream_sha256') == admission['bitstream_sha256']
                    and cell.get('control_sha256') == admission['control_program_sha256'],
                    'wrapper plan ELF/bitstream/runner identity mismatch')
            require(cell.get('zlib_library') is None and cell.get('retention_probe') is None
                    and cell.get('embedded_zlib_library') is False
                    and cell.get('legacy_four_arg_cli') is False
                    and cell.get('legacy_no_terminal_handshake') is False
                    and cell.get('runtime_ms') == 3600000, 'wrapper plan delivery/terminal shape mismatch')
            for key, expected in (('nbf', image_sha), ('transfer', admission['transfer_sha256'])):
                path = Path(cell[key])
                require(path.is_absolute(), 'wrapper artifact paths must be absolute')
                if str(path) not in files:
                    files[str(path)] = artifact(path)
                require(files[str(path)]['sha256'] == expected, 'actual wrapper ' + key + ' hash mismatch')
            require(validate_transfer(Path(cell['transfer']), admission['elf_sha256']) is None,
                    'fixed scoped ELF must use its bound gzip transfer')
            log = Path(cell['log'])
            expected_log = session_path.parent / f'{index}-{workload}32-futex-early.log'
            require(log.is_absolute() and log == expected_log, 'wrapper log path/order differs from session plan')
            status = log.with_suffix(log.suffix + '.status.json')
            log_record = unique_file(log, seen, 'transcript', content=True)
            status_record = unique_file(status, seen, 'status')
            logs.append(dict(path=log, status=status, workload=workload, image=scheduled['image'],
                             board_helper_sha256=helper_protocol['visit_versions'][scheduled['label']],
                             transcript_record=log_record, status_record=status_record,
                             identity=dict(**fixed_identity, nbf_sha256=image_sha),
                             config=dict(**fixed_config, workload=workload)))
            session_record['logs'].append(str(log))
        sessions.append(session_record)
    # _load enforces unique boot contents, one boot, PASS + zero runner exit,
    # exact SCOPE, WHOLE/resource protocol order and all controller invariants.
    results = _load([row['path'] for row in logs])
    comparisons = {workload: {'baseline': [], 'control': []} for workload in admission['workloads']}
    bound_logs = []
    for row, result in zip(logs, results):
        require(result['config'] == row['config'], 'guest configuration differs from fixed admission')
        require(result['identity'] == row['identity'], 'guest identity differs from fixed admission')
        runner = json.loads(row['status'].read_text())
        require(runner.get('zlib_library_sha256') is None
                and runner.get('zlib_transfer_encoding') is None
                and runner.get('transfer_encoding') is None
                and runner.get('embedded_elf_source') is None
                and runner.get('legacy_four_arg_cli') is False,
                'runner status delivery/terminal shape differs from plain scoped gzip')
        guest = parse_args(['image.nbf', 'transfer', admission['elf_sha256'], 'result.log',
                            '--bitstream-sha256', admission['bitstream_sha256'], '--loops', '64',
                            '--repeats', '4', '--warmup', '32', '--policy', 'futex-early',
                            '--sync', 'futex', '--working-set-kib', '32', '--workload', row['workload']])
        require(runner.get('command') == build_guest_command(guest), 'runner guest command differs from fixed admission')
        text = row['path'].read_text(errors='replace').replace('\r', '').replace('\x00', '')
        helper_markers = list(re.finditer(r'^BOARD_RUNNER_SOURCE_SHA256=([0-9a-f]{64})$', text, re.MULTILINE))
        if row['board_helper_sha256'] == HELPER_OLD_SHA:
            require(not helper_markers and 'BOARD_RUNNER_SOURCE_SHA256' not in text,
                    'legacy board helper phase has an unexpected source marker')
        else:
            require(text.count('BOARD_RUNNER_SOURCE_SHA256') == 1
                    and len(helper_markers) == 1 and helper_markers[0][1] == HELPER_NEW_SHA,
                    'new board helper executed-source marker missing or changed')
            marker_position = helper_markers[0].start()
            for terminal in (r'PIPE_HINT_PASS', r'CORE(?:\[0\])? PASS', r'BSG PASS'):
                matches = list(re.finditer(terminal, text))
                require(matches and all(match.end() < marker_position for match in matches),
                        'board helper source marker is not after every required program terminal')
        reply = re.escape(admission['elf_sha256']) + r'  ' + re.escape(GUEST_ELF)
        require(len(re.findall(r'^' + reply + r'$', text, re.MULTILINE)) == 1,
                'actual guest ELF hash confirmation missing or duplicated')
        bound_logs.append(dict(image=row['image'], workload=row['workload'],
                               board_helper_sha256=row['board_helper_sha256'],
                               helper_identity_evidence=('legacy-no-per-run-marker' if row['board_helper_sha256'] == HELPER_OLD_SHA
                                                         else 'actual-post-terminal-self-sha256'),
                               transcript=row['transcript_record'], status=row['status_record'],
                               config=result['config'], identity=result['identity'],
                               memory_bound=_runtime_46_bound(row['path'])))
        arm = 'baseline' if row['image'] == 'A' else 'control'
        comparisons[row['workload']][arm].append(str(row['path']))
    images = verify_reviewed_images('embedded46')
    bindings = [admission_record, acquisition_record, *files.values()]
    bindings.extend([helper_protocol['review'], helper_protocol['installation']])
    bindings.extend(helper_protocol['evidence'][name] for name in
                    ('original', 'cleanup_sync', 'diff', 'operational_addendum', 'inspection', 'known_owned_cleanup'))
    for session in sessions:
        bindings.extend([session['manifest'], *session['host_sources'].values()])
    for row in bound_logs:
        bindings.extend([row['transcript'], row['status']])
    for record in bindings:
        require(sha(Path(record['path'])) == record['sha256'], 'input changed during audit: ' + record['path'])
    return dict(state='protocol-accepted; image contrasts not calculated',
                admission=admission_record, acquisition=acquisition_record,
                audit_source=artifact(Path(__file__)), frozen_host_sources=HOST_SOURCES,
                board_helper_protocol=helper_protocol,
                validator_sources={name: artifact(Path(__file__).with_name(name)) for name in
                                   ('analyze_scheduler_pipe_hint.py', 'compare_scheduler_pipe_hint_mode14.py',
                                    'run_scheduler_pipe_hint.py')},
                host=common_host, sessions=sessions, artifacts=list(files.values()),
                reviewed_images=images, logs=bound_logs, comparator_inputs=comparisons,
                limitations=['Scope v1 covers reported prefix-controller bits only, not all UCE/memory responses.',
                             'The low-level board helper changed explicitly after three admitted visits, only in post-program cleanup durability. Frozen host-eight and all timed guest code/parameters remain unchanged; the reviewed transition is hash-bound.',
                             'Mode-zero cleanup does not invalidate retained cache contents. Initial setup before each cell fence can inherit completed lines; this is the fixed repeated-crossover schedule, not an isolated cold-cell measurement.',
                             'Two boots per image/workload give limited between-boot evidence; admission is not a performance conclusion.',
                             'Hash-bound provenance records the declared chronology and frozen wrapper plan; it is not a hardware attestation.'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acquisition', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise SystemExit('refusing to replace audit output')
    try:
        result = audit(args.acquisition)
    except (ValueError, OSError, KeyError, TypeError) as error:
        raise SystemExit(str(error)) from error
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print('Protocol accepted: 16 complete independent logs; image contrasts not calculated.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
