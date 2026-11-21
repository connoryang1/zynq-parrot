#!/usr/bin/env python3
"""Run a short natural-demand matrix under the shared physical-board reservation."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess

from run_scheduler_pipe_hint import parse_args as guest_args, run, validate_args

SESSION_LOCK = Path('/home/coyang/fpga-artifacts/pynq-session.lock')
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'codex-skills/bp-fpga-synthesis/scripts'
HOST_SOURCES = (
    'linux-tests/run_resume_workload_session.py',
    'linux-tests/run_scheduler_pipe_hint.py',
    'linux-tests/run_scheduler_tagged_replay.py',
    *(f'codex-skills/bp-fpga-synthesis/scripts/{name}.sh' for name in (
        'stage_pynq_artifacts', 'power_cycle_pynq', 'wait_pynq_ready',
        'load_pynq_overlay', 'run_pynq_interactive')),
)


def snapshot_sources(output):
    records = {}
    for relative in HOST_SOURCES:
        data = (ROOT / relative).read_bytes()
        target = output / 'host-sources' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        records[relative] = hashlib.sha256(data).hexdigest()
    return records


def verify_sources(records):
    for relative, expected in records.items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise RuntimeError('host source changed during physical session: ' + relative)


@contextmanager
def reservation():
    # Open the agreed inode only. O_CREAT, truncation, unlink and replacement
    # are forbidden: another process may still hold a lock on the original.
    with SESSION_LOCK.open('r') as descriptor:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)


def recover(host, env):
    for helper in ('power_cycle_pynq.sh', 'wait_pynq_ready.sh', 'load_pynq_overlay.sh'):
        subprocess.run([str(SCRIPTS / helper), host], env=env, check=True)


def cell(text):
    match = re.fullmatch(r'(scan|lookup|parse|chase|deflate):(\d+):(futex-early|futex-early-both|preseed|retention-rr|retention-first)', text)
    if not match or int(match[2]) > 65536:
        raise argparse.ArgumentTypeError('cell must be workload:kib:policy (early, both, preseed, or retention)')
    return match[1], int(match[2]), match[3]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('nbf', type=Path)
    parser.add_argument('transfer', type=Path)
    parser.add_argument('elf_sha256')
    parser.add_argument('package', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--bitstream-sha256', required=True)
    parser.add_argument('--zlib-library', type=Path)
    parser.add_argument("--embedded-zlib-library", action="store_true",
                        help="copy fixed embedded library; requires exact --zlib-library")
    parser.add_argument("--host", default="xilinx@192.168.4.35")
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument('--cell', action='append', type=cell)
    operation.add_argument('--retention-probe', choices=('absent', 'present'))
    parser.add_argument('--loops', type=int, default=64)
    parser.add_argument('--warmup', type=int, default=32)
    parser.add_argument('--repeats', type=int, default=4)
    parser.add_argument('--all-three-acknowledged', action='store_true', required=True)
    args = parser.parse_args(argv)
    if args.embedded_zlib_library and args.zlib_library is None:
        parser.error("--embedded-zlib-library requires exact --zlib-library")
    if not args.package.is_file():
        parser.error('verified package must exist')
    if args.output.exists():
        parser.error('session output must be new; existing evidence is never overwritten')
    # Validate every guest command/transfer before reserving or touching a board.
    plan = []
    for index, (workload, kib, policy) in enumerate(args.cell or []):
        parsed = guest_args([
            str(args.nbf), str(args.transfer), args.elf_sha256,
            str(args.output / f'{index}-{workload}{kib}-{policy}.log'),
            '--bitstream-sha256', args.bitstream_sha256, '--host', args.host,
            '--workload', workload, '--working-set-kib', str(kib),
            '--sync', 'futex', '--policy', policy, '--loops', str(args.loops),
            '--warmup', str(args.warmup), '--repeats', str(args.repeats)])
        plan.append(parsed)
        parsed.zlib_library = args.zlib_library
        parsed.embedded_zlib_library = args.embedded_zlib_library
    if args.retention_probe:
        plan.append(guest_args([
            str(args.nbf), str(args.transfer), args.elf_sha256,
            str(args.output / f'0-retention-probe-{args.retention_probe}.log'),
            '--bitstream-sha256', args.bitstream_sha256, '--host', args.host,
            '--retention-probe', args.retention_probe]))
        if args.zlib_library is not None:
            parser.error('retention probe uses no optional zlib library')
    env = os.environ.copy()
    if not env.get('PYNQ_POWER_STATE_URL'):
        # Existing local fallback, never echo or retain the credential.
        match = re.search(r'https?://[^\s\x27\x22]+', Path('/home/coyang/power_cycle.sh').read_text())
        if not match:
            parser.error('no power controller configured')
        env['PYNQ_POWER_STATE_URL'] = match[0]
    env['PYNQ_POWER_OFF_SECONDS'] = '15'
    # A failed lock acquisition has no board side effect or output directory.
    with reservation():
        args.output.mkdir(parents=True)
        for parsed in plan:
            validate_args(parsed)
        status = {'reservation': str(SESSION_LOCK), 'host': args.host,
                  'all_three_acknowledged': True, 'state': 'reserved',
                  'started_utc': datetime.now(timezone.utc).isoformat(),
                  'host_source_sha256': snapshot_sources(args.output),
                  'plan': [vars(parsed) for parsed in plan]}
        status_path = args.output / 'session.json'
        def save():
            status_path.write_text(json.dumps(status, default=str, indent=2) + '\n')
        save()
        def interrupted(signum, frame):
            raise KeyboardInterrupt(f'session interrupted by signal {signum}')
        old_handlers = {sig: signal.signal(sig, interrupted)
                        for sig in (signal.SIGTERM, signal.SIGHUP)}
        try:
            subprocess.run([str(SCRIPTS / 'stage_pynq_artifacts.sh'), str(args.package),
                            args.host, str(args.nbf)], env=env, check=True)
            for parsed in plan:
                recover(args.host, env)
                run(parsed)  # Still uses the hash-bound serialized board runner.
            verify_sources(status['host_source_sha256'])
            status['state'] = 'complete'
        except BaseException as error:
            status.update(state='failed', error=repr(error))
            save()
            try:
                recover(args.host, env)
                status['recovery'] = 'complete before reservation release'
            except BaseException as recovery_error:
                status['recovery'] = repr(recovery_error)
            raise
        finally:
            status['released_utc'] = datetime.now(timezone.utc).isoformat()
            try:
                save()
            finally:
                for sig, handler in old_handlers.items():
                    signal.signal(sig, handler)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
