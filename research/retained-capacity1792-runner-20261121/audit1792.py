#!/usr/bin/env python3
"""Fixed1792/256 profile of the frozen64-line real-SRAM capacity auditor."""
import argparse
import fcntl
import gzip
import json
from pathlib import Path
import subprocess
import threading
import os
import signal
import selectors
import time
from contextlib import closing

import frozen
import audit
import generate
import budget1792
from build import ROOT, bind, require
from budget1792 import check_budget,resource_phase

class AuditInterrupted(RuntimeError):pass

def kill_owned_reader(process):
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass

def check_admitted_reader(path,preparation,admission):
    require(bind(path)==preparation['reader']==admission['reader'],'exact admitted FST reader path/bytes/SHA')

def guarded_reader(command,error_path,guard,timeout=3600):
    """Guard idle readers independently of data parsing; own exactly one PG."""
    guard();start=time.monotonic();process=None;watch=None;stop=threading.Event();errors=[];handlers={};failure=None;polls=[];late_error=None
    def interrupted(signum,frame):raise AuditInterrupted('audit caught signal '+str(signum))
    def monitor():
        last=time.monotonic()
        while not stop.wait(.25):
            try:
                now=time.monotonic();polls.append(now-last);require(now-last<=1,'audit guard poll gap over1s');last=now
                guard()
                require(now-start<timeout,'audit fixed reader deadline')
            except BaseException as error:
                errors.append(error);kill_owned_reader(process);return
    try:
        for sig in (signal.SIGTERM,signal.SIGINT):handlers[sig]=signal.signal(sig,interrupted)
        with error_path.open('wb') as error:
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=error,start_new_session=True,bufsize=0)
            watch=threading.Thread(target=monitor,daemon=True);watch.start();pending=b''
            with selectors.DefaultSelector() as selected:
                selected.register(process.stdout,selectors.EVENT_READ)
                while selected.get_map():
                    if errors:raise errors[0]
                    require(time.monotonic()-start<timeout,'audit fixed reader deadline')
                    for key,event in selected.select(.1):
                        chunk=os.read(key.fileobj.fileno(),65536)
                        if not chunk:selected.unregister(key.fileobj);continue
                        pending+=chunk
                        while b'\n' in pending:
                            line,pending=pending.split(b'\n',1);require(len(line)<1024*1024,'bounded selected event line')
                            if errors:raise errors[0]
                            yield line.decode('utf-8')+'\n'
                        require(len(pending)<1024*1024,'bounded pending selected line')
                if errors:raise errors[0]
                if pending:yield pending.decode('utf-8')
                require(process.wait(timeout=max(.001,timeout-(time.monotonic()-start)))==0,'reader complete0')
                guard()
    except BaseException as error:
        failure=repr(error);raise
    finally:
        try:
            for sig in handlers:signal.signal(sig,signal.SIG_IGN)
            stop.set();end=time.monotonic()+5
            if process is not None:
                kill_owned_reader(process);process.wait(timeout=max(.001,end-time.monotonic()))
                if watch is not None:watch.join(timeout=max(.001,end-time.monotonic()));require(not watch.is_alive(),'audit guard thread did not stop')
                while True:
                    try:os.killpg(process.pid,0)
                    except ProcessLookupError:break
                    require(time.monotonic()<end,'reader group remains after5s cleanup');time.sleep(.01)
                if process.stdout is not None:process.stdout.close()
                if errors and failure is None:late_error=errors[0];failure=repr(late_error)
                receipt=dict(argv=command,owned_pgid=process.pid,returncode=process.returncode,failure=failure,
                             owned_group_remaining=False,guard_interval_s=.25,max_observed_poll_gap_s=max(polls,default=0),teardown_bound_s=5)
                error_path.with_suffix('.owned.json').write_text(json.dumps(receipt,indent=2)+'\n')
                if late_error is not None:raise late_error
        finally:
            for sig,handler in handlers.items():signal.signal(sig,handler)


def source_bindings(source_list):
    """Bind actual new-model critical inputs; do not require historical RTL."""
    raw=json.loads(Path(source_list).read_text());compiled=raw.get('sources',raw);result=[]
    for suffix in ('bp_top/src/v/bp_unicore_lite.sv','bp_me/src/v/cce/bp_uce.sv',
                   'bp_common/src/v/bp_retained_line_store.sv','bp_fe/src/v/bp_fe_icache.sv',
                   'bp_be/src/v/bp_be_dcache/bp_be_dcache.sv'):
        matches=[record for path,record in compiled.items() if path.endswith('/import/black-parrot/'+suffix)]
        require(len(matches)==1,'one consumed critical source: '+suffix)
        actual=bind(matches[0]['path']);require(actual==matches[0],'actual new-model RTL identity: '+suffix);result.append(actual)
    return result


