#!/usr/bin/env python3
"""Default offline. Fresh ROOT-only raw versus canonical primary CSR mapping, no simulation."""
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
PLAN = HERE/'plan.json'
FINAL = HERE/'admission.FINAL.json'
RUN = Path('/run/user/1001/zp-csr-canonical-paired-mapping-20261123-01')
HELPERS = Path('/home/coyang/fpga-artifacts/context-resume/csr-snapshot-mapped-functional-20261122/runtime-full05')
WRAPPER = Path('/home/coyang/zynq-parrot-linux-capacity/codex-skills/bp-fpga-synthesis/scripts/run_vivado_2024_2.sh')
CLAIM = 'ONE paired real-CSR raw1666 RAM then canonical741 RAM OOC mapping; no mapped/fullcore/fit claim'


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def bind(path):
    path = Path(path)
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def verify(row):
    require(bind(row['path']) == row, 'input/source drift '+row['path'])


def module(name, row):
    verify(row)
    spec = importlib.util.spec_from_file_location(name, row['path'])
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    require(Path(result.__file__).resolve() == Path(row['path']).resolve(), 'actual helper identity')
    return result


def load(expected=None, executing=False):
    plan = json.loads(PLAN.read_text())
    require(plan['schema'] == 'csr-canonical-paired-mapping-plan-v1', 'fixed source plan')
    require(plan['stage'] == str(RUN) and plan['arms'] == ['raw','canonical'], 'fixed fresh pair')
    require(plan['linux_claim'] == CLAIM, 'scope')
    require(usage(HERE) <= plan['source_packet_cap_bytes'], 'whole source/authority packet96KiB')
    for row in plan['inputs']:
        verify(row)
    require(bind(Path(__file__).resolve()) in plan['inputs'], 'actual worker pin')
    require(plan['qualified_worker']['path'] == str(HELPERS/'qualified_worker.py')
            and plan['owned_worker']['path'] == str(HELPERS/'software_owned_v2.py'), 'fixed qualified APIs')
    verify(plan['behavioral_session'])
    proof = json.loads(Path(plan['behavioral_session']['path']).read_text())
    require(proof['state'].startswith('PASS composite behavioral canonical real-two-bank13312 sweep')
            and proof['source_endcheck']=='PASS' and proof['old01_endcheck'].startswith('PASS complete read-only')
            and proof['ownership_final']['linux_claim_state']=='RELEASED'
            and not proof['ownership_final']['owned_group_remaining']
            and proof['final_global_idle']['vendor_processes']==[], 'exact completed behavioral composite prerequisite')
    require(len(proof['commands'])==5 and all(r['owned']['returncode']==0
            and r['owned']['failure'] is None and not r['owned']['owned_group_remaining']
            for r in proof['commands']), 'all five continuation receipts')
    require(proof['commands'][0]['analysis']['encoded_bits']==741
            and proof['commands'][-1]['analysis']['expected_assertion']=='CSR_CANONICAL_RECONSTRUCTION_MISMATCH'
            and proof['promotion']['noncanonical']['expected_assertion']=='CSR_CANONICAL_NONCANONICAL_WRITE',
            'same actual741 codec and both target assertions')
    if not executing:
        return plan, None
    require(expected and bind(FINAL)['sha256'] == expected, 'exact ROOT FINAL SHA')
    final = json.loads(FINAL.read_text())
    require(final['schema'] == 'csr-canonical-paired-mapping-admission-v1'
            and final['launchable'] is True, 'DRAFT cannot execute')
    require(final['source_plan'] == bind(PLAN) and final['limits'] == plan['limits']
            and final['linux_claim'] == CLAIM, 'exact plan/limits/claim')
    verify(final['ROOT_release'])
    release_path = Path(final['ROOT_release']['path']).resolve()
    outside_authority = 0 if HERE in release_path.parents else final['ROOT_release']['bytes']
    require(usage(HERE)+outside_authority <= plan['source_packet_cap_bytes'],
            'source packet plus external ROOT authority96KiB')
    release = json.loads(Path(final['ROOT_release']['path']).read_text())
    require(release.get('allow_csr_canonical_paired_mapping') is True
            and release.get('source_plan') == bind(PLAN)
            and release.get('linux_claim') == CLAIM, 'fresh explicit ROOT release')
    other = final['fixed_OTHER_reservations']
    require(set(other) == {'RUN_bytes','HOME_bytes'}
            and all(type(x) is int and x >= 0 for x in other.values()), 'priced OTHER')
    require(release.get('fixed_OTHER_reservations') == other, 'release resource identity')
    verify(final['behavioral_archive_complete'])
    close = json.loads(Path(final['behavioral_archive_complete']['path']).read_text())
    require(close['state'].startswith('PASS complete lossless canonical behavioral history')
            and close['all_actual_originals_retained'] is True
            and close['global_vendor_at_end']['vendor_processes']==[], 'complete lossless original behavioral history')
    verify(final['ROOT_behavioral_future_freeze'])
    freeze = json.loads(Path(final['ROOT_behavioral_future_freeze']['path']).read_text())
    require(freeze.get('ROOT_approved') is True and freeze.get('behavioral_archive_complete')==final['behavioral_archive_complete']
            and freeze.get('behavioral_RUN_future_bytes')==0, 'explicit completed old behavioral future0, never inferred')
    require(socket.gethostname() == plan['target_hostname'], 'actual tool host')
    return plan, final


