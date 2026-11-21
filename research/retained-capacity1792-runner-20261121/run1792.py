#!/usr/bin/env python3
"""Run one next fixed1792 case, only after complete previous raw/counter audits."""
import argparse
import fcntl
import frozen
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import selectors
import signal
import time
from types import SimpleNamespace

from build import ROOT, bind, require, verify_coverage
from run_case import primary_counts
from audit1792 import source_bindings

ORDER = ('d-enabled', 'd-off', 'i-enabled')


def previous_gate(cohort, role):
    for previous in ORDER[:ORDER.index(role)]:
        case = cohort / previous
        audit = cohort / (previous + '-audit')
        run = json.loads((case / 'verification.json').read_text())
        proof = json.loads((audit / 'verification.json').read_text())
        counters = json.loads((audit / 'counter-words.json').read_text())
        require(run['role'] == previous and run['state'].startswith('PASS') and proof['state'].startswith('PASS'), 'complete fixed prior case')
        require(proof['lines'] == 1792 and proof['sets'] == 256 and len(proof['targets']) == 1792, 'all prior actual targets')
        require(counters['state'] == 'PASS final FST counter words equal actual GP0 reads' and
                counters['audit'] == bind(audit / 'verification.json') and counters['values'] == run['counters'], 'prior actual counter corroboration')
        for record in run['files'] + [run['admission']] + list(proof['bindings'].values()) + [counters['auditor']]:
            require(bind(record['path']) == record, 'prior closed source/raw proof drift')


def check_inputs(preparation):
    frozen.verify()
    for record in preparation['linked_libraries']:
        require(bind(record['path'])==record,'qualified runtime library drift')
    for key in ('model', 'model_stamp', 'compiled_sources', 'compiled_metadata', 'host_dependency', 'program', 'preparer', 'root_session', 'leaf_coverage', 'stage_guard'):
        record = preparation[key]
        require(bind(record['path']) == record, 'frozen preparation changed: ' + key)
    for record in preparation['critical_sources']:
        require(bind(record['path'])['sha256'] == record['sha256'], 'critical host/RTL source drift')
    stage=Path(preparation['case_paths']['d-enabled']).parent.resolve()
    model_path=Path(preparation['model']['path'])
    require(model_path.resolve().parent==stage/'model' and not model_path.is_symlink(),'model must be charged inside fixed stage')
    schema_path=Path(__file__).parent/'schema167.json'
    require(bind(schema_path)['sha256']=='60127818144df33e34bf3dc998ca317fac67cbefaf53784123836af8ba08c78e','fixed capacity167 contract')
    coverage=json.loads(Path(preparation['leaf_coverage']['path']).read_text())
    require(coverage['state']=='PASS exact167 actual-clone header coverage' and all(coverage['model'][k]==preparation['model'][k] for k in ('bytes','sha256')),'actual clone/header coverage required')
    guard=json.loads(Path(preparation['stage_guard']['path']).read_text())
    require(guard['state']=='ROOT-APPROVED fixed512MiB in-driver phase/sum/owned-group guard' and guard['runner']==bind(__file__) and guard['stage']==str(Path(preparation['case_paths']['d-enabled']).parent),'reviewed source-bound stage guard')
    require(guard['RAM_stage_cap_bytes']==512*1024**2 and guard['phase_caps']==dict(raw_total=384*1024**2,raw_per_case=128*1024**2,audit_total=96*1024**2,audit_per_case=32*1024**2,other_total=32*1024**2),'exact guard phase split')
    resources=guard['actual_ROOT_host_resources'];identity=guard['actual_stage_identity']
    require(isinstance(resources,dict) and isinstance(identity,dict),'actual root-host admission fields required')
    stat=stage.stat();require(identity==dict(path=str(stage),device=stat.st_dev,inode=stat.st_ino),'actual owned stage identity')
    require(resources['RAM_free_bytes_at_approval']>=1024**3+512*1024**2 and resources['HOME_free_bytes_at_approval']>=3*1024**3,'root-host approval resource minimum')
    expected={r['key']:r for r in json.loads(schema_path.read_text())['leaves']}
    observed={r['key']:r for r in coverage['leaves']}
    require(len(coverage['leaves'])==167 and set(observed)==set(expected),'all167 distinct actual leaves')
    for key,row in expected.items():
        require(observed[key]['width']==row['width'] and (observed[key]['path']==row['suffix'] or observed[key]['path'].endswith('.'+row['suffix'])),'exact raw leaf/width '+key)
    raw = json.loads(Path(preparation['compiled_sources']['path']).read_text());compiled=raw if 'sources' in raw else {'sources':raw}
    source_bindings(Path(preparation['compiled_sources']['path']))
    for path, record in compiled['sources'].items():
        require(bind(path)['sha256'] == record['sha256'], 'actual compiled RTL input drift')
    program = json.loads(Path(preparation['program']['path']).read_text())
    require(program['max_lines']==program['code_functions']==1792 and program['max_sets']==256 and program['elf']['sha256']=='062a3dd884d64bc1fdf7f0048f312cc5efc84280eb89006c21ef6b60f1f43ed6','fixed reviewed1792fixture')
    for record in program['sources'] + [program['elf'], program['compiler'], program['converter']]:
        require(bind(record['path']) == record, 'program/compiler input drift')
    return program


