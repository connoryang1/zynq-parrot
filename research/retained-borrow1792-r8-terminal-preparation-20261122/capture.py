#!/usr/bin/env python3
"""ROOT-only lossless terminal R8 capture; no tools, signals, cleanup or reservation release."""
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
PRODUCER = HERE.parent / 'retained-borrow256-trace0-preparation-20261122'
sys.path.insert(0, str(PRODUCER))
import run_full as full

API = Path('/home/coyang/zynq-parrot-linux-host-observer/research/retained256-qualification-20261122/close256.py')
spec = importlib.util.spec_from_file_location('qualified_R8_archive_api', API)
api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
JOB = '20261122T062351Z-3daedee66'
CAD = Path('/run/user/1001/zp-linux-borrow1792-trace0-cad-20261122-01')
WORK = CAD / ('zynq-parrot-fpga-' + JOB)
VIVADO = WORK / 'cosim/black-parrot-example/vivado'
PREP = Path('/home/coyang/zynq-parrot-linux-host-observer/research/borrow-fpga-cad-preparation-20261122')
LOGS = Path('/home/coyang/fpga-logs-linux-retained-borrow1792-trace0')
RECOVERY = Path('/home/coyang/fpga-artifacts/context-resume/retained-borrow1792-monitor-recovery-20261122')
TERMINAL = RECOVERY / 'preparation01/observe01/terminal-status.json'
TERMINAL_SHA = 'b67c89c00caa5168819bdf5adfeb124116a2a37d4f92b2f3931ee9a4ce7b8c84'
CAD_ADMISSION = Path('/home/coyang/fpga-artifacts/context-resume/native1792-borrow-trace0-cad-20261122/admission02.json')
OUT = PREP / 'closed-terminal01'
CAP = 384 * 1024**2
FLOOR = 2560 * 1024**2
SECONDS = 600
DCP = [('synth', VIVADO / 'black_parrot_bd_proj.runs/synth_1/black_parrot_bd_1_wrapper.dcp'),
       ('optimized', VIVADO / 'black_parrot_bd_proj.runs/impl_1/black_parrot_bd_1_wrapper_opt.dcp'),
       ('impl-wrapper-not-routed', VIVADO / 'black_parrot_bd_proj.runs/impl_1/black_parrot_bd_1_wrapper.dcp')]
SUFFIX = {'.log', '.rpt', '.tcl', '.xdc', '.xci', '.xpr', '.xml', '.vds', '.jou', '.str', '.json', '.txt',
          '.v', '.sv', '.vh', '.svh', '.bd', '.prj', '.mem', '.mif', '.coe', '.hwh', '.map', '.ini', '.csv'}
require = full.require


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


def vendor_processes():
    rows = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            name = (p / 'comm').read_text().strip()
            if name.lower() in ('vivado', 'xelab', 'xsim', 'xvlog', 'rdi_program'):
                rows.append(dict(pid=int(p.name), comm=name))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    return rows