def usage(path):
    return sum(x.stat().st_size for x in path.rglob('*') if x.is_file()) if path.exists() else 0


def budget(plan, final):
    limit = plan['limits']
    run, home = usage(RUN), usage(HERE)
    require(run <= limit['mapped_output_bytes'] <= limit['RUN_bytes'] and home <= limit['HOME_family_bytes'], 'mapped output64MiB inside256MiB RUN / HOME8MiB caps')
    other = final['fixed_OTHER_reservations']
    require(shutil.disk_usage(RUN.parent).free >= limit['RUN_floor_bytes']
            +limit['RUN_bytes']-run+other['RUN_bytes'], 'RUN floor/remaining/OTHER')
    require(shutil.disk_usage(HERE).free >= limit['HOME_floor_bytes']
            +limit['HOME_family_bytes']-home+other['HOME_bytes'], 'HOME floor/remaining/OTHER')
    available = next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines()
                     if x.startswith('MemAvailable:'))
    require(available >= limit['MemAvailable_floor_bytes'], 'host memory floor')
    return dict(RUN_bytes=run, HOME_bytes=home, MemAvailable_bytes=available)


def command(arm):
    require(arm in ('raw','canonical'), 'fixed arm only')
    return list(map(str,[WRAPPER,'-mode','batch','-source',HERE/'probe.tcl',
                         '-log','vivado.log','-journal','vivado.jou','-tclargs',arm]))