def check_budget(cohort, preparation):
    fixed=dict(per_trace_cap_bytes=128*1024**2,raw_cohort_cap_bytes=384*1024**2,
               audit_cohort_cap_bytes=96*1024**2,per_audit_cap_bytes=32*1024**2,other_stage_cap_bytes=32*1024**2,native_runtime_ms=1800000,outer_timeout_s=1980,
               preparation_cap_bytes=16*1024**2,HOME_reserve_bytes=3*1024**3,
               RAM_stage_cap_bytes=512*1024**2,RAM_reserve_bytes=1024**3)
    require(all(preparation.get(k)==v for k,v in fixed.items()),'fixed reviewed budgets')
    total=sum(path.stat().st_size for path in cohort.rglob('*') if path.is_file())
    raw=sum(path.stat().st_size for path in cohort.glob('*/trace.fst'))
    audits=sum(path.stat().st_size for path in cohort.glob('*-audit/*') if path.is_file())
    require(total<=fixed['RAM_stage_cap_bytes'] and raw<=fixed['raw_cohort_cap_bytes'] and audits<=fixed['audit_cohort_cap_bytes'] and total-raw-audits<=fixed['other_stage_cap_bytes'],'exact combined/raw/audit/other caps')
    require(all(path.stat().st_size<=fixed['per_trace_cap_bytes'] for path in cohort.glob('*/trace.fst')),'per-case trace cap')
    require(all(sum(p.stat().st_size for p in d.rglob('*') if p.is_file())<=fixed['per_audit_cap_bytes'] for d in cohort.glob('*-audit') if d.is_dir()),'per-case audit cap')
    home=Path(preparation['HOME_preparation_path']);require(home.is_dir(),'explicit HOME preparation')
    require(sum(p.stat().st_size for p in home.rglob('*') if p.is_file())<=fixed['preparation_cap_bytes'],'HOME preparation cap')
    if preparation['storage']=='HOME':
        require(shutil.disk_usage(cohort).free>=fixed['HOME_reserve_bytes']+max(0,fixed['RAM_stage_cap_bytes']-total)+fixed['preparation_cap_bytes'],'HOME budget plus3GiB reserve')
    elif preparation['storage']=='ROOT-host-RAM':
        require(str(cohort.resolve()).startswith('/dev/shm/'),'explicit root-host RAM path only')
        require(total<=fixed['RAM_stage_cap_bytes'] and shutil.disk_usage(cohort).free>=fixed['RAM_reserve_bytes']+fixed['RAM_stage_cap_bytes']-total,'bounded RAM stage plus1GiB reserve')
        require(shutil.disk_usage(home).free>=fixed['HOME_reserve_bytes']+fixed['preparation_cap_bytes'],'HOME3GiB reserve')
    else:raise ValueError('reviewed storage path required')


