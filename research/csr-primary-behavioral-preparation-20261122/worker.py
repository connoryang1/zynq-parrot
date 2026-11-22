#!/usr/bin/env python3
"""Default offline; ROOT-only bounded behavioral RAM-DUT primary miter."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import socket
import sys
import time
import uuid
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PLAN = HERE / 'plan.json'
FINAL = HERE / 'admission.FINAL.json'
RUN = Path('/run/user/1001/zp-csr-primary-behavioral-20261122-01')
CLAIM = 'ONE behavioral RAM real-CSR primary interface negative plus positive; no synthesis'
V = Path('/tools/Xilinx/Vivado/2024.2')
HELPERS = Path('/home/coyang/fpga-artifacts/context-resume/csr-snapshot-mapped-functional-20261122/runtime-full05')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def bind(path):
    path = Path(path)
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def verify(row):
    require(bind(row['path']) == row, 'source/input drift: ' + row['path'])


def load_module(name, row):
    verify(row)
    spec = importlib.util.spec_from_file_location(name, row['path'])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    require(Path(module.__file__).resolve() == Path(row['path']).resolve(), 'actual helper import')
    return module


def load(expected=None, execute=False):
    plan = json.loads(PLAN.read_text())
    require(plan['schema'] == 'csr-primary-behavioral-plan-v1', 'fixed behavioral schema')
    require(plan['stage'] == str(RUN) and plan['linux_claim'] == CLAIM, 'fixed case/stage')
    for row in plan['inputs']:
        verify(row)
    require(bind(Path(__file__).resolve()) in plan['inputs'], 'actual worker pin')
    # No arbitrary module/file selection through FINAL or command line.
    require(plan['qualified_worker']['path'] == str(HELPERS/'qualified_worker.py'), 'fixed qualified API')
    require(plan['owned_worker']['path'] == str(HELPERS/'software_owned_v2.py'), 'fixed owned API')
    require(plan['DUT']['kind'] == 'behavioral_RAM_only', 'not a mapped/FF admission')
    if not execute:
        return plan, None
    require(expected and bind(FINAL)['sha256'] == expected, 'exact ROOT FINAL SHA required')
    final = json.loads(FINAL.read_text())
    require(final['schema'] == 'csr-primary-behavioral-admission-v1' and final['launchable'] is True,
            'DRAFT cannot execute')
    require(final['source_plan'] == bind(PLAN) and final['limits'] == plan['limits'], 'exact plan/limits')
    require(final['linux_claim'] == CLAIM, 'actual behavioral scope')
    verify(final['ROOT_release'])
    release = json.loads(Path(final['ROOT_release']['path']).read_text())
    require(release.get('allow_csr_primary_behavioral_RAM') is True
            and release.get('source_plan') == bind(PLAN)
            and release.get('linux_claim') == CLAIM, 'explicit ROOT release')
    other = final['fixed_OTHER_reservations']
    require(set(other) == {'RUN_bytes', 'HOME_bytes'}
            and all(type(v) is int and v >= 0 for v in other.values()), 'priced fixed OTHER')
    require(release.get('fixed_OTHER_reservations') == other, 'release prices OTHER')
    require(socket.gethostname() == plan['target_hostname'], 'actual tool host')
    return plan, final


def usage(path):
    return sum(x.stat().st_size for x in path.rglob('*') if x.is_file()) if path.exists() else 0


def budget(plan, final):
    limits = plan['limits']
    run, home = usage(RUN), usage(HERE)
    require(run <= limits['RUN_bytes'] and home <= limits['HOME_family_bytes'], 'whole resource caps')
    other = final['fixed_OTHER_reservations']
    require(shutil.disk_usage(RUN.parent).free >= limits['RUN_floor_bytes']
            + limits['RUN_bytes']-run+other['RUN_bytes'], 'RUN remaining/floor/OTHER')
    require(shutil.disk_usage(HERE).free >= limits['HOME_floor_bytes']
            + limits['HOME_family_bytes']-home+other['HOME_bytes'], 'HOME remaining/floor/OTHER')
    available = next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()
                     if line.startswith('MemAvailable:'))
    require(available >= limits['MemAvailable_floor_bytes'], 'host memory floor')
    return dict(RUN_bytes=run, HOME_bytes=home, MemAvailable_bytes=available)


def prepare_inputs(plan):
    folder = RUN/'inputs'
    folder.mkdir()
    copies = []
    for row in plan['compile_sources']:
        verify(row)
        dest = folder/Path(row['path']).name
        require(not dest.exists(), 'unique fixed source basename')
        original = Path(row['path']).read_bytes()
        prefix = b'' if re.search(rb'(?m)^\s*`timescale\b', original) else b'`timescale 1ps/1ps\n'
        dest.write_bytes(prefix+original)
        require(dest.read_bytes()[len(prefix):] == original, 'timescale-only copy')
        copies.append(dict(source=row, copy=bind(dest), prefix=prefix.decode()))
    return copies


def verify_copies(rows):
    for row in rows:
        verify(row['copy'])


def commands(plan):
    build = RUN/'build'
    snapshot = 'csr_primary_behavioral'
    rtl = [V/'bin/xvlog', '--sv']
    for path in plan['include_dirs']:
        rtl += ['-i', path]
    for define in plan['defines']:
        rtl += ['-d', define]
    rtl += [RUN/'inputs'/Path(row['path']).name for row in plan['compile_sources']]
    return [
        ('xvlog-global', 60, build, [V/'bin/xvlog', V/'data/verilog/src/glbl.v']),
        ('xvlog-RTL', 90, build, rtl),
        ('xelab', 180, build, [V/'bin/xelab', '-L', 'unisims_ver', '-L', 'unimacro_ver',
                             '-L', 'secureip', 'work.csr_primary_miter', 'work.glbl', '-s', snapshot]),
        ('negative', 45, RUN/'negative', [V/'bin/xsim', snapshot, '-testplusarg', 'NEGATIVE=1',
                                        '-tclbatch', HERE/'run.tcl']),
        ('positive', 180, RUN/'positive', [V/'bin/xsim', snapshot, '-tclbatch', HERE/'run.tcl'])]


def check_log(text, negative):
    lines = [line.rstrip('\r') for line in text.splitlines()]
    require(not any(re.match(r'^(?:Fatal:|FATAL_ERROR|ERROR:|Error:)', line) for line in lines),
            'native/HDL fatal or error')
    require(not any('CSR_PRIMARY_MISMATCH' in line for line in lines), 'DUT mismatch')
    positives = [line for line in lines if re.fullmatch(
        r'CSR_PRIMARY_EQUIVALENCE_PASS checks=\d+ cycles=\d+ reads=\d+ saves=\d+ reloads=\d+', line)]
    negatives = [line for line in lines if re.fullmatch(
        r'CSR_PRIMARY_NEGATIVE_DETECTED interface=mepc bit=2 cycles=\d+ checks=\d+', line)]
    require((len(negatives) == 1 and not positives) if negative
            else (len(positives) == 1 and not negatives), 'one exact anchored expected terminal')
    return dict(marker=(negatives if negative else positives)[0])


def physical_snapshot(build, destination):
    source = build/'xsim.dir'
    require(source.is_dir() and not source.is_symlink(), 'actual compiled physical snapshot')
    rows = []
    for path in sorted(source.rglob('*')):
        require(not path.is_symlink(), 'unknown compiled symlink; do not follow')
        if path.is_file():
            rows.append(dict(relative=str(path.relative_to(source)), binding=bind(path)))
    require(rows, 'nonempty compiled snapshot')
    shutil.copytree(source, destination/'xsim.dir')
    for row in rows:
        copied = bind(destination/'xsim.dir'/row['relative'])
        require((copied['bytes'], copied['sha256']) ==
                (row['binding']['bytes'], row['binding']['sha256']), 'copied compiled bytes')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--admission-sha256')
    args = parser.parse_args()
    plan, final = load(args.admission_sha256, args.execute)
    if not args.execute:
        print(json.dumps(dict(state='DRAFT source-only; no inventory or tools', source_plan=bind(PLAN),
                              commands=[dict(label=n, seconds=t, cwd=str(c), argv=list(map(str,a)))
                                        for n,t,c,a in commands(plan)]), indent=2))
        return
    owned = load_module('software_owned_v2', plan['owned_worker'])
    q = load_module('csr_primary_qualified_worker', plan['qualified_worker'])
    require(q.owned is owned, 'same actual owned helper')
    require(not RUN.exists(), 'fresh one-shot stage; no retry')
    initial_idle = q.empty_inventory()
    budget(plan, final)
    RUN.mkdir()
    row = q.stat_row(os.getpid())
    identity = dict(hostname=socket.gethostname(), pid=os.getpid(), pgid=os.getpgrp(),
                    startticks=row['startticks'], nonce=uuid.uuid4().hex)
    receipt = dict(schema='bp1-root-pervm-cad-ownership-receipt-v1', **identity,
                   admission_sha256=args.admission_sha256, linux_claim_state='ACK',
                   linux_claim=CLAIM, basis='coordinator conditional release + ROOT perVM onejobprotocol',
                   atomic_global_lock=False, initial_idle=initial_idle)
    ack = RUN/'ROOT-ownership.json'
    q.save(ack, receipt)
    q.save(RUN/'ROOT-ownership-initial.json', receipt)
    state = dict(state='RUNNING behavioral RAM real-bank miter only', source_plan=bind(PLAN),
                 admission=bind(FINAL), commands=[], no_synthesis_mapped_or_board=True)
    started = time.monotonic()
    active = None
    armed = False

    def guard():
        nonlocal active
        require(time.monotonic()-started < plan['limits']['whole_seconds'], 'whole600s limit')
        budget(plan, final)
        require(bind(FINAL)['sha256'] == args.admission_sha256, 'FINAL drift')
        q.validate_ack(json.loads(ack.read_text()), identity, args.admission_sha256, CLAIM)
        rows = q.process_rows()
        if armed and active is None:
            children = [x for x in rows if x['ppid'] == os.getpid() and x['pgid'] == x['pid']]
            require(len(children) <= 1, 'one owned child group')
            if children:
                active = {k:children[0][k] for k in ('pid','pgid','startticks')}
        leader = next((x for x in rows if active and x['pid'] == active['pid']
                       and x['startticks'] == active['startticks']), None)
        foreign = q.vendor_inventory(rows, active['pgid'] if leader else None)
        require(not foreign, 'foreign vendor/launcher; stop owned group only '+json.dumps(foreign))

    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0,0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (plan['limits']['RUN_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_AS, (plan['limits']['per_process_AS_bytes'],)*2)

    def interrupted(sig, frame):
        raise RuntimeError('ROOT behavioral worker signal '+str(sig))

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, interrupted)
    try:
        state['source_copies'] = prepare_inputs(plan)
        (RUN/'build').mkdir()
        for label, seconds, cwd, argv in commands(plan):
            load(args.admission_sha256, True)
            verify_copies(state['source_copies'])
            guard()
            if label in ('negative','positive'):
                cwd.mkdir()
                state[label+'_snapshot'] = physical_snapshot(RUN/'build', cwd)
            entry = dict(label=label, timeout_seconds=seconds, cwd=str(cwd), argv=list(map(str,argv)))
            state['commands'].append(entry)
            q.save(RUN/'session.json', state)
            active = None
            armed = True
            with (RUN/(label+'.log')).open('wb') as log:
                try:
                    entry['owned'] = owned.run(entry['argv'], cwd,
                        dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), log, seconds, guard, limits)
                except BaseException as error:
                    entry['owned'] = getattr(error, 'owned_receipt',
                        dict(failure=repr(error), owned_group_remaining=False, scope='prePopen refusal'))
                    raise
            armed = False
            require(entry['owned']['returncode'] == 0 and not entry['owned']['owned_group_remaining'],
                    'native phase failed '+label)
            if active:
                require(entry['owned']['owned_pgid'] == active['pgid'], 'actual owned group identity')
            active = None
            entry['log'] = bind(RUN/(label+'.log'))
            text = (RUN/(label+'.log')).read_text()
            if label in ('negative','positive'):
                entry['analysis'] = check_log(text, label == 'negative')
            if label == 'xvlog-RTL':
                require(all(row['copy']['path'] in text for row in state['source_copies']),
                        'actual xvlog analyzed all16 source copies')
            if label == 'xelab':
                require(re.search(r'(?m)^Vivado Simulator v2024\.2(?:\.0)?\s*$', text),
                        'actual simulator2024.2 header')
                threads = re.findall(r'Using (\d+) slave threads\.', text)
                require(len(threads) == 1, 'record actual default elaboration parallelism')
                entry['actual_xelab_slave_threads'] = int(threads[0])
            guard()
            q.save(RUN/'session.json', state)
        require(len(state['commands']) == 5, 'five commands only')
        state['state'] = 'PASS behavioral RAM real-CSR primary equivalence plus observable MEPC negative; not mapped/fullcore'
    except BaseException as error:
        state.update(state='FAIL preserved; no retry', error=repr(error))
        raise
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        armed = False
        try:
            load(args.admission_sha256, True)
            verify_copies(state.get('source_copies', []))
            state['source_endcheck'] = 'PASS'
        except BaseException as error:
            state.update(state='FAIL source-endcheck', source_endcheck_error=repr(error))
        remaining = bool(active and owned.group_state(active['pgid'])) or any(
            x.get('owned',{}).get('owned_group_remaining',False) for x in state['commands'])
        if remaining:
            state['state'] = 'FAIL owned group remains; claim HELD'
        release = dict(receipt, linux_claim_state='HELD_OWNED_GROUP_REMAINS' if remaining else 'RELEASED',
                       owned_group_remaining=remaining, outcome=state['state'])
        try:
            current = json.loads(ack.read_text())
            if all(current.get(k) == identity[k] for k in identity) and current.get('linux_claim_state') == 'ACK':
                q.save(ack, release)
            else:
                q.save(RUN/'ROOT-ownership-final.json', release)
        except BaseException as error:
            state.update(state='FAIL ownership receipt', ownership_release_error=repr(error))
            q.save(RUN/'ROOT-ownership-final.json', release)
        state.update(elapsed_seconds=time.monotonic()-started, ownership_final=release)
        q.save(RUN/'session.json', state)
    require(state['state'].startswith('PASS behavioral RAM'), 'final behavioral acceptance')


if __name__ == '__main__':
    main()
