#!/usr/bin/env python3
"""ROOT-only lossless terminal R9 capture; no tools, signals, cleanup or reservation release."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
from shared import *
api = archive_api()
JOB = '20261122T084853Z-1008854d3'
CAD = Path('/run/user/1001/zp-linux-borrow256-trace0-cad-20261122-01')
WORK = CAD / ('zynq-parrot-fpga-' + JOB)
VIVADO = WORK / 'cosim/black-parrot-example/vivado'
PREP = Path('/home/coyang/fpga-artifacts/context-resume/borrow256-fpga-preparation-20261122/preparation01')
LOGS = Path('/home/coyang/fpga-logs-linux-retained-borrow256-trace0')
RECOVERY = PREP / ('adapter02/run-' + JOB)
TERMINAL = RECOVERY / 'terminal-status.json'
TERMINAL_SHA = '963a094768dd01eef3e515530ab2c9ce127cbab024de4b549451974a9d0b7282'
CAD_ADMISSION = PREP / 'adapter02/admission01.json'
OUT = PREP / 'closed-terminal01'
CAP = 192 * 1024**2
FLOOR = 2560 * 1024**2
SECONDS = 600
DCP = [('synth', VIVADO / 'black_parrot_bd_proj.runs/synth_1/black_parrot_bd_1_wrapper.dcp'),
       ('optimized', VIVADO / 'black_parrot_bd_proj.runs/impl_1/black_parrot_bd_1_wrapper_opt.dcp'),
       ('impl-wrapper-not-routed', VIVADO / 'black_parrot_bd_proj.runs/impl_1/black_parrot_bd_1_wrapper.dcp')]
SUFFIX = {'.log', '.rpt', '.tcl', '.xdc', '.xci', '.xpr', '.xml', '.vds', '.jou', '.str', '.json', '.txt',
          '.v', '.sv', '.vh', '.svh', '.bd', '.prj', '.mem', '.mif', '.coe', '.hwh', '.map', '.ini', '.csv'}



def digest(stream):
    h, size = hashlib.sha256(), 0
    for block in iter(lambda: stream.read(1048576), b''):
        h.update(block); size += len(block)
    return dict(bytes=size, sha256=h.hexdigest())


def bind(path):
    p = Path(path)
    with p.open('rb') as f:
        r = digest(f)
    return dict(path=str(p.resolve()), **r)


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def evidence(exclude_output=False):
    rows = {}
    for root in (PREP, LOGS):
        for p in root.rglob('*'):
            if p.is_file() and not (exclude_output and OUT in p.parents):
                s = p.stat(); rows[str(p.resolve())] = (s.st_size, s.st_blocks * 512)
    return dict(logical=sum(x[0] for x in rows.values()), allocated=sum(x[1] for x in rows.values()), files=rows)


def closed_terminal():
    release = Path('/home/coyang/fpga-artifacts/context-resume/borrow256-terminal-release-20261122/release01.json')
    require(bind(release)['sha256'] == 'ce9f86268ac4e7ae3883e7923d58db86b27236739ab2d8ef2338aa1a180f130e', 'ROOT independent terminal/disappearance release')
    release_row = json.loads(release.read_text())
    require(release_row['current_CAD_job'] == JOB and release_row['terminal_verified'] is True and release_row['worker_absent'] is True and release_row['fresh_global_vendor_inventory'] == [], 'builder only released, storage still reserved')
    require(bind(TERMINAL)['sha256'] == TERMINAL_SHA, 'exact repaired terminal receipt')
    t = json.loads(TERMINAL.read_text())
    require(t['status'] == 'FAIL' and t['features'] == 'PASS actual seven defines/three contexts/20MHz-8MHz/source', 'terminal failure, not a route result')
    require(all(not t['ownership'][k] for k in ('owned_current', 'foreign_vendor_tools', 'unknown_worker_group', 'proven_orphans')), 'terminal worker/vendor ownership gone')
    require(not t['bound_violations'] and not t['identity_violations'] and not t['feedback_warnings'], 'terminal identities/bounds/no feedback warnings')
    require(Path(t['poll']).name == t['poll'], 'safe exact terminal poll basename')
    p = json.loads(gzip.decompress((RECOVERY / t['poll']).read_bytes()))
    expected = dict(BP_RETAINED_BUFFER=[1], BP_RETAINED_I_LINES=[256], BP_RETAINED_D_LINES=[256], BP_RETAINED_SETS=[256], BP_RETAINED_OBSERVE=[1], BP_AXI_RESPONSE_DELAY=[0], BP_CACHE_MISS_TRACE=[0])
    require(p['job'] == JOB and p['status'] == 'FAIL' and p['child_actual_features'] == expected, 'actual seven child defines')
    require(not p['identity_violations'] and not p['feedback_warnings'], 'no source identity or feedback-cut violation')
    require(p['source'] == dict(top='1008854d30e5d923c86c3232fc22af039467d552', bp='bb575a764c200f07c6f3259a179bdc861dd7593f'), 'actual borrowing-only source')
    require(p['source_archive_identity'] == dict(verified=4523, expected=4523), 'all declared worker source identities')
    require(all(r['selected'] == ['e_bp_unicore_zynqparrot_prefetch16k_cfg'] for r in p['selected_configuration']), 'actual STATIC16KiB configuration')
    require(any(r['final_BD'] for r in p['actual_clocks']) and all(r['result']['valid'] and r['result']['actual'] == dict(CLKOUT1_REQUESTED_OUT_FREQ=['2E+1'], CLKOUT2_REQUESTED_OUT_FREQ=['8']) for r in p['actual_clocks']), 'actual20MHz/8MHz clock IP')
    require(p['worker'] is None and not p['global_vendor_tools'], 'terminal no worker/vendor')
    require(not Path('/proc/1194135').exists(), 'exact worker1194135 absent; never signal it')
    require(not vendor_processes(), 'no vendor/known launcher now; no launch/query/signal')
    require((LOGS / JOB / 'status').read_text().strip() == 'FAIL', 'actual worker terminal status')
    require(not list(VIVADO.rglob('*.bit')), 'no bitstream accepted or present')
    return t, p


def inputs():
    a = json.loads(CAD_ADMISSION.read_text())
    require(a['configuration']['work_root'] == str(CAD) and a['resources']['evidence_cap_bytes'] == CAP and a['resources']['home_floor_bytes'] == FLOOR, 'original allocation, not a new budget')
    require(a['top'] == '1008854d30e5d923c86c3232fc22af039467d552' and a['bp'] == 'bb575a764c200f07c6f3259a179bdc861dd7593f', 'exact source admission')
    source, links = [], []
    require(len(a['configuration']['source_files']) == 4523, 'complete original worker source set')
    for rel, expected in a['configuration']['source_files'].items():
        require(not Path(rel).is_absolute() and '..' not in Path(rel).parts, 'declared source path')
        p = WORK / rel
        if expected['mode'] == '120000':
            require(p.is_symlink(), 'original Git symlink preserved')
            target = os.readlink(p); raw = os.fsencode(target)
            require(dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()) == {k: expected[k] for k in ('bytes', 'sha256')}, 'exact symlink definition')
            links.append(dict(path=str(p), target=target, git_binding=expected))
        else:
            r = bind(p); require({k: r[k] for k in ('bytes', 'sha256')} == {k: expected[k] for k in ('bytes', 'sha256')}, 'declared source bytes unchanged')
            source.append(r)
    generated = [p for p in VIVADO.rglob('*') if p.is_file() and (p.suffix.lower() in SUFFIX or '.log.' in p.name)]
    provenance = []
    for root in (PREP, LOGS, HERE):
        provenance += [p for p in root.rglob('*') if p.is_file() and OUT not in p.parents and '__pycache__' not in p.parts]
    for row in a['bindings'] + a['operational_bindings']:
        require(bind(row['path']) == row, 'source/launcher/probe/native admission input preserved')
        provenance.append(Path(row['path']))
    native = a['prerequisites']['fullcore']
    for name in ('binding', 'source_archive'):
        require(bind(native[name]['path']) == native[name], 'exact accepted native qualification/source archive')
        provenance.append(Path(native[name]['path']))
    native_record = json.loads(Path(native['binding']['path']).read_text())
    for row in native_record['closed_audits'].values():
        require(bind(row['path']) == row, 'native strict/full512/counters/17parameters/generated L2 proof')
        provenance.append(Path(row['path']))
    provenance.append(Path(a['source_preparation']['path']))
    provenance.append(API)
    provenance.append(Path('/home/coyang/fpga-artifacts/context-resume/borrow256-terminal-release-20261122/release01.json'))
    prior = Path('/run/user/1001/zp-linux-borrow1792-trace0-cad-20261122-01/zynq-parrot-fpga-20261122T062351Z-3daedee66/cosim/black-parrot-example/vivado/black_parrot_bd_proj.runs/synth_1/runme.log')
    provenance.append(prior)
    provenance += [POLICY, MARKER] + [Path(row['path']) for row in json.loads(MARKER.read_text()).values() if isinstance(row, dict) and 'path' in row]
    return dict(worker_sources=source, worker_symlinks=links,
                generated=[bind(p) for p in dict.fromkeys(generated)],
                provenance=[bind(p) for p in dict.fromkeys(provenance)],
                checkpoints=[dict(stage=stage, original=bind(p)) for stage, p in DCP])


def inference_excerpt():
    paths = [('R8', Path('/run/user/1001/zp-linux-borrow1792-trace0-cad-20261122-01/zynq-parrot-fpga-20261122T062351Z-3daedee66/cosim/black-parrot-example/vivado/black_parrot_bd_proj.runs/synth_1/runme.log')),
             ('R9', VIVADO / 'black_parrot_bd_proj.runs/synth_1/runme.log')]
    rows = {}
    for name, path in paths:
        lines = path.read_text().splitlines(keepends=True); wanted = set()
        for i, line in enumerate(lines):
            if re.search(r'retained|payload|tag_mem|epoch|bht|footprint|prefix|cache_miss_trace|RAMB|RAM64M|RAM32M', line, re.I):
                wanted.update(range(max(0, i - 3), min(len(lines), i + 4)))
        rows[name] = dict(source=bind(path), exact_lines=[dict(number=i + 1, text=lines[i]) for i in sorted(wanted)])
    return dict(logs=rows, scope='Exact source-bound lines plus complete archived logs. No vendor query or isolated causal inference; source capacity differs1792 vs256.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--admission-sha256', required=True); ap.add_argument('--execute', action='store_true')
    args = ap.parse_args(); admission = HERE / 'admission.json'
    require(args.execute and bind(admission)['sha256'] == args.admission_sha256, 'ROOT exact explicit archive admission')
    a = json.loads(admission.read_text())
    for row in a['inputs']:
        require(bind(row['path']) == row, 'frozen closure helper/prerequisite input')
    require(not OUT.exists(), 'fresh terminal closure; no overwrite or retry')
    start = time.monotonic()
    check_policy()
    before = evidence(); require(max(before['logical'], before['allocated']) <= CAP, 'original evidence union cap')
    stable_other = evidence(True)['files']
    work_bytes = allocated_tree(CAD)
    def cheap():
        used = allocated_tree(OUT)
        logical = sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()) if OUT.exists() else 0
        require(time.monotonic() - start < SECONDS, 'fixed600s capture bound')
        require(max(before['logical'] + logical, before['allocated'] + used) <= CAP, 'copies inside original192MiB evidence union')
        resources(work_bytes, before['allocated'] + used, check_shared=False)
    def boundary():
        require(evidence(True)['files'] == stable_other, 'closed original evidence unchanged')
        require(allocated_tree(CAD) == work_bytes, 'closed work allocated bytes unchanged')
        current = evidence(); require(max(current['logical'], current['allocated']) <= CAP, 'actual evidence union cap')
        resources(work_bytes, current['allocated'])
        cheap()
    base_work = resources(work_bytes, before['allocated'])
    terminal, poll = closed_terminal(); cheap(); OUT.mkdir()
    record = dict(state='RUNNING lossless terminal R9 failure capture', admission=bind(admission), script=bind(__file__),
                  terminal=bind(TERMINAL), original_evidence_cap=CAP, HOME_floor=FLOOR, deadline_seconds=SECONDS,
                  resource_before=base_work, evidence_before=before, archives=[], checkpoints=[],
                  no_reservation_release=True, no_vendor_or_signal_calls=True)
    write(OUT / 'manifest.json', record)
    saved = {s: signal.getsignal(s) for s in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    def stop(sig, frame):
        raise TimeoutError('own archival process stopped by signal ' + str(sig))
    for s in saved:
        signal.signal(s, stop)
    signal.alarm(max(1, int(SECONDS - (time.monotonic() - start))))
    try:
        groups = inputs(); record['inputs'] = groups
        write(OUT / 'worker-symlinks.json', groups['worker_symlinks'])
        record['symlink_definitions'] = bind(OUT / 'worker-symlinks.json')
        write(OUT / 'inference-excerpts.json', inference_excerpt())
        record['inference_excerpts'] = bind(OUT / 'inference-excerpts.json')
        write(OUT / 'manifest.json', record)
        for name in ('worker_sources', 'generated', 'provenance'):
            boundary(); record['archives'].append(api.archive_group(OUT / (name + '.tar.gz'), groups[name], cheap))
        for row in groups['checkpoints']:
            boundary(); dest = OUT / (row['stage'] + '.dcp'); original = row['original']
            with Path(original['path']).open('rb') as src, dest.open('xb') as dst:
                for block in iter(lambda: src.read(1048576), b''):
                    cheap(); dst.write(block)
            copied = bind(dest)
            require({k: copied[k] for k in ('bytes', 'sha256')} == {k: original[k] for k in ('bytes', 'sha256')}, 'complete raw DCP byte equality')
            record['checkpoints'].append(dict(stage=row['stage'], original=original, copy=copied, routed_or_accepted=False))
        require(inputs() == groups, 'all declared/generated/provenance/DCP source bytes unchanged after capture')
        closed_terminal(); boundary()
        require(not vendor_processes(), 'all vendor processes absent at final capture boundary')
        for row in a['inputs']:
            require(bind(row['path']) == row, 'frozen closure source endcheck')
        record.update(state='PASS CLOSED R9 detailed-placement failure; no route/bit/FPGA result',
                      elapsed_seconds=time.monotonic() - start, evidence_after=evidence(), vendor_processes_end=vendor_processes(),
                      ROOT_reported_metrics=dict(synth_LUT=53514, synth_FF=29798, synth_BRAM_tiles=93.5, synth_DSP=11, synth_elapsed='01:25:29',
                                                 placement_required_slices=11176, placement_available_slices=11010, slice_gap=166,
                                                 control_sets=1162, combined_LUT=56323, total_LUT=65455, placement_FF=29814, placement_elapsed='00:05:56'),
                      interpretation='Terminal placement failure only. Three distinct checkpoints retain exact stages; none is routed or accepted. No isolated causal area attribution.',
                      next='ROOT may freeze old CAD work/evidence future growth ONLY after independently verifying this complete capture. This helper never releases reservations or deletes data.')
    except BaseException as error:
        record.update(state='FAIL capture attempt preserved; no cleanup/extension/release', error=repr(error))
        raise
    finally:
        signal.alarm(0)
        for sig, handler in saved.items():
            signal.signal(sig, handler)
        write(OUT / 'manifest.json', record)
        try:
            cheap()
            final_evidence = evidence()
            require(max(final_evidence['logical'], final_evidence['allocated']) <= CAP, 'final actual evidence union cap including final manifest')
        except BaseException as error:
            record.update(state='FAIL final capture guard preserved; no release/cleanup', final_guard_error=repr(error))
            write(OUT / 'manifest.json', record)
            raise
        print(OUT / 'manifest.json', record['state'])


if __name__ == '__main__':
    main()