def closed_terminal():
    require(bind(TERMINAL)['sha256'] == TERMINAL_SHA, 'exact repaired terminal receipt')
    t = json.loads(TERMINAL.read_text())
    require(t['status'] == 'FAIL' and t['state'] == 'PASS read-only exact ownership/limits', 'terminal failure, not a route result')
    require(not t['violations'] and all(not t['ownership'][k] for k in ('owned_current', 'foreign_vendor_tools', 'unknown_worker_group', 'proven_orphans')), 'terminal worker/vendor ownership gone')
    require(t['signals_sent'] == t['vendor_or_launcher_calls'] == 0, 'read-only monitor provenance')
    require(bind(t['poll']['path']) == t['poll'], 'exact terminal poll')
    p = json.loads(gzip.decompress(Path(t['poll']['path']).read_bytes()))
    expected = dict(BP_RETAINED_BUFFER=[1], BP_RETAINED_I_LINES=[1792], BP_RETAINED_D_LINES=[1792], BP_RETAINED_SETS=[256], BP_RETAINED_OBSERVE=[1], BP_AXI_RESPONSE_DELAY=[0], BP_CACHE_MISS_TRACE=[0])
    require(p['job'] == JOB and p['status'] == 'FAIL' and p['child_actual_features'] == expected, 'actual seven child defines')
    require(not p['identity_violations'] and not p['feedback_warnings'], 'no source identity or feedback-cut violation')
    require(p['source'] == dict(top='3daedee66a3c94014b4a666fea037b17cc9b0943', bp='bb575a764c200f07c6f3259a179bdc861dd7593f'), 'actual borrowing-only source')
    require(p['source_archive_identity'] == dict(verified=4523, expected=4523), 'all declared worker source identities')
    require(all(r['selected'] == ['e_bp_unicore_zynqparrot_prefetch16k_cfg'] for r in p['selected_configuration']), 'actual STATIC16KiB configuration')
    require(any(r['final_BD'] for r in p['actual_clocks']) and all(r['result']['valid'] and r['result']['actual'] == dict(CLKOUT1_REQUESTED_OUT_FREQ=['2E+1'], CLKOUT2_REQUESTED_OUT_FREQ=['8']) for r in p['actual_clocks']), 'actual20MHz/8MHz clock IP')
    require(not vendor_processes(), 'no vendor process now; never launch/query/signal one')
    require((LOGS / JOB / 'status').read_text().strip() == 'FAIL', 'actual worker terminal status')
    require(not list(VIVADO.rglob('*.bit')), 'no bitstream accepted or present')
    return t, p


def inputs():
    a = json.loads(CAD_ADMISSION.read_text())
    require(a['configuration']['work_root'] == str(CAD) and a['resources']['evidence_cap_bytes'] == CAP and a['resources']['home_floor_bytes'] == FLOOR, 'original allocation, not a new budget')
    require(a['top'] == '3daedee66a3c94014b4a666fea037b17cc9b0943' and a['bp'] == 'bb575a764c200f07c6f3259a179bdc861dd7593f', 'exact source admission')
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
    for root in (PREP, LOGS, RECOVERY, CAD_ADMISSION.parent, HERE):
        provenance += [p for p in root.rglob('*') if p.is_file() and OUT not in p.parents and '__pycache__' not in p.parts]
    for row in a['bindings'] + a['operational_bindings']:
        require(bind(row['path']) == row, 'source/launcher/probe/native admission input preserved')
        provenance.append(Path(row['path']))
    native = a['prerequisites']['fullcore']
    for name in ('binding', 'receipt', 'source_archive'):
        require(bind(native[name]['path']) == native[name], 'exact accepted native qualification/source archive')
        provenance.append(Path(native[name]['path']))
    provenance.append(Path(a['source_preparation']['path']))
    provenance.append(API)
    # Keep the old raw inference table for a stage-qualified mapping comparison.
    prior = Path('/run/user/1001/zp-linux-canonical-r7-20261121/zynq-parrot-fpga-20261122T003339Z-eb7d39013/cosim/black-parrot-example/vivado/black_parrot_bd_proj.runs/synth_1/runme.log')
    provenance.append(prior)
    return dict(worker_sources=source, worker_symlinks=links,
                generated=[bind(p) for p in dict.fromkeys(generated)],
                provenance=[bind(p) for p in dict.fromkeys(provenance)],
                checkpoints=[dict(stage=stage, original=bind(p)) for stage, p in DCP])


