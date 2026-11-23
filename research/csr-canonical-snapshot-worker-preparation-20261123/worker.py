#!/usr/bin/env python3
"""Default offline; ROOT-only canonical CSR real-primary component; no synthesis."""
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
RUN = Path('/run/user/1001/zp-csr-canonical-snapshot-component-20261123-01')
PREP = Path('/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/csr-canonical-snapshot-component-preparation-20261123')
CODEC = Path('/home/coyang/bp-csr-canonical-snapshot-20261123/bp_be/src/v/bp_be_csr_snapshot_store_canonical.sv')
CLAIM = 'ONE canonical inactive CSR real-two-bank component positive and three negatives; no synthesis'
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
    require(plan['schema'] == 'csr-canonical-snapshot-worker-plan-v1', 'fixed behavioral schema')
    require(plan['stage'] == str(RUN) and plan['linux_claim'] == CLAIM, 'fixed case/stage')
    for row in plan['inputs']:
        verify(row)
    require(bind(Path(__file__).resolve()) in plan['inputs'], 'actual worker pin')
    # No arbitrary module/file selection through FINAL or command line.
    require(plan['qualified_worker']['path'] == str(HELPERS/'qualified_worker.py'), 'fixed qualified API')
    require(plan['owned_worker']['path'] == str(HELPERS/'software_owned_v2.py'), 'fixed owned API')
    require(plan['DUT']['kind'] == 'production_CANONICAL_RAM_only', 'not a mapped/FF admission')
    require(len(plan['compile_sources']) == 17, 'exact17 RTL inputs plus separate glbl')
    require(plan['phase_seconds'] == {'xvlog-global':60,'xvlog-RTL':90,'xelab':180,'negative':45,'noncanonical':45,'positive':300,'xvlog-global-mutant':30,'xvlog-RTL-mutant':90,'xelab-mutant':180,'reconstruction':45}, 'fixed one-shot phase bounds')
    if not execute:
        return plan, None
    require(expected and bind(FINAL)['sha256'] == expected, 'exact ROOT FINAL SHA required')
    final = json.loads(FINAL.read_text())
    require(final['schema'] == 'csr-canonical-snapshot-worker-admission-v1' and final['launchable'] is True,
            'DRAFT cannot execute')
    require(final['source_plan'] == bind(PLAN) and final['limits'] == plan['limits'], 'exact plan/limits')
    require(final['linux_claim'] == CLAIM, 'actual behavioral scope')
    verify(final['ROOT_release'])
    release = json.loads(Path(final['ROOT_release']['path']).read_text())
    require(release.get('allow_csr_canonical_snapshot_component') is True
            and release.get('source_plan') == bind(PLAN)
            and release.get('linux_claim') == CLAIM, 'explicit ROOT release')
    other = final['fixed_OTHER_reservations']
    require(set(other) == {'RUN_bytes', 'HOME_bytes'}
            and all(type(v) is int and v >= 0 for v in other.values()), 'priced fixed OTHER')
    require(release.get('fixed_OTHER_reservations') == other, 'release prices OTHER')
    require(socket.gethostname() == plan['target_hostname'], 'actual tool host')
    require(set(final['tool_inputs']) == {'xvlog','xelab','xsim','glbl'}, 'ROOT exact tool/glbl byte authority')
    for name,row in final['tool_inputs'].items():
        require(row['path'] == str(V/('data/verilog/src/glbl.v' if name=='glbl' else 'bin/'+name)), 'fixed actual tool paths')
        verify(row)
    require(final['frozen_preparation'] == bind(PREP/'handoff.json'), 'same frozen six-file preparation')

    return plan, final


def usage(path):
    return sum(x.stat().st_size for x in path.rglob('*') if x.is_file()) if path.exists() else 0


