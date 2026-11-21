#!/usr/bin/env python3
"""Future complete1792 cohort native phase; externally anchored admission required."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import shutil
import contract as c

bind,require=c.bind,c.require
ROOT=c.native.ROOT
primary_counts=c.native.primary_counts
verify_coverage=c.native.verify_coverage
owned_run=c.native.owned_run
check_budget=c.check_budget


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation',required=True,type=Path)
    parser.add_argument('--preparation-sha256',required=True)
    parser.add_argument('--role',choices=c.ORDER,required=True)
    parser.add_argument('--prior-audit-sha256',action='append',default=[])
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    require(args.execute,'default offline; explicit ROOT admission and --execute required')
    preparation,program=c.load(args.preparation,args.preparation_sha256)
    cohort=Path(preparation['stage'])
    require(len(args.prior_audit_sha256)==c.ORDER.index(args.role),'all and only prior closed audit SHA anchors')
    with (cohort/'acquisition.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for previous,sha in zip(c.ORDER,args.prior_audit_sha256):
            c.verify_audit(cohort,previous,preparation,args.preparation,sha)
        check_budget(cohort,preparation)
        sources=c.runtime_sources()
        frozen=cohort/'runtime-sources.json'
        if frozen.exists():require(json.loads(frozen.read_text())==sources,'runtime frozen across three cases')
        else:
            require(args.role==c.ORDER[0],'source freeze only before first case')
            c.archive.write_json(frozen,sources)
        output=cohort/args.role
        output.mkdir(exist_ok=False)
        case = program['cases'][args.role]
        require(bind(case['nbf']['path']) == case['nbf'], 'exact selected NBF')
        shutil.copyfile(program['elf']['path'], output / 'prog.riscv')
        shutil.copyfile(case['nbf']['path'], output / 'prog.nbf')
        coverage = verify_coverage(output / 'prog.riscv', output / 'prog.nbf', program['symbols']['retained_capacity_config']['address'], int(case['input_word'], 16))
        command = [preparation['model']['path'], '+c_args=prog.nbf 1800000', '+bsg_trace=' + str(output / 'trace.fst')]
        admission = dict(schema='retained-capacity1792-stream-native-v1', role=args.role,
                         preparation=bind(args.preparation), runtime_sources=bind(frozen),
                         program=preparation['program'], model=preparation['model'], compiled_sources=preparation['compiled_sources'],
                         elf=bind(output / 'prog.riscv'), nbf=bind(output / 'prog.nbf'), coverage=coverage, command=command,
                         native_runtime_ms=1800000, outer_timeout_s=1980, fst_cap_bytes=128*1024**2, negative_control=args.role == 'd-off', reader=preparation['reader'])
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
                audits=sum(p.stat().st_size for d in cohort.glob('*-audit') for p in d.rglob('*') if p.is_file())
                return c.CAPS['other_total']-(total-raw-audits)-65536
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
            c.load(args.preparation,args.preparation_sha256)
            require(c.runtime_sources() == sources, 'source drift during execution')
            check_budget(cohort,preparation)
            require(sum(path.stat().st_size for path in cohort.glob('*/trace.fst')) <= 384*1024**2, 'raw cohort cap')
            report = dict(state='PASS primary functional/counter gate; per-address closed trace pending' if active else 'PASS negative checked execution with primary retained-use gate rejected; closed trace pending',
                          role=args.role, config=config, counters=values, primary_use_gate_rejected=rejected, actual_returncode=process.returncode,
                          admission=bind(output / 'admission.json'), files=[bind(output / name) for name in ('prog.riscv', 'prog.nbf', 'run.log', 'process.json', 'trace.fst')],
                          limits='No FPGA/fit/performance result. Per-address full-payload audit and counter corroboration required before next case.')
            (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
            check_budget(cohort,preparation)
        except BaseException as error:
            if (output/'verification.json').exists():(output/'verification.json').rename(output/'FAILED-verification.json')
            (output / 'FAIL.json').write_text(json.dumps(dict(state='FAIL STOP cohort; no retry/limit raise/next case', error=repr(error))) + '\n')
            raise
        print(output / 'verification.json')


if __name__=='__main__':main()