def analyze(folder, arm):
    required = ['blackboxes.txt','type-widths.tsv','clocks.tsv','source-context.tsv',
                'utilization.rpt','timing-summary.rpt','timing-paths.rpt','control-sets.rpt',
                'primitives.tsv','realization.tsv','synthesized.dcp','functional.v','snapshot-shape.tsv',
                'mapped-bit-ports.tsv','mapped-logical-ports.tsv','used-primitive-properties.tsv']
    require(all((folder/name).is_file() for name in required), 'complete mapped artifacts')
    require(not (folder/'blackboxes.txt').read_text().strip(), 'no blackbox')
    text = (folder/'console.log').read_text()
    require(re.search(r'(?m)^PRIMARY_TOOL 2024\.2[^\n]* THREADS 2\s*$', text), 'actual2024.2/two workers')
    require(len(re.findall(r'(?m)^CSR_CANONICAL_PRIMARY_MAPPING_COMPLETE '+arm+r'\s*$', text)) == 1,
            'original recipe completed exactly once')
    terminals = re.findall(r'(?m)^CSR_PRIMARY_PORT_INVENTORY_COMPLETE arm='+arm+r' logical_ports=86 bit_ports=(\d+)\s*$', text)
    require(len(terminals) == 1, 'complete appended port inventory')
    expected = {x['name']:x['direction'] for x in json.loads((HERE/'interface.json').read_text())['ports']}
    bit_rows = [line.split('\t') for line in (folder/'mapped-bit-ports.tsv').read_text().splitlines()[1:]]
    bits = {}
    for name, logical, direction in bit_rows:
        require(name not in bits and expected.get(logical) == direction, 'unique actual logical/bit direction')
        bits[name] = dict(logical=logical, direction=direction)
    logicals = {}
    for line in (folder/'mapped-logical-ports.tsv').read_text().splitlines()[1:]:
        name, direction, count = line.split('\t')
        require(name not in logicals and expected.get(name) == direction, 'unique mapped logical port')
        names = sorted(n for n, row in bits.items() if row['logical'] == name)
        require(len(names) == int(count) and int(count) > 0, 'all mapped bits counted')
        logicals[name] = dict(direction=direction, bits=int(count), mapped_bit_names=names)
    require(set(logicals) == set(expected) and len(logicals) == 86
            and len(bits) == int(terminals[0]), 'all86 logical and every bit port')
    clock = (folder/'clocks.tsv').read_text().splitlines()
    require(len(clock) == 1, 'one owning clock')
    name, period, waveform = clock[0].split('\t')
    require(name == 'owning_clock' and float(period) == 50
            and [float(x) for x in waveform.strip('{}').split()] == [0,25], 'actual50ns owning clock')
    report = (folder/'utilization.rpt').read_text()
    top = 'csr_native_consumer_wrapper' if arm=='raw' else 'csr_native_canonical_wrapper'
    match = re.search(r'^\| '+re.escape(top)+r'\s*\|\s*\(top\)\s*\|([^\n]+)\|$', report, re.M)
    require(match is not None, 'exact primary resource row')
    values = [int(x.strip().replace(',','')) for x in match[1].split('|')]
    require(len(values) == 8, 'eight actual utilization columns')
    resources = dict(zip(['LUT','logic_LUT','LUTRAM','SRL','FF','RAMB36','RAMB18','DSP'], values))
    require(resources['RAMB36'] == 0 and resources['RAMB18'] == 0 and resources['DSP'] == 0,
            'no BRAM/DSP substitute')
    require(resources['LUTRAM'] > 0, 'actual distributed snapshot RAM not absent')
    # FF count also includes the real resident CSR banks. No per-bit retained
    # liveness/removable-cost claim follows from this condition or hierarchy.
    return dict(resources=resources, logical_ports=logicals, mapped_bit_ports=bits,
                scope='OOC real CSR banks with controller cut; no mapped functional/fullcore/fit inference')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--admission-sha256')
    args = ap.parse_args()
    plan, final = load(args.admission_sha256, args.execute)
    if not args.execute:
        print(json.dumps(dict(state='DRAFT; no tools/inventory', source_plan=bind(PLAN),
                              commands={arm:command(arm) for arm in plan['arms']}), indent=2))
        return
    owned = module('software_owned_v2', plan['owned_worker'])
    q = module('csr_primary_mapping_qualified_worker', plan['qualified_worker'])
    require(q.owned is owned, 'same qualified owned helper')
    require(not RUN.exists(), 'fresh one-shot pair only')
    initial = q.empty_inventory()
    budget(plan, final)
    RUN.mkdir()
    row = q.stat_row(os.getpid())
    identity = dict(hostname=socket.gethostname(), pid=os.getpid(), pgid=os.getpgrp(),
                    startticks=row['startticks'], nonce=uuid.uuid4().hex)
    receipt = dict(schema='bp1-root-pervm-cad-ownership-receipt-v1', **identity,
                   admission_sha256=args.admission_sha256, linux_claim_state='ACK', linux_claim=CLAIM,
                   basis='coordinator conditional release + ROOT perVM onejobprotocol',
                   atomic_global_lock=False, initial_idle=initial)
    ack = RUN/'ROOT-ownership.json'
    q.save(ack, receipt)
    q.save(RUN/'ROOT-ownership-initial.json', receipt)
    state = dict(state='RUNNING paired primary component only', source_plan=bind(PLAN),
                 admission=bind(FINAL), arms=[], no_simulation_or_board=True)
    start = time.monotonic()
    active = None
    armed = False
    arm_start = None

    def guard():
        nonlocal active
        require(time.monotonic()-start < plan['limits']['whole_seconds'], 'fixed1250s whole pair')
        if armed:
            require(time.monotonic()-arm_start < 600, 'fixed600s arm parent bound')
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
        require(not foreign, 'foreign vendor/launcher; abort owned PG only '+json.dumps(foreign))

    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0,0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (plan['limits']['RUN_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_AS, (plan['limits']['per_process_AS_bytes'],)*2)

    def interrupted(sig, frame):
        raise RuntimeError('ROOT paired worker signal '+str(sig))

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, interrupted)
    try:
        for arm in plan['arms']:
            load(args.admission_sha256, True)
            guard()
            q.empty_inventory()
            folder = RUN/arm
            folder.mkdir()
            entry = dict(arm=arm, argv=command(arm), cwd=str(folder), timeout_seconds=580)
            state['arms'].append(entry)
            q.save(RUN/'session.json', state)
            active = None
            armed = True
            arm_start = time.monotonic()
            with (folder/'console.log').open('wb') as log:
                try:
                    entry['owned'] = owned.run(entry['argv'], folder,
                        dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), log, 580, guard, limits)
                except BaseException as error:
                    entry['owned'] = getattr(error, 'owned_receipt',
                        dict(failure=repr(error), owned_group_remaining=False, scope='prePopen refusal'))
                    raise
            armed = False
            require(entry['owned']['returncode'] == 0 and entry['owned']['failure'] is None and not entry['owned']['owned_group_remaining'],
                    'native arm failed; no next arm')
            if active:
                require(entry['owned']['owned_pgid'] == active['pgid'], 'actual group identity')
            active = None
            guard()
            entry['analysis'] = analyze(folder, arm)
            if arm == 'canonical':
                old = state['arms'][0]['analysis']
                require(entry['analysis']['logical_ports'] == old['logical_ports']
                        and entry['analysis']['mapped_bit_ports'] == old['mapped_bit_ports'],
                        'all86 logical widths/directions and every bit name must match')
                state['canonical_minus_raw'] = {k:entry['analysis']['resources'][k]-v
                                                for k,v in old['resources'].items()}
            entry['artifacts'] = [bind(x) for x in sorted(folder.rglob('*')) if x.is_file()]
            load(args.admission_sha256, True)
            guard()
            q.save(RUN/'session.json', state)
        require(len(state['arms']) == 2, 'complete pair only')
        state['state'] = 'PASS paired real-CSR raw1666 versus canonical741 OOC resources and all86 logical bit-port identity; MAPPED_FUNCTION_PENDING; no fullcore/fit'
    except BaseException as error:
        state.update(state='FAIL preserved; no retries', error=repr(error))
        raise
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        armed = False
        try:
            load(args.admission_sha256, True)
            state['source_endcheck'] = 'PASS'
            state['global_vendor_at_end'] = q.empty_inventory()
        except BaseException as error:
            state.update(state='FAIL source-endcheck', source_endcheck_error=repr(error))
        remaining = bool(active and owned.group_state(active['pgid'])) or any(
            x.get('owned',{}).get('owned_group_remaining',False) for x in state['arms'])
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
        state.update(elapsed_seconds=time.monotonic()-start, ownership_final=release)
        q.save(RUN/'session.json', state)
    require(state['state'].startswith('PASS paired real-CSR'), 'final pair acceptance')


if __name__ == '__main__':
    main()