def budget(plan, final):
    limits = plan['limits']
    run, home = usage(RUN), usage(HERE)+usage(PREP)+CODEC.stat().st_size
    source = usage(HERE)+usage(PREP)+CODEC.stat().st_size
    require(source <= limits['source_packet_bytes'], 'both frozen prep/worker/codec source-authority family cap')
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
    copies = []
    anchor = b"    if (int'(read_addr_i)<contexts_p) read_data_o = decode(encoded_read);"
    mutation = anchor+b"\n    if (read_valid_o) read_data_o[962] = ~read_data_o[962];"
    for arm in ('normal','mutant'):
        folder = RUN/('inputs-'+arm)
        folder.mkdir()
        for row in plan['compile_sources']:
            verify(row)
            dest = folder/Path(row['path']).name
            require(not dest.exists(), 'unique fixed source basename')
            original = Path(row['path']).read_bytes()
            body = original
            mutated = arm=='mutant' and Path(row['path'])==CODEC
            if mutated:
                require(body.count(anchor)==1, 'one exact decoder mutation anchor')
                body=body.replace(anchor,mutation,1)
                require(body.replace(mutation,anchor,1)==original, 'only mscratch-bit0 reconstruction mutation')
            prefix = b'' if re.search(rb'(?m)^\s*`timescale\b', body) else b'`timescale 1ps/1ps\n'
            dest.write_bytes(prefix+body)
            require(dest.read_bytes()[len(prefix):] == body, 'timescale-only wrapper beyond declared mutant')
            copies.append(dict(arm=arm,source=row,copy=bind(dest),prefix=prefix.decode(),mutation='mscratch bit0 decoded read only' if mutated else None))
    require(sum(bool(r['mutation'])for r in copies)==1, 'exactly one mutation in fresh copy, originals unchanged')
    return copies

def verify_copies(rows):
    for row in rows:
        verify(row['copy'])


def commands(plan):
    def compile_argv(arm):
        rtl=[V/'bin/xvlog','--sv']
        for path in plan['include_dirs']:rtl+=['-i',path]
        for define in plan['defines']:rtl+=['-d',define]
        return rtl+[RUN/('inputs-'+arm)/Path(r['path']).name for r in plan['compile_sources']]
    def elaborate(name):
        return [V/'bin/xelab','-L','unisims_ver','-L','unimacro_ver','-L','secureip',
                '-mt','8','work.csr_primary_miter','work.glbl','-s',name]
    def simulate(name,plusargs=()):
        args=[V/'bin/xsim',name]
        for value in plusargs:args+=['-testplusarg',value]
        return args+['-tclbatch',HERE/'run.tcl']
    normal='csr_canonical_normal'; mutant='csr_canonical_reconstruction'
    return [
        ('xvlog-global',60,RUN/'build-normal',[V/'bin/xvlog',V/'data/verilog/src/glbl.v']),
        ('xvlog-RTL',90,RUN/'build-normal',compile_argv('normal')),
        ('xelab',180,RUN/'build-normal',elaborate(normal)),
        ('negative',45,RUN/'negative',simulate(normal,['NEGATIVE=1'])),
        ('noncanonical',45,RUN/'noncanonical',simulate(normal,['NONCANONICAL_WRITE'])),
        ('positive',300,RUN/'positive',simulate(normal)),
        ('xvlog-global-mutant',30,RUN/'build-mutant',[V/'bin/xvlog',V/'data/verilog/src/glbl.v']),
        ('xvlog-RTL-mutant',90,RUN/'build-mutant',compile_argv('mutant')),
        ('xelab-mutant',180,RUN/'build-mutant',elaborate(mutant)),
        ('reconstruction',45,RUN/'reconstruction',simulate(mutant))]


