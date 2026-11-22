#!/usr/bin/env python3
"""ROOT-only independent R9 capture verification and immutable paired freeze."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys
import tarfile
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CAPTURE_HELPER = HERE.parent / 'retained-borrow256-r9-terminal-preparation-20261122'
sys.path.insert(0, str(CAPTURE_HELPER))
from shared import bind, require, allocated_tree, resources, vendor_processes, check_policy

ROOT = Path('/home/coyang/fpga-artifacts/context-resume')
WORK = Path('/run/user/1001/zp-linux-borrow256-trace0-cad-20261122-01')
EVIDENCE = [Path('/home/coyang/fpga-logs-linux-retained-borrow256-trace0'), ROOT / 'borrow256-fpga-preparation-20261122/preparation01']
CAPTURE = EVIDENCE[1] / 'closed-terminal01/manifest.json'
TERMINAL = EVIDENCE[1] / 'adapter02/run-20261122T084853Z-1008854d3/terminal-status.json'
RELEASE = ROOT / 'borrow256-terminal-release-20261122/release01.json'
OUT = ROOT / 'reservation-closures-20261122'
DEST = {name: OUT / ('r9-' + name + '.json') for name in ('work', 'evidence')}
DEST['complete'] = OUT / 'r9-freeze-complete.json'
DEST['verification'] = OUT / 'r9-independent-verification.json'
CAPS = dict(work=2684354560, evidence=201326592)
SECONDS = 600
RECEIPT_CAP = 8 * 1024**2

def inventory(roots, guard):
    rows = {}
    for root in roots:
        require(root.is_dir() and not root.is_symlink(), 'exact existing closed-family root')
        for path in sorted(root.rglob('*')):
            guard(); before = path.lstat()
            if stat.S_ISDIR(before.st_mode):
                continue
            if stat.S_ISLNK(before.st_mode):
                target = os.readlink(path); raw = os.fsencode(target)
                row = dict(path=str(path), kind='symlink', link_target=target, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            else:
                require(stat.S_ISREG(before.st_mode), 'unsupported nonregular closed-family entry: ' + str(path))
                row = dict(bind(path, guard), kind='regular')
            after = path.lstat()
            require((before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                    (after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'closed entry changed during read')
            row.update(allocated_bytes=after.st_blocks * 512, mode=stat.S_IMODE(after.st_mode))
            require(str(path) not in rows, 'overlapping family roots')
            rows[str(path)] = row
    return list(rows.values())

def verify_capture(capture, guard):
    require(capture['state'] == 'PASS CLOSED R9 detailed-placement failure; no route/bit/FPGA result' and capture['no_reservation_release'] is True, 'actual complete unreleased capture')
    require(capture['original_evidence_cap'] == CAPS['evidence'] and capture['HOME_floor'] == 2684354560, 'original unchanged evidence cap/floor')
    require(len(capture['archives']) == 3 and len(capture['checkpoints']) == 3, 'exact archive/checkpoint groups')
    counts = {}
    for group in ('worker_sources', 'generated', 'provenance'):
        row = next(r for r in capture['archives'] if Path(r['archive']['path']).name == group + '.tar.gz')
        require(bind(row['archive']['path'], guard) == row['archive'] and row['roundtrip'] is True, 'closed exact archive hash')
        require([r['original'] for r in row['members']] == capture['inputs'][group], 'exact source group; NO assumed internal manifest')
        with tarfile.open(row['archive']['path'], 'r|gz') as archive:
            count = 0
            for member in archive:
                guard(); require(count < len(row['members']), 'no extra archive members')
                expected = row['members'][count]
                require(member.isfile() and member.name == expected['member'], 'exact regular member/name/order')
                h = hashlib.sha256(); size = 0
                with archive.extractfile(member) as stream:
                    for block in iter(lambda: stream.read(1048576), b''):
                        guard(); h.update(block); size += len(block)
                require(dict(bytes=size, sha256=h.hexdigest()) == {k: expected['original'][k] for k in ('bytes', 'sha256')}, 'lossless independent member verification')
                require(bind(expected['original']['path'], guard) == expected['original'], 'every archived original source unchanged')
                count += 1
            require(count == len(row['members']), 'no missing members')
        counts[group + '.tar.gz'] = count
    require(counts['worker_sources.tar.gz'] == 4521 and len(capture['inputs']['worker_symlinks']) == 2, 'all4523 source definitions')
    require(bind(capture['symlink_definitions']['path'], guard) == capture['symlink_definitions'], 'exact symlink definition file')
    for row in capture['inputs']['worker_symlinks']:
        p = Path(row['path']); require(p.is_symlink() and os.readlink(p) == row['target'], 'both original Git symlink definitions')
        raw = os.fsencode(row['target'])
        require(dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()) == {k: row['git_binding'][k] for k in ('bytes', 'sha256')}, 'declared Git symlink bytes')
    require({r['stage'] for r in capture['checkpoints']} == {'synth', 'optimized', 'impl-wrapper-not-routed'}, 'three actual distinct stages, no route claim')
    for row in capture['checkpoints']:
        for name in ('original', 'copy'):
            require(bind(row[name]['path'], guard) == row[name], 'each actual DCP original/copy hash')
        require({k: row['copy'][k] for k in ('bytes', 'sha256')} == {k: row['original'][k] for k in ('bytes', 'sha256')} and row['routed_or_accepted'] is False, 'exact DCP equality; none routed/accepted')
    return counts

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admission-sha256', required=True)
    parser.add_argument('--capture-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(); admission = HERE / 'admission.json'
    require(args.execute and bind(admission)['sha256'] == args.admission_sha256, 'ROOT exact prospective freeze admission')
    plan = json.loads(admission.read_text())
    for row in plan['inputs']:
        require(bind(row['path']) == row, 'frozen gate/helper/prerequisite')
    require(all(not p.exists() for p in DEST.values()), 'fresh names; never overwrite or retry')
    require(bind(CAPTURE)['sha256'] == args.capture_sha256, 'ROOT reviewed actual capture SHA required')
    require(bind(TERMINAL)['sha256'] == '963a094768dd01eef3e515530ab2c9ce127cbab024de4b549451974a9d0b7282', 'exact terminal')
    require(bind(RELEASE)['sha256'] == 'ce9f86268ac4e7ae3883e7923d58db86b27236739ab2d8ef2338aa1a180f130e', 'ROOT independent builder release')
    capture = json.loads(CAPTURE.read_text()); terminal = json.loads(TERMINAL.read_text())
    require(terminal['status'] == 'FAIL' and all(not terminal['ownership'][k] for k in ('owned_current','foreign_vendor_tools','unknown_worker_group','proven_orphans')), 'original worker/vendor gone')
    require(not Path('/proc/1194135').exists() and not vendor_processes(), 'fresh no worker/vendor/known launcher; never signal anything')
    check_policy(); start = time.monotonic()
    w = allocated_tree(WORK); e = sum(allocated_tree(p) for p in EVIDENCE)
    def guard():
        files = [p for p in DEST.values() if p.exists()]
        charged = max(sum(p.stat().st_size for p in files), sum(p.stat().st_blocks * 512 for p in files))
        require(time.monotonic() - start < SECONDS and charged <= RECEIPT_CAP, 'fixed600s/8MiB receipt cap')
        resources(w, e, extra_home=max(0, RECEIPT_CAP - charged), check_shared=False)
    saved = {s: signal.getsignal(s) for s in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    def stop(sig, frame):
        raise TimeoutError('own freeze gate interrupted: ' + str(sig))
    for sig in saved:
        signal.signal(sig, stop)
    signal.alarm(SECONDS)
    try:
        guard(); counts = verify_capture(capture, guard)
        verification = dict(schema='r9-independent-capture-verification-v1', state='PASS independent exact archive members/source/DCP-copy verification', manifest=bind(CAPTURE), archive_members=counts, checkpoints=3, git_symlink_definitions=2, no_reservation_release=True)
        before = dict(work=inventory([WORK], guard), evidence=inventory(EVIDENCE, guard))
        require(allocated_tree(WORK) == w and sum(allocated_tree(p) for p in EVIDENCE) == e, 'no work/evidence growth during verification')
        pair = hashlib.sha256(json.dumps(dict(capture=bind(CAPTURE), verification=verification, inventories=before), sort_keys=True).encode()).hexdigest()
        outputs = {}
        for kind, files in before.items():
            logical = sum(r['bytes'] for r in files); allocated = sum(r['allocated_bytes'] for r in files); charged = max(logical, allocated)
            require(charged <= CAPS[kind], 'unchanged original family cap')
            outputs[kind] = dict(schema='r9-closed-family-v1', state='CLOSED immutable old R9 ' + kind + '; effective ONLY with complete marker', roots=list(map(str,[WORK] if kind == 'work' else EVIDENCE)), files=files,
                actual_closed_logical_bytes=logical, actual_closed_allocated_bytes=allocated, actual_closed_charged_bytes=charged, original_allocation_bytes=CAPS[kind], unused_allocation_released_bytes=CAPS[kind]-charged,
                future_growth_reserved_bytes=0, original_allocation_limit_unchanged=True, new_writes_to_closed_family_require_new_admission=True,
                freeze_pair_id=pair, requires_complete_marker=dict(path=str(DEST['complete']),freeze_pair_id=pair), terminal=bind(TERMINAL),durable_closure=bind(CAPTURE),independent_verification_path=str(DEST['verification']),no_cleanup=True)
        require(dict(work=inventory([WORK], guard),evidence=inventory(EVIDENCE, guard)) == before, 'all closed WORK/evidence bytes unchanged before seal')
        require(not vendor_processes() and not Path('/proc/1194135').exists(), 'final no vendor/worker; no signaling')
        check_policy()
        for row in plan['inputs']:
            require(bind(row['path']) == row, 'gate/helper source endcheck')
        with DEST['verification'].open('x') as f:
            json.dump(verification,f,indent=2);f.write('\n')
        for kind in ('work','evidence'):
            guard()
            with DEST[kind].open('x') as f:
                json.dump(outputs[kind],f,indent=2);f.write('\n')
        marker = dict(schema='r9-work-evidence-freeze-complete-v1', state='PASS ROOT old R9 WORK/evidence immutable freeze; unused future allocations released',freeze_pair_id=pair,
            work=bind(DEST['work']),evidence=bind(DEST['evidence']),terminal=bind(TERMINAL),durable_closure=bind(CAPTURE),independent_verification=bind(DEST['verification']),
            rule='Validate BOTH receipts, common pair and this complete marker. Half-pairs never release anything.',elapsed_seconds=time.monotonic()-start,no_vendor_board_signal_or_cleanup_calls=True,original_caps_unchanged=True)
        guard()
        encoded_marker = json.dumps(marker,indent=2) + '\n'
        require(sum(p.stat().st_blocks * 512 for p in DEST.values() if p.exists()) + len(encoded_marker.encode()) + 4096 <= RECEIPT_CAP, 'reserve final complete-marker allocation BEFORE publication')
        with DEST['complete'].open('x') as f:
            f.write(encoded_marker)
        # Publication is last: no later operation can invalidate a completed pair.
        print(json.dumps({k:bind(v) for k,v in DEST.items()},indent=2))
    finally:
        signal.alarm(0)
        for sig,handler in saved.items():
            signal.signal(sig,handler)

if __name__ == '__main__':
    main()
