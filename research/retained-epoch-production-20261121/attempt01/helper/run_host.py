#!/usr/bin/env python3
"""One root-host component gate, never a full-core/vendor/board launcher."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import tarfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ADMISSION = ROOT / 'admission.json'
BASE = '225489a435cb0b2a2c0b237077f94418dc89549b'
REL = 'bp_common/src/v/bp_retained_line_store.sv'
STAGE = Path('/dev/shm/zp-retained-canonical-epochs-production-20261121-01')
SENTINEL = Path('/dev/shm/zp-retained1792-allslots-20261121-01')
CAP = 32 * 1024**2
DURABLE_CAP = 24 * 1024**2
HOME_RESERVE = 3 * 1024**3
RAM_RESERVE = 1024**3
VERILATOR = Path('/home/coyang/zynq-parrot/install/bin/verilator')
CASES = [('actual1792',1792,1792,256,8,False),
         ('small-fallback',93,131,256,2,False),
         ('single-set-disabled-I',0,3,1,2,False),
         ('negative-clear0',1792,1792,256,8,True)]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def bind(path):
    path = Path(path)
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def save(path, value):
    raw = (json.dumps(value, indent=2) + '\n').encode()
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(raw)
    temporary.replace(path)


def normalize(backend, module):
    """Only two declaration moves plus a byte-identical auxiliary module."""
    text = backend.decode()
    declarations = ['    wire [epoch_width_p-1:0] line_epoch, inv_epoch;\n',
                    '    wire last_slot;\n']
    for declaration in declarations:
        require(text.count(declaration) == 1, 'unique declaration move')
        text = text.replace(declaration, '')
    anchor = '    wire [set_width_lp-1:0] inv_set = '
    require(text.count(anchor) == 1, 'unique declaration insertion point')
    text = text.replace(anchor, ''.join(declarations) + anchor)
    return text.encode() + b'\n/* verilator lint_off DECLFILENAME */\n' + module + b'/* verilator lint_on DECLFILENAME */\n'


def negative_source(raw):
    anchor = b'if (write_v_i)'
    require(raw.count(anchor) == 1, 'negative exact module-write anchor')
    return raw.replace(anchor, b"if (write_v_i && write_addr_i != '0)")


def command(argv, cwd=None):
    return subprocess.check_output(argv, cwd=cwd, text=True).strip()


def preflight(admission):
    require(admission['schema'] == 'retained-epoch-production-component-v1', 'admission schema')
    require(admission['stage'] == str(STAGE) and admission['cases'] == [list(c) for c in CASES], 'fixed stage/cases')
    require(admission['limits'] == dict(stage_bytes=CAP, durable_bytes=DURABLE_CAP,
            home_reserve_bytes=HOME_RESERVE, ram_reserve_bytes=RAM_RESERVE,
            build_seconds=300, run_seconds=120, child_file_bytes=12*1024**2,
            owned_cleanup_seconds=5), 'fixed budgets')
    for record in admission['inputs']:
        require(bind(record['path']) == record, 'frozen input drift: ' + record['path'])
    backend = Path(admission['sealed_backend']).read_bytes()
    module = Path(admission['sealed_module']).read_bytes()
    candidate = Path(admission['candidate'])
    require(candidate.read_bytes() == normalize(backend, module), 'production declaration-only normalization')
    require(candidate.read_text().count('module bp_retained_epoch_ram\n') == 1, 'exactly one embedded auxiliary definition')
    ref = (HERE/'bp_retained_line_store_reference.sv').read_bytes()
    original = Path(admission['original']).read_bytes()
    require(ref == original.replace(b'module bp_retained_line_store\n', b'module bp_retained_line_store_reference\n'), 'reference only module rename')
    wrapper = (HERE/'retained_metadata_wrapper.sv').read_text()
    require('mismatch_o[l] |= ({lookup_ready' in wrapper, 'corrected all-cell comparison OR must remain active')
    worktree = Path(admission['worktree'])
    require((worktree/'.git').is_file(), 'real BP worktree required')
    require(command(['git','rev-parse','HEAD'],worktree) == BASE, 'fixed base BP')
    require(command(['git','branch','--show-current'],worktree) == admission['branch'], 'fixed dedicated branch')
    require(command(['git','diff','--name-only','HEAD'],worktree).splitlines() == [REL], 'only allowed production file modified')
    require(not command(['git','ls-files','--others','--exclude-standard'],worktree), 'unexpected untracked BP source')
    command(['git','diff','--check'],worktree)
    expected_diff=''.join(difflib.unified_diff(original.decode().splitlines(keepends=True),candidate.read_text().splitlines(keepends=True),fromfile='BP225',tofile='canonical-production'))
    require(expected_diff.encode() == (ROOT/'production.diff').read_bytes(), 'exact production diff')
    return dict(state='PASS-preexecution-source-normalization-only', candidate=bind(candidate),
                reference=bind(HERE/'bp_retained_line_store_reference.sv'), negative_sha256=hashlib.sha256(negative_source(candidate.read_bytes())).hexdigest(),
                component_executed=False)


def namespace_check():
    stat = SENTINEL.stat()
    require((stat.st_dev, stat.st_ino) == (25,299801), 'root-host namespace sentinel mismatch; no private RAM allocation')
    require(not STAGE.exists(), 'preserve one-shot stage; no retries')


def used(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file()) if path.exists() else 0


def guard():
    n = used(STAGE)
    home = used(ROOT/'closed01')
    require(n <= CAP, 'fixed32MiB stage cap')
    require(home <= DURABLE_CAP, 'fixed24MiB durable cap')
    require(shutil.disk_usage('/dev/shm').free >= RAM_RESERVE + CAP - n, '1GiB free plus remaining stage allocation')
    require(shutil.disk_usage(ROOT).free >= HOME_RESERVE + DURABLE_CAP - home, '3GiB HOME reserve plus remaining durable allocation')
    return dict(stage_bytes=n, durable_bytes=home)


def negative_gate(text):
    require('cycle/payload/RAM-port miter mismatch' in text and 'RETAINED_METADATA_MITER_PASS' not in text, 'negative actual miter rejection')
    witness = re.findall(r'EPOCH_NEGATIVE_WITNESS tick=(\d+) total=(\d+) epochI=(\d+) epochD=(\d+) protocol=(\d+)',text)
    require(len(witness) == 1 and witness[0][1:] == ('2','0','1','0'), 'negative must reject at D all-cell comparison before protocol divergence')
    return dict(tick=int(witness[0][0]), total=2, epochI=0, epochD=1, protocol=0)


def run(argv, cwd, log, timeout, negative=False):
    guard()
    process = None
    start = time.monotonic()
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        resource.setrlimit(resource.RLIMIT_FSIZE,(12*1024**2,12*1024**2))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(STAGE/'tmp'),
               VERILATOR_ROOT='/home/coyang/zynq-parrot/install/share/verilator')
    # No inherited compiler flags or alternate tool overrides.
    for name in ['CXX','CC','AR','MAKE','CXXFLAGS','CPPFLAGS','LDFLAGS','MAKEFLAGS','MFLAGS']:
        env.pop(name,None)
    env['PATH'] = '/usr/bin:/bin'
    try:
        with log.open('wb') as stream:
            process = subprocess.Popen(list(map(str,argv)),cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,
                    start_new_session=True,preexec_fn=limits)
            while process.poll() is None:
                guard()
                require(time.monotonic()-start < timeout, 'fixed component deadline')
                time.sleep(.1)
        guard()
        rc = process.returncode
        require((rc != 0) if negative else (rc == 0), 'component command failed: ' + str(log))
        return dict(argv=list(map(str,argv)),cwd=str(cwd),returncode=rc,seconds=time.monotonic()-start,log=bind(log))
    finally:
        if process is not None:
            try:
                os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)


def execute(admission):
    proof = preflight(admission)
    admission_snapshot = bind(ADMISSION)
    namespace_check()  # Before any RAM write.
    require(not (ROOT/'host-supervision.json').exists() and not (ROOT/'closed01').exists(), 'one-shot durable attempt')
    guard()
    STAGE.mkdir()
    state = dict(state='RUNNING-owned-component-only', admission=bind(ADMISSION), preflight=proof,
                 owner_pid=os.getpid(), stage=str(STAGE), commands=[], runs=[], frozen_inputs=admission['inputs'])
    def checkpoint():
        save(STAGE/'session.json',state)
        save(ROOT/'host-supervision.json',state)
    def stopped(signum, frame):
        raise RuntimeError('owned flow interrupted by signal '+str(signum))
    for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:
        signal.signal(sig,stopped)
    checkpoint()
    try:
        (STAGE/'tmp').mkdir()
        source = STAGE/'source'
        source.mkdir()
        shutil.copyfile(admission['candidate'],source/'bp_retained_line_store.sv')
        for name in ['bp_retained_line_store_reference.sv','retained_metadata_wrapper.sv','driver.cpp']:
            shutil.copyfile(HERE/name,source/name)
        for name,ilines,dlines,sets,epoch,negative in CASES:
            out=STAGE/name
            out.mkdir()
            candidate=source/'bp_retained_line_store.sv'
            if negative:
                candidate=out/'bp_retained_line_store.sv'
                candidate.write_bytes(negative_source((source/'bp_retained_line_store.sv').read_bytes()))
                state['negative_source']=bind(candidate)
            args=[VERILATOR,'--cc','--exe','--build','--trace-fst','--assert','-Wall',
                  '-DBP_RETAINED_METADATA_VERIFY','--top-module','retained_metadata_wrapper',
                  '-GI_LINES='+str(ilines),'-GD_LINES='+str(dlines),'-GRETAINED_SETS='+str(sets),'-GEPOCH_WIDTH='+str(epoch),
                  '-CFLAGS','-std=c++14','-j','1','-MAKEFLAGS','VM_PARALLEL_BUILDS=0','--Mdir',out/'obj',
                  candidate,source/'bp_retained_line_store_reference.sv',source/'retained_metadata_wrapper.sv',source/'driver.cpp']
            state['commands'].append(run(args,out,out/'build.log',300))
            exe=out/'obj/Vretained_metadata_wrapper'
            state.setdefault('executables',{})[name]=bind(exe)
            checkpoint()
            for mode in (('inverted',) if negative else ('inverted','different-periods')):
                runtime=out/mode
                runtime.mkdir()
                log=out/('run-'+mode+'.log')
                result=run([exe]+([] if mode=='inverted' else [mode]),runtime,log,120,negative)
                text=log.read_text()
                if negative:
                    result['all_cell_witness']=negative_gate(text)
                else:
                    for marker in ['RETAINED_METADATA_MITER_PASS ','RETAINED_METADATA_HAZARDS_PASS ','RETAINED_TEST_EXIT_CLEAN']:
                        require(text.count(marker)==1,'complete miter/hazard/clean markers')
                result.update(case=name,mode=mode,expected_rejection=negative,fst=bind(runtime/'retained-line-store.fst'))
                state['runs'].append(result)
                checkpoint()
        require(len(state['runs'])==7,'exactly six normal plus one negative')
        state['final_source_check']=preflight(admission)
        require(bind(ADMISSION)==admission_snapshot, 'admission drift')
        state.update(state='PASS-integrated-production-cycle512b-allcells-coherence-plus-negative',resources=guard())
    except BaseException as error:
        state.update(state='FAIL-preserved-no-retry',error=repr(error))
        raise
    finally:
        # Preserve every generated source/model/log/FST even on failure. No deletion.
        try:
            state['final_source_check']=preflight(admission)
            require(bind(ADMISSION)==admission_snapshot, 'admission drift')
        except BaseException as error:
            state.update(state='FAIL-preserved-source-drift',source_error=repr(error))
        checkpoint()
        closed=ROOT/'closed01'
        closed.mkdir()
        archive=closed/'component-stage.tar.gz'
        try:
            # Streaming archive; disk/resource guard is checked between each member.
            with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
                for path in sorted(STAGE.rglob('*')):
                    guard()
                    if path.is_file():
                        tar.add(path,arcname=str(path.relative_to(STAGE)),recursive=False)
            guard()
            save(closed/'manifest.json',dict(state=state['state'],admission=bind(ADMISSION),archive=bind(archive),session=state))
        except BaseException as error:
            state.update(state='FAIL-preserved-archive-or-resource',archive_error=repr(error))
        checkpoint()
        print(ROOT/'host-supervision.json',state['state'],flush=True)
    require(state['state'].startswith('PASS-'),'component flow did not close PASS')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight',action='store_true')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    require(args.preflight != args.execute,'choose exactly preflight or execute')
    admission=json.loads(ADMISSION.read_text())
    if args.preflight:
        print(json.dumps(preflight(admission),indent=2))
    else:
        execute(admission)


if __name__=='__main__':
    main()