class Validator(audit.Validator):
    def __init__(self, program, role):
        require(program['max_lines'] == 1792 and program['max_sets'] == 256, 'fixed1792/256 generated bounds')
        super().__init__(program, role)
        self.lines, self.sets = 1792, 256
        self.targets = {}
        for slot in range(self.lines):
            index = (slot & ~255) + ((slot * 0xaaaaaaaaaaaaaaab) & 255)
            addr = program['code_base'] + 192 * index if self.lane == 'i' else program['data_base'] + 64 * slot
            self.targets[addr] = dict(slot=slot, index=index,
                                     words=generate.code_words(index) if self.lane == 'i' else generate.data_words(slot))

    def finish(self):
        result = super().finish()
        result['sets'] = self.sets
        result['limits'] = ('Only actual1792/1792 retained partitions,256 sets; ordinary L1 remains64 sets/8 ways. '
                            'Physical aggregate counters are weaker than per-address model proof. No FPGA/fit/speedup claim.')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('case', 'reader', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    run = json.loads((args.case / 'verification.json').read_text())
    admission = json.loads((args.case / 'admission.json').read_text())
    require(bind(admission['preparation']['path'])==admission['preparation'],'exact admitted preparation')
    preparation=json.loads(Path(admission['preparation']['path']).read_text())
    cohort=args.case.resolve().parent;handlers={}
    def interrupted(signum,frame):raise AuditInterrupted('audit phase caught signal '+str(signum))
    try:
        for sig in (signal.SIGTERM,signal.SIGINT):handlers[sig]=signal.signal(sig,interrupted)
        with (cohort/'acquisition.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:
                with resource_phase(lambda:check_budget(cohort,preparation)) as guard:
                    audit_case(args,run,admission,preparation,guard)
            except BaseException:
                for sig in handlers:signal.signal(sig,signal.SIG_IGN)
                proof=args.out/'verification.json'
                if getattr(args,'owned_output',False) and proof.exists():proof.rename(args.out/'FAILED-verification.json')
                raise
    finally:
        for sig,handler in handlers.items():signal.signal(sig,handler)


def audit_case(args,run,admission,preparation,guard):
    require(admission['schema'] == 'retained-capacity-correctness1792-v1', 'fixed1792 admission')
    for record in run['files'] + [run['admission']]:
        require(bind(record['path']) == record, 'closed run binding changed')
    require(bind(admission['preparation']['path'])==admission['preparation'],'exact admitted preparation')
    require(preparation['state']=='ROOT-APPROVED fixed1792 simulation only','audit requires approved preparation')
    check_admitted_reader(args.reader,preparation,admission)
    require(bind(admission['runtime_sources']['path'])==admission['runtime_sources'],'native runtime source snapshot')
    runtime_sources=json.loads(Path(admission['runtime_sources']['path']).read_text())
    require(bind(__file__) in runtime_sources,'executed auditor belongs to frozen runtime sources')
    for record in runtime_sources:require(bind(record['path'])==record,'runtime/audit source drift')
    cohort=args.case.resolve().parent
    require(args.out.resolve()==cohort/(run['role']+'-audit'),'exact admitted audit output')
    guard()
    program = json.loads(Path(admission['program']['path']).read_text())
    require(bind(admission['program']['path']) == admission['program'], 'program binding')
    source_bindings(Path(admission['compiled_sources']['path']))
    args.out.mkdir(parents=True, exist_ok=False)
    args.owned_output=True
    selected = audit.selection()
    selection = args.out / 'selection.tsv'
    selection.write_text(''.join(key + '\t' + suffix + '\n' for key, (suffix, _) in selected.items()))
    fst = args.case / 'trace.fst'
    before = bind(fst)
    validator = Validator(program, run['role'])
    command = [str(args.reader.resolve()), str(fst.resolve()), str(selection.resolve())]
    with gzip.open(args.out / 'selected-events.tsv.gz', 'wt') as saved:
        with closing(guarded_reader(command,args.out/'reader.stderr',guard)) as lines:
            def stream():
                for line in lines:
                    require(len(line)<=1024*1024,'bounded selected event line')
                    saved.write(line)
                    require(saved.buffer.fileobj.tell()<=31*1024**2,'32MiB per-case compressed audit cap with1MiB buffering reserve')
                    yield line
            for t, clocks, values in audit.edges(stream(), selected):
                validator.sample(t, clocks, values)
    guard()
    result = validator.finish()
    require(sum(p.stat().st_size for p in args.out.parent.glob('*-audit/*') if p.is_file())<=96*1024**2,'96MiB audit cohort output cap')
    require(bind(fst) == before, 'closed FST unchanged')
    require(bind(args.reader)==preparation['reader'],'reader immutable after audit')
    frozen.verify()
    for record in runtime_sources:require(bind(record['path'])==record,'runtime/audit source changed during audit')
    result['bindings'] = dict(fst=before, run=bind(args.case / 'verification.json'), admission=bind(args.case / 'admission.json'),
                              program=bind(admission['program']['path']), auditor=bind(__file__), inherited_auditor=bind(audit.__file__),
                              reader=bind(args.reader), selection=bind(selection), events=bind(args.out / 'selected-events.tsv.gz'),
                              reader_lifecycle=bind(args.out/'reader.owned.json'),budget_helper=bind(budget1792.__file__),
                              runtime_sources=admission['runtime_sources'],preparation=admission['preparation'])
    output=json.dumps(result,indent=2)+'\n'
    require(sum(p.stat().st_size for p in args.out.rglob('*') if p.is_file())+len(output.encode())<=32*1024**2,'final32MiB per-case audit cap')
    require(sum(p.stat().st_size for p in args.out.parent.glob('*-audit/*') if p.is_file())+len(output.encode())<=96*1024**2,'final96MiB audit cohort cap')
    (args.out / 'verification.json').write_text(output)
    guard()
    print(args.out / 'verification.json')


if __name__ == '__main__':
    main()