def check_log(text,label,rc):
    lines=[line.rstrip('\r')for line in text.splitlines()]
    width=[tuple(map(int,m))for m in re.findall(r'(?m)^CSR_CANONICAL_WIDTH expanded=(\d+) encoded=(\d+) contexts=(\d+)\s*$',text)]
    require(len(width)==1 and width[0][0]==1666 and 0<width[0][1]<1666 and width[0][2]==4, 'actual codec width marker')
    positives=[line for line in lines if re.fullmatch(r'CSR_PRIMARY_EQUIVALENCE_PASS checks=\d+ cycles=\d+ reads=\d+ saves=\d+ reloads=\d+',line)]
    negatives=[line for line in lines if re.fullmatch(r'CSR_PRIMARY_NEGATIVE_DETECTED interface=mepc bit=2 cycles=\d+ checks=\d+',line)]
    fatal_lines=[line for line in lines if re.match(r'^(?:Fatal:|FATAL_ERROR|FATAL:)',line)]
    if label in ('noncanonical','reconstruction'):
        marker='CSR_CANONICAL_NONCANONICAL_WRITE' if label=='noncanonical' else 'CSR_CANONICAL_RECONSTRUCTION_MISMATCH'
        require(rc!=0 and text.count(marker)==1 and not positives and not negatives, 'exact expected HDL-fatal negative, nonzero native exit')
        require(len(fatal_lines)==1 and marker in fatal_lines[0], 'only expected target assertion fatal')
        require('CSR_PRIMARY_MISMATCH'not in text and 'fixed HDL watchdog'not in text, 'no unrelated mismatch/timeout')
        return dict(expected_assertion=marker,actual_returncode=rc,expanded_bits=width[0][0],encoded_bits=width[0][1],contexts=width[0][2],raw_tool_error_lines=[line for line in lines if re.match(r'^(?:ERROR:|Error:)',line)])
    require(rc==0 and not fatal_lines and not any(re.match(r'^(?:ERROR:|Error:)',line)for line in lines), 'normal/MEPC exact native0, no fatal/error')
    require(not any(marker in text for marker in ('CSR_PRIMARY_MISMATCH','CSR_CANONICAL_NONCANONICAL_WRITE','CSR_CANONICAL_RECONSTRUCTION_MISMATCH')), 'no codec/primary assertion')
    if label=='negative':require(len(negatives)==1 and not positives,'original MEPC negative terminal')
    else:
        require(len(positives)==1 and not negatives,'one exact positive terminal')
        sweep='CSR_CANONICAL_REAL_PRODUCER_SWEEP_PASS banks=2 contexts=4 fields=26 inputbits=64 writes=13312'
        require(lines.count(sweep)==1, 'complete unchanged-oracle real producer sweep')
    return dict(marker=(negatives if label=='negative'else positives)[0],expanded_bits=width[0][0],encoded_bits=width[0][1],contexts=width[0][2])


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
        require(time.monotonic()-started < plan['limits']['whole_seconds'], 'whole1100s limit')
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
        (RUN/'build-normal').mkdir()
        (RUN/'build-mutant').mkdir()
        (RUN/'tmp').mkdir()
        for label, seconds, cwd, argv in commands(plan):
            load(args.admission_sha256, True)
            verify_copies(state['source_copies'])
            guard()
            if label in ('negative','noncanonical','positive','reconstruction'):
                cwd.mkdir()
                state[label+'_snapshot'] = physical_snapshot(RUN/('build-mutant'if label=='reconstruction'else 'build-normal'), cwd)
            entry = dict(label=label, timeout_seconds=seconds, cwd=str(cwd), argv=list(map(str,argv)))
            state['commands'].append(entry)
            q.save(RUN/'session.json', state)
            active = None
            armed = True
            with (RUN/(label+'.log')).open('wb') as log:
                try:
                    entry['owned'] = owned.run(entry['argv'], cwd,
                        dict(os.environ, PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(RUN/'tmp')), log, seconds, guard, limits)
                except BaseException as error:
                    entry['owned'] = getattr(error, 'owned_receipt',
                        dict(failure=repr(error), owned_group_remaining=False, scope='prePopen refusal'))
                    raise
            armed = False
            require(entry['owned']['failure'] is None and not entry['owned']['owned_group_remaining'], 'owned lifecycle failed '+label)
            require((entry['owned']['returncode'] != 0) if label in ('noncanonical','reconstruction') else (entry['owned']['returncode'] == 0), 'native returncode '+label)
            if active:
                require(entry['owned']['owned_pgid'] == active['pgid'], 'actual owned group identity')
            active = None
            entry['log'] = bind(RUN/(label+'.log'))
            text = (RUN/(label+'.log')).read_text()
            if label in ('negative','noncanonical','positive','reconstruction'):
                entry['analysis'] = check_log(text,label,entry['owned']['returncode'])
            if label in ('xvlog-RTL','xvlog-RTL-mutant'):
                arm='mutant'if label.endswith('-mutant')else 'normal'
                rows=[r for r in state['source_copies']if r['arm']==arm]
                require(len(rows)==17 and all(r['copy']['path'] in text for r in rows), 'actual xvlog analyzed all17 declared copies')
            if label in ('xelab','xelab-mutant'):
                require(re.search(r'(?m)^Vivado Simulator v2024\.2(?:\.0)?\s*$', text),
                        'actual simulator2024.2 header')
                threads = re.findall(r'Using (\d+) slave threads\.', text)
                require(len(threads)==1 and 0<int(threads[0])<=8,'actual elaboration workers<=8')
                entry['actual_xelab_slave_threads'] = int(threads[0])
            guard()
            q.save(RUN/'session.json', state)
        require(len(state['commands'])==10,'ten fixed commands only')
        widths={x['analysis']['encoded_bits']for x in state['commands']if 'analysis'in x}
        require(len(widths)==1,'one identical actual codec width across all four executions')
        state['state'] = 'PASS behavioral canonical CSR real-primary sweep plus MEPC/canonicality/reconstruction negatives; not mapped/fullcore'
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
    require(state['state'].startswith('PASS behavioral canonical CSR'), 'final behavioral acceptance')


if __name__ == '__main__':
    main()
