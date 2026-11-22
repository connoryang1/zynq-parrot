#!/usr/bin/env python3
"""ROOT-only immutable R8 family receipts after exact independent archive verification."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import signal
import stat
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'retained-borrow256-trace0-preparation-20261122'))
import run_full as full

ROOT = Path('/home/coyang/fpga-artifacts/context-resume')
WORK = Path('/run/user/1001/zp-linux-borrow1792-trace0-cad-20261122-01')
EVIDENCE = [Path('/home/coyang/fpga-logs-linux-retained-borrow1792-trace0'), Path('/home/coyang/zynq-parrot-linux-host-observer/research/borrow-fpga-cad-preparation-20261122')]
CAPTURE = EVIDENCE[1] / 'closed-terminal01/manifest.json'
VERIFY = ROOT / 'retained-borrow1792-terminal-independent-20261122/verification02.json'
FAILURE = VERIFY.with_name('verifier-precondition-failure01.json')
TERMINAL = ROOT / 'retained-borrow1792-monitor-recovery-20261122/preparation01/observe01/terminal-status.json'
OUT = ROOT / 'reservation-closures-20261122'
DEST = dict(work=OUT / 'r8-work.json', evidence=OUT / 'r8-evidence.json', complete=OUT / 'r8-freeze-complete.json')
CAPS = dict(work=2560 * 1024**2, evidence=384 * 1024**2)
RECEIPT_CAP = 8 * 1024**2
SECONDS = 600
require = full.require


def bind(path, guard=lambda: None):
    p = Path(path); h, n = hashlib.sha256(), 0
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            guard(); h.update(block); n += len(block)
    return dict(path=str(p), bytes=n, sha256=h.hexdigest())


def vendor_absent():
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            require((p / 'comm').read_text().strip().lower() not in ('vivado', 'xelab', 'xsim', 'xvlog', 'rdi_program'), 'vendor process present; no signal/tool action permitted')
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass


def inventory(roots, guard):
    rows = {}
    for root in roots:
        require(root.is_dir() and not root.is_symlink(), 'exact old family root exists')
        for p in sorted(root.rglob('*')):
            guard(); before = p.lstat()
            if stat.S_ISDIR(before.st_mode):
                continue
            if stat.S_ISLNK(before.st_mode):
                raw = __import__('os').fsencode(__import__('os').readlink(p))
                row = dict(path=str(p), kind='symlink', link_target=__import__('os').readlink(p), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            else:
                require(stat.S_ISREG(before.st_mode), 'unsupported nonregular closed-family entry: ' + str(p))
                row = dict(bind(p, guard), kind='regular')
            after = p.lstat()
            require((before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'closed file changed during read')
            row.update(allocated_bytes=after.st_blocks * 512, mode=stat.S_IMODE(after.st_mode))
            require(str(p) not in rows, 'overlapping old family roots')
            rows[str(p)] = row
    return list(rows.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--admission-sha256', required=True); ap.add_argument('--execute', action='store_true')
    args = ap.parse_args(); admission = HERE / 'admission.json'
    require(args.execute and bind(admission)['sha256'] == args.admission_sha256, 'ROOT exact explicit freeze admission')
    plan = json.loads(admission.read_text())
    for r in plan['inputs']:
        require(bind(r['path']) == r, 'frozen gate/prerequisite bytes')
    require(all(not p.exists() for p in DEST.values()), 'fresh receipt names; never overwrite')
    require(bind(CAPTURE)['sha256'] == 'f2d11985ae3c5c05a9f0449d29d0ffdc896ed7c0dbf43d319c83f801d860079b', 'exact final R8 capture')
    require(bind(VERIFY)['sha256'] == '6a1dbfe203c4ef66e00e6a6ae73bdcb64c78d2cc806998cfc6aaea1f4a1cc7b0', 'ROOT actual independent verification')
    proof = json.loads(VERIFY.read_text()); capture = json.loads(CAPTURE.read_text()); terminal = json.loads(TERMINAL.read_text())
    expected = {'worker_sources.tar.gz': 4521, 'generated.tar.gz': 1148, 'provenance.tar.gz': 190}
    require(proof['state'] == 'PASS ROOT independent full archive member/source/DCP-copy verification' and proof['manifest']['sha256'] == bind(CAPTURE)['sha256'], 'complete ROOT verification binds capture')
    require(proof['archive_members'] == expected and proof['checkpoints'] == 3 and proof['git_symlink_definitions'] == 2 and proof['no_reservation_release'] is True, 'all member/source/DCP coverage verified BEFORE release')
    require(capture['state'] == 'PASS CLOSED R8 detailed-placement failure; no route/bit/FPGA result' and capture['no_reservation_release'] is True, 'unreleased terminal capture')
    for name, group in (('worker_sources', 'worker_sources'), ('generated', 'generated'), ('provenance', 'provenance')):
        row = next(r for r in capture['archives'] if Path(r['archive']['path']).name == name + '.tar.gz')
        require([m['original'] for m in row['members']] == capture['inputs'][group] and len(row['members']) == expected[name + '.tar.gz'], 'exact memberlist; NO invented internal manifest')
    require(len(capture['checkpoints']) == 3 and all({k: r['copy'][k] for k in ('bytes', 'sha256')} == {k: r['original'][k] for k in ('bytes', 'sha256')} for r in capture['checkpoints']), 'three distinct exact DCP copies')
    require(bind(TERMINAL)['sha256'] == 'b67c89c00caa5168819bdf5adfeb124116a2a37d4f92b2f3931ee9a4ce7b8c84' and terminal['status'] == 'FAIL' and all(not terminal['ownership'][k] for k in ('owned_current', 'foreign_vendor_tools', 'unknown_worker_group', 'proven_orphans')), 'original worker/vendor gone')
    vendor_absent()
    start = time.monotonic(); w = full.budget.check(); h = full.source.budget()
    home_need = h['required_free_bytes'] + full.budget.DURABLE_CAP - full.source.size(full.budget.DURABLE)
    def guard():
        used = sum(p.stat().st_size for p in DEST.values() if p.exists())
        require(time.monotonic() - start < SECONDS and used <= RECEIPT_CAP, 'fixed600s/8MiB receipt gate')
        require(shutil.disk_usage(OUT).free >= home_need + RECEIPT_CAP - used, 'all old native/CAD/HOME reservations remain charged until complete marker')
        require(shutil.disk_usage(WORK.parent).free >= w['required_free_bytes'], 'all old native/work future allocations remain charged until complete marker')
    saved = signal.getsignal(signal.SIGALRM)
    def alarm(sig, frame):
        raise TimeoutError('own receipt gate600s deadline')
    signal.signal(signal.SIGALRM, alarm); signal.alarm(SECONDS)
    try:
        guard(); before = dict(work=inventory([WORK], guard), evidence=inventory(EVIDENCE, guard))
        rows_by_path = {r['path']: r for rows in before.values() for r in rows}
        for r in capture['archives']:
            require({k: rows_by_path[r['archive']['path']][k] for k in ('bytes', 'sha256')} == {k: r['archive'][k] for k in ('bytes', 'sha256')}, 'verified archive still exact')
        for r in capture['checkpoints']:
            for name in ('original', 'copy'):
                row = r[name]; require({k: rows_by_path[row['path']][k] for k in ('bytes', 'sha256')} == {k: row[k] for k in ('bytes', 'sha256')}, 'every actual original/copy DCP still exact')
        pair = hashlib.sha256(json.dumps(dict(capture=bind(CAPTURE), verification=bind(VERIFY), inventories=before), sort_keys=True).encode()).hexdigest()
        outputs = {}
        for kind, files in before.items():
            logical = sum(r['bytes'] for r in files); allocated = sum(r['allocated_bytes'] for r in files); charged = max(logical, allocated)
            require(charged <= CAPS[kind], 'original family cap unchanged')
            outputs[kind] = dict(schema='r8-closed-family-v1', state='CLOSED immutable old R8 ' + kind + '; effective ONLY with complete marker', roots=list(map(str, [WORK] if kind == 'work' else EVIDENCE)), files=files,
                                 actual_closed_logical_bytes=logical, actual_closed_allocated_bytes=allocated, actual_closed_charged_bytes=charged,
                                 original_allocation_bytes=CAPS[kind], unused_allocation_released_bytes=CAPS[kind] - charged,
                                 future_growth_reserved_bytes=0, original_allocation_limit_unchanged=True, new_writes_to_closed_family_require_new_admission=True,
                                 freeze_pair_id=pair, requires_complete_marker=dict(path=str(DEST['complete']), freeze_pair_id=pair),
                                 terminal=bind(TERMINAL), durable_closure=bind(CAPTURE), independent_verification=bind(VERIFY), prior_verifier_precondition_failure=bind(FAILURE), no_cleanup=True)
        require(dict(work=inventory([WORK], guard), evidence=inventory(EVIDENCE, guard)) == before, 'ALL closed source/work/evidence bytes unchanged before sealing')
        vendor_absent()
        for r in plan['inputs']:
            require(bind(r['path']) == r, 'frozen gate/source endcheck')
        for kind in ('work', 'evidence'):
            with DEST[kind].open('x') as f:
                json.dump(outputs[kind], f, indent=2); f.write('\n')
            guard()
        marker = dict(schema='r8-work-evidence-freeze-complete-v1', state='PASS ROOT old R8 WORK/evidence immutable freeze; unused future allocations released', freeze_pair_id=pair,
                      work=bind(DEST['work']), evidence=bind(DEST['evidence']), terminal=bind(TERMINAL), durable_closure=bind(CAPTURE), independent_verification=bind(VERIFY),
                      rule='Consumers MUST validate BOTH receipts against this marker and common freeze_pair_id. Half-pairs never release anything.', elapsed_seconds=time.monotonic() - start,
                      no_vendor_board_signal_or_cleanup_calls=True, original_caps_unchanged=True)
        guard()
        with DEST['complete'].open('x') as f:
            json.dump(marker, f, indent=2); f.write('\n')
        # No work/evidence writes occur; only these new external receipts are created.
        print(json.dumps(dict(state=marker['state'], complete=bind(DEST['complete']), work=bind(DEST['work']), evidence=bind(DEST['evidence'])), indent=2))
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, saved)


if __name__ == '__main__':
    main()