def owned_run(command,cwd,env,log_path,timeout,limits,guard,allowance):
    """Bound only this fresh process group; never retry or extend execution."""
    guard();start=time.monotonic();process=None;failure=None;saved_handlers={}
    def interrupted(signum,frame):raise InterruptedError('caught signal '+str(signum))
    try:
        for signum in (signal.SIGTERM,signal.SIGINT):
            saved_handlers[signum]=signal.signal(signum,interrupted)
        with log_path.open('wb') as log:
            process=subprocess.Popen(command,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                     start_new_session=True,preexec_fn=limits,bufsize=0)
            with selectors.DefaultSelector() as selected:
                selected.register(process.stdout,selectors.EVENT_READ)
                while selected.get_map():
                    guard()
                    if time.monotonic()-start>=timeout:raise TimeoutError('fixed outer deadline')
                    for key,event in selected.select(timeout=.1):
                        block=os.read(key.fileobj.fileno(),65536)
                        if not block:selected.unregister(key.fileobj);continue
                        require(len(block)<=allowance(),'other-stage log budget (64KiB cleanup reserve)')
                        log.write(block);log.flush()
                process.wait(timeout=max(.001,timeout-(time.monotonic()-start)))
    except BaseException as error:
        failure=repr(error);raise
    finally:
        try:
            for signum in saved_handlers:signal.signal(signum,signal.SIG_IGN)
            if process is not None:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                end=time.monotonic()+5
                process.wait(timeout=max(.001,end-time.monotonic()))
                while True:
                    try:os.killpg(process.pid,0)
                    except ProcessLookupError:break
                    require(time.monotonic()<end,'owned group still live after bounded cleanup')
                    time.sleep(.01)
                receipt=dict(argv=command,owned_pgid=process.pid,returncode=process.returncode,failure=failure,
                             elapsed_seconds=time.monotonic()-start,owned_group_remaining=False,teardown_bound_s=5)
                log_path.with_suffix('.owned.json').write_text(json.dumps(receipt,indent=2)+'\n')
                if process.stdout is not None:process.stdout.close()
        finally:
            for signum,handler in saved_handlers.items():signal.signal(signum,handler)
    return SimpleNamespace(returncode=process.returncode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation', required=True, type=Path)
    parser.add_argument('--role', choices=ORDER, required=True)
    args = parser.parse_args()
    cohort = args.preparation.resolve().parent
    with (cohort / 'acquisition.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        preparation = json.loads(args.preparation.read_text())
        require(preparation['schema'] == 'retained-capacity1792-preparation-v1' and preparation['schedule'] == list(ORDER), 'fixed prepared cohort')
        require(preparation.get('state')=='ROOT-APPROVED fixed1792 simulation only','DRAFT UNLAUNCHABLE until clone/coverage/resources/closure review')
        qualification=preparation['clone_qualification'];require(bind(qualification['path'])==qualification,'closed qualification binding')
        q=json.loads(Path(qualification['path']).read_text());require(q['state']=='PASS-returned-compact-closure-model-source-five-literal-domains-maintained-proofs' and all(q['qualified_model'][k]==preparation['model'][k] for k in ('bytes','sha256')),'exact qualified414 model')
        require(set(q['domains'])=={'core252','observer_and_geometry','SP_strict162','actual_geometry16','capacity167'} and all(r['clean_EOF'] for r in q['domains'].values()),'all five qualified literal domains')
        program = check_inputs(preparation)
        require(source_bindings(Path(preparation['compiled_sources']['path']))==preparation['critical_sources'],'reviewed new-model critical sources')
        previous_gate(cohort, args.role)
        check_budget(cohort, preparation)
        here = Path(__file__).resolve().parent
        source_paths = sorted(path for path in here.iterdir() if path.is_file())
        sources = [bind(path) for path in source_paths]
        frozen = cohort / 'runtime-sources.json'
        if frozen.exists():
            require(json.loads(frozen.read_text()) == sources, 'runtime sources frozen across cohort')
        else:
            require(args.role == ORDER[0], 'first source freeze only before first case')
            frozen.write_text(json.dumps(sources, indent=2) + '\n')
        output = Path(preparation['case_paths'][args.role])
        require(output == cohort / args.role, 'exact admitted path')
        output.mkdir(exist_ok=False)
        case = program['cases'][args.role]
        require(bind(case['nbf']['path']) == case['nbf'], 'exact selected NBF')
        shutil.copyfile(program['elf']['path'], output / 'prog.riscv')
        shutil.copyfile(case['nbf']['path'], output / 'prog.nbf')
        coverage = verify_coverage(output / 'prog.riscv', output / 'prog.nbf', program['symbols']['retained_capacity_config']['address'], int(case['input_word'], 16))
        command = [preparation['model']['path'], '+c_args=prog.nbf 1800000', '+bsg_trace=' + str(output / 'trace.fst')]
        admission = dict(schema='retained-capacity-correctness1792-v1', role=args.role,
                         preparation=bind(args.preparation), runtime_sources=bind(frozen),
                         program=preparation['program'], model=preparation['model'], compiled_sources=preparation['compiled_sources'],
                         elf=bind(output / 'prog.riscv'), nbf=bind(output / 'prog.nbf'), coverage=coverage, command=command,
                         native_runtime_ms=1800000, outer_timeout_s=1980, fst_cap_bytes=128*1024**2, negative_control=args.role == 'd-off')
        (output / 'admission.json').write_text(json.dumps(admission, indent=2) + '\n')
        env = os.environ.copy()
        for name in ('BSG_RUNTIME_PATCH_ADDR', 'BSG_RUNTIME_PATCH_VALUE', 'BSG_TRACE_TIMEOUT_S'):
            env.pop(name, None)
        require(set(preparation['environment'])=={'LD_LIBRARY_PATH'},'qualified runtime environment keys')
        env.update(preparation['environment'])
        def limits():
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_FSIZE, (128*1024**2, 128*1024**2))
        try:
            def allowance():
                total=sum(p.stat().st_size for p in cohort.rglob('*') if p.is_file())
                raw=sum(p.stat().st_size for p in cohort.glob('*/trace.fst'))
                audits=sum(p.stat().st_size for p in cohort.glob('*-audit/*') if p.is_file())
                return preparation['other_stage_cap_bytes']-(total-raw-audits)-65536
            process=owned_run(command,output,env,output/'run.log',1980,limits,
                              lambda:check_budget(cohort,preparation),allowance)
            (output / 'process.json').write_text(json.dumps(dict(returncode=process.returncode)) + '\n')
            checker_path = ROOT / 'testing/check_run.py'
            spec = importlib.util.spec_from_file_location('checker1792', checker_path)
            checker = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(checker)
            text = (output / 'run.log').read_text(errors='replace')
            checker.check_transcript(text, process.returncode)
            marker = '[BSG-PASS] retained capacity checked all full64B payloads completed'
            require(text.count(marker) == 1 and text.index(marker) < checker.CORE_PASS.search(text).start(), 'complete payload/CORE marker')
            rows = re.findall(r'RETAINED_CAPACITY_CONFIG ([^\r\n]+)', text)
            require(len(rows) == 1, 'one exact config')
            config = dict(word.split('=') for word in rows[0].split())
            lane, active = args.role[0], args.role.endswith('enabled')
            expected = dict(version='1', lane=lane, active=str(int(active)), lines='1792', sets='256', max_lines='1792', line_bytes='64',
                            data_base='0x%016x' % program['data_base'], code_base='0x%016x' % program['code_base'], code_stride='192', copy='0')
            require(config == expected and len(rows[0].split()) == len(expected), 'exact actual geometry/role/config')
            fields = re.findall(r'RETAINED_USE_COUNTERS version=1 i_hits=(\d+) d_hits=(\d+) i_published=(\d+) d_published=(\d+) i_write_beats=(\d+) d_write_beats=(\d+) saturating_bits=16 reset=axi_only', text)
            require(len(fields) == 1, 'one exact actual GP0 row')
            values = tuple(map(int, fields[0]))
            rejected = False
            if active:
                primary_counts(lane, 1792, values)
            else:
                require(values == (0, 0, 0, 0, 0, 0), 'negative zero retained events')
                try:
                    primary_counts(lane, 1792, values)
                except ValueError:
                    rejected = True
                require(rejected, 'negative primary gate rejected')
            check_inputs(preparation)
            require([bind(path) for path in source_paths] == sources, 'source drift during execution')
            check_budget(cohort,preparation)
            require(sum(path.stat().st_size for path in cohort.glob('*/trace.fst')) <= 384*1024**2, 'raw cohort cap')
            report = dict(state='PASS primary functional/counter gate; per-address closed trace pending' if active else 'PASS negative checked execution with primary retained-use gate rejected; closed trace pending',
                          role=args.role, config=config, counters=values, primary_use_gate_rejected=rejected, actual_returncode=process.returncode,
                          admission=bind(output / 'admission.json'), files=[bind(output / name) for name in ('prog.riscv', 'prog.nbf', 'run.log', 'process.json', 'trace.fst')],
                          limits='No FPGA/fit/performance result. Per-address full-payload audit and counter corroboration required before next case.')
            (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
        except BaseException as error:
            (output / 'FAIL.json').write_text(json.dumps(dict(state='FAIL STOP cohort; no retry/limit raise/next case', error=repr(error))) + '\n')
            raise
        print(output / 'verification.json')


if __name__ == '__main__':
    main()
