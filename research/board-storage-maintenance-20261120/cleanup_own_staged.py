#!/usr/bin/env python3
"""Remove only hash-backed retired copies from this task's staged board files.

The common session reservation and the existing board program lock remain held
through inventory, host-prefix verification, removal and sync. No PL operation
or program run occurs, and the accepted/bounded images are not candidates.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import signal
from datetime import datetime, timezone

ROOT = Path('/home/coyang/zynq-parrot-linux-research')
ART = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120')
sys.path.insert(0, str(ROOT / 'linux-tests'))
from run_resume_workload_session import reservation, SESSION_LOCK

# Each complete copy has a durable immutable source. The only partial candidate
# is the exact temporary name reported by failed session16's scp invocation.
CANDIDATES = {
    'linux-prefix32-retention27-accepted-rootfs-shell.nbf':
        ('kernel27-accepted-rootfs/linux-prefix32-retention27-accepted-rootfs-shell.nbf',
         'c7c1e214796644b1dbe728cc274ca3d776c1cd24d4eb7ff570e109f44b53e3ff', False),
    'linux-prefix32-mode14-early-only-shell.nbf':
        ('mode14-early-only-control/linux-prefix32-mode14-early-only-shell.nbf',
         'd14dc8b00908bb7c7a310d4c517f31752a9db4f5836b5d60b5d916d596a7847b', False),
    'linux-prefix32-embedded-baseline-shell.nbf':
        ('embedded-workloads/linux-prefix32-embedded-baseline-shell.nbf',
         'e9aeba407073407cd01f91e2a687c21c4c8a6917b70886d997ce6852270b4508', False),
    '.linux-prefix32-embedded46-baseline-shell.nbf.incoming-568324':
        ('embedded46-workloads/linux-prefix32-embedded46-baseline-shell.nbf',
         '2e5ccc94a801fe724fd5b8787f5086fb6e939795c4ec98e49ef7a702ad9c024a', True),
}


def digest(path, limit=None):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        remaining = path.stat().st_size if limit is None else limit
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError('short durable backup')
            value.update(chunk)
            remaining -= len(chunk)
    return value.hexdigest()


REMOTE = r'''
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys
directory = Path.home() / 'zynq-parrot/cosim/black-parrot-example/zynq'
names = NAMES
def record(name):
    path = directory / name
    if not path.exists(): return {'name':name, 'exists':False}
    if path.is_symlink() or not path.is_file(): raise ValueError('not a regular candidate')
    info = path.stat()
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024), b''): h.update(block)
    return {'name':name, 'exists':True, 'bytes':info.st_size, 'sha256':h.hexdigest(),
            'inode':info.st_ino, 'links':info.st_nlink, 'uid':info.st_uid}
lock = Path.home() / 'bp-logs/.control-program.lock'
if subprocess.run(['pgrep','-x','control-program'], stdout=subprocess.DEVNULL).returncode == 0:
    raise RuntimeError('active control-program')
# The maintained board runners use a mkdir/owner-PID lock, not a flock file.
# Never reclaim another directory here, even if its owner appears stale.
lock.mkdir()
owner = lock / 'owner'
owner.write_text(str(os.getpid())+'\n')
try:
    if subprocess.run(['pgrep','-x','control-program'], stdout=subprocess.DEVNULL).returncode == 0:
        raise RuntimeError('active control-program')
    inventory = [record(name) for name in names]
    print(json.dumps({'inventory':inventory, 'remote_uid':os.getuid(), 'free_before':shutil.disk_usage(directory).free}), flush=True)
    approved = json.loads(sys.stdin.readline())
    if not isinstance(approved, list): raise ValueError('bad approval protocol')
    previous = {row['name']:row for row in inventory}
    # Recheck every selected inode and byte before any unlink.
    for row in approved:
        if row['name'] not in names or row != previous[row['name']] or record(row['name']) != row:
            raise ValueError('candidate changed before removal')
        if row['uid'] != os.getuid() or row['links'] != 1:
            raise ValueError('candidate ownership/link count changed')
    for row in approved: (directory / row['name']).unlink()
    os.sync()
    print(json.dumps({'removed':approved, 'free_after':shutil.disk_usage(directory).free}), flush=True)
finally:
    if owner.read_text().strip() != str(os.getpid()):
        raise RuntimeError('maintenance program-lock owner changed')
    owner.unlink()
    lock.rmdir()
'''


def main():
    output = ART / 'maintenance-own-staged-cleanup-v2'
    if output.exists():
        raise ValueError('maintenance evidence must be new')
    for relative, expected, _ in CANDIDATES.values():
        if digest(ART / relative) != expected:
            raise ValueError('durable complete backup identity mismatch')
    state = {'scope':'Only this task retired staged copies and exact failed session16 temporary upload.',
             'reservation':str(SESSION_LOCK), 'all_three_acknowledged':True,
             'board_program_lock':'~/bp-logs/.control-program.lock', 'state':'reserved',
             'board_program_lock_protocol':'maintained mkdir plus owner PID',
             'started_utc':datetime.now(timezone.utc).isoformat(),
             'source_sha256':digest(Path(__file__))}
    with reservation():
        output.mkdir()
        manifest = output / 'maintenance.json'
        def interrupted(signum, frame):
            raise KeyboardInterrupt('maintenance interrupted by signal '+str(signum))
        old_handlers = {sig:signal.signal(sig,interrupted) for sig in (signal.SIGTERM,signal.SIGHUP)}
        remote_script = REMOTE.replace('names = NAMES', 'names = '+repr(list(CANDIDATES)))
        # The remote program source goes in -c, leaving stdin for one JSON
        # decision. shlex.quote handles the static Python program as shell code.
        import shlex
        process = subprocess.Popen(['ssh','-o','BatchMode=yes','xilinx@192.168.4.35',
                                    'python3 -c '+shlex.quote(remote_script)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        try:
            first = process.stdout.readline()
            if not first:
                raise RuntimeError(process.stderr.read())
            state.update(json.loads(first))
            approved, skipped = [], []
            for row in state['inventory']:
                if not row['exists']:
                    continue
                relative, expected, partial = CANDIDATES[row['name']]
                local = ART / relative
                match = (row['links'] == 1 and row['uid'] == state['remote_uid']
                         and row['bytes'] <= local.stat().st_size
                         and (partial or row['bytes'] == local.stat().st_size)
                         and row['sha256'] == digest(local, row['bytes']))
                (approved if match else skipped).append(row)
            state.update(approved=approved, skipped=skipped)
            manifest.write_text(json.dumps(state,indent=2)+'\n')
            process.stdin.write(json.dumps(approved)+'\n'); process.stdin.flush(); process.stdin.close()
            result = process.stdout.readline()
            code = process.wait(timeout=180)
            error = process.stderr.read()
            if code or not result:
                raise RuntimeError('remote cleanup failed: '+error)
            state.update(json.loads(result), state='complete', remote_exit=code)
            print(json.dumps({'removed_files':len(state['removed']),
                              'free_before':state['free_before'], 'free_after':state['free_after'],
                              'skipped':len(skipped)},indent=2))
        except BaseException as error:
            state.update(state='failed', error=repr(error))
            if process.poll() is None:
                process.terminate(); process.wait(timeout=15)
            raise
        finally:
            state['released_utc']=datetime.now(timezone.utc).isoformat()
            manifest.write_text(json.dumps(state,indent=2)+'\n')
            for sig, handler in old_handlers.items():
                signal.signal(sig,handler)


if __name__ == '__main__':
    main()