def inference_excerpt():
    root = Path('/run/user/1001/zp-linux-canonical-r7-20261121/zynq-parrot-fpga-20261122T003339Z-eb7d39013/cosim/black-parrot-example/vivado')
    rows = {}
    for name, path in [('R7', root / 'black_parrot_bd_proj.runs/synth_1/runme.log'),
                       ('R8', VIVADO / 'black_parrot_bd_proj.runs/synth_1/runme.log')]:
        lines = path.read_text().splitlines(keepends=True); wanted = set()
        for i, line in enumerate(lines):
            if re.search(r'retained|payload|tag_mem|epoch|bht|footprint|prefix|cache_miss_trace|RAMB|RAM64M', line, re.I):
                wanted.update(range(max(0, i - 3), min(len(lines), i + 4)))
        rows[name] = dict(source=bind(path), exact_lines=[dict(number=i + 1, text=lines[i]) for i in sorted(wanted)])
    return dict(logs=rows, scope='Exact source-bound raw-line excerpts; complete original logs are also archived. No DCP query or isolated causal inference.',
                ROOT_observed_accounting='Local retained payload25RAMB36+2RAMB18 and2tagRAMB36 per lane totals56tiles. R7 two cache-miss-trace RAMB36 are absent with trace0; four other shallow memories map from LUTRAM to fourRAMB18 in R8, consuming two tiles. Whole-device total remains140; this is mapping accounting, not exclusive causal attribution or spare-capacity proof.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--admission-sha256', required=True); ap.add_argument('--execute', action='store_true')
    args = ap.parse_args(); admission = HERE / 'admission.json'
    require(args.execute and bind(admission)['sha256'] == args.admission_sha256, 'ROOT exact explicit archive admission')
    a = json.loads(admission.read_text())
    for row in a['inputs']:
        require(bind(row['path']) == row, 'frozen closure helper/prerequisite input')
    require(not OUT.exists(), 'fresh terminal closure; no overwrite or retry')
    start = time.monotonic(); base_work = full.budget.check(); home = full.source.budget()
    require(full.source.FLOOR == FLOOR and full.budget.OWN_CAP == 768 * 1024**2, 'same original native pool/floor')
    before = evidence(); require(max(before['logical'], before['allocated']) <= CAP, 'original evidence union cap')
    stable_other = evidence(True)['files']; work_need = base_work['required_free_bytes']
    home_need = home['required_free_bytes'] + full.budget.DURABLE_CAP - full.source.size(full.budget.DURABLE)
    phase_out = 0
    def cheap():
        used = full.source.size(OUT)
        require(time.monotonic() - start < SECONDS, 'fixed600s capture bound')
        require(max(before['logical'], before['allocated']) + used <= CAP, 'copies INSIDE original384MiB union')
        require(shutil.disk_usage(HERE).free >= home_need - (used - phase_out), 'same2.5GiB floor plus all remaining evidence/source/native durable reservations')
        require(shutil.disk_usage(CAD.parent).free >= work_need, 'native768MiB/oldwork/CAD reserves remain charged; no premature release')
    def boundary():
        nonlocal work_need, home_need, phase_out
        require(evidence(True)['files'] == stable_other, 'closed original evidence remains unchanged')
        now = full.budget.check(); now_home = full.source.budget()
        work_need = now['required_free_bytes']; phase_out = full.source.size(OUT)
        home_need = now_home['required_free_bytes'] + full.budget.DURABLE_CAP - full.source.size(full.budget.DURABLE)
        current = evidence(); require(max(current['logical'], current['allocated']) <= CAP, 'actual logical/allocated evidence union remains bounded')
        cheap()
    terminal, poll = closed_terminal(); cheap(); OUT.mkdir()
    record = dict(state='RUNNING lossless terminal R8 failure capture', admission=bind(admission), script=bind(__file__),
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
        record.update(state='PASS CLOSED R8 detailed-placement failure; no route/bit/FPGA result',
                      elapsed_seconds=time.monotonic() - start, evidence_after=evidence(), vendor_processes_end=vendor_processes(),
                      ROOT_reported_metrics=dict(synth_LUT=54001, synth_FF=29859, synth_BRAM_tiles=140, synth_DSP=11, synth_elapsed='01:26:11',
                                                 placement_required_slices=11211, placement_available_slices=10988, slice_gap=223,
                                                 control_sets=1169, combined_LUT=56452, total_LUT=65987, placement_FF=29863),
                      interpretation='Terminal placement failure only. Three distinct checkpoints retain exact stages; none is routed or accepted. Retained56tile local mapping is not whole-device spare capacity. No isolated causal area attribution.',
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
