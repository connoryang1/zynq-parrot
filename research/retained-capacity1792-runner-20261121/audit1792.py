#!/usr/bin/env python3
"""Fixed1792/256 profile of the frozen64-line real-SRAM capacity auditor."""
import argparse
import gzip
import json
from pathlib import Path
import subprocess
import threading
import os
import signal

import frozen
import audit
import generate
from build import ROOT, bind, require

def kill_owned_reader(process):
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass


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
    require(admission['schema'] == 'retained-capacity-correctness1792-v1', 'fixed1792 admission')
    for record in run['files'] + [run['admission']]:
        require(bind(record['path']) == record, 'closed run binding changed')
    program = json.loads(Path(admission['program']['path']).read_text())
    require(bind(admission['program']['path']) == admission['program'], 'program binding')
    source_bindings(Path(admission['compiled_sources']['path']))
    args.out.mkdir(parents=True, exist_ok=False)
    selected = audit.selection()
    selection = args.out / 'selection.tsv'
    selection.write_text(''.join(key + '\t' + suffix + '\n' for key, (suffix, _) in selected.items()))
    fst = args.case / 'trace.fst'
    before = bind(fst)
    validator = Validator(program, run['role'])
    command = [str(args.reader.resolve()), str(fst.resolve()), str(selection.resolve())]
    with (args.out / 'reader.stderr').open('w') as error, gzip.open(args.out / 'selected-events.tsv.gz', 'wt') as saved:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=error, text=True,start_new_session=True)
        timer = threading.Timer(3600,lambda:kill_owned_reader(process))
        timer.daemon = True
        timer.start()
        try:
            def stream():
                for line in process.stdout:
                    require(len(line)<=1024*1024,'bounded selected event line')
                    saved.write(line)
                    require(saved.buffer.fileobj.tell()<=31*1024**2,'32MiB per-case compressed audit cap with1MiB buffering reserve')
                    yield line
            for t, clocks, values in audit.edges(stream(), selected):
                validator.sample(t, clocks, values)
            require(process.wait() == 0, 'reader completion within fixed3600s offline-audit bound')
        except BaseException:
            kill_owned_reader(process)
            process.wait(timeout=5)
            raise
        finally:
            timer.cancel()
            kill_owned_reader(process)
            process.wait(timeout=5)
    result = validator.finish()
    require(sum(p.stat().st_size for p in args.out.parent.glob('*-audit/*') if p.is_file())<=96*1024**2,'96MiB audit cohort output cap')
    require(bind(fst) == before, 'closed FST unchanged')
    result['bindings'] = dict(fst=before, run=bind(args.case / 'verification.json'), admission=bind(args.case / 'admission.json'),
                              program=bind(admission['program']['path']), auditor=bind(__file__), inherited_auditor=bind(audit.__file__),
                              reader=bind(args.reader), selection=bind(selection), events=bind(args.out / 'selected-events.tsv.gz'))
    output=json.dumps(result,indent=2)+'\n'
    require(sum(p.stat().st_size for p in args.out.rglob('*') if p.is_file())+len(output.encode())<=32*1024**2,'final32MiB per-case audit cap')
    require(sum(p.stat().st_size for p in args.out.parent.glob('*-audit/*') if p.is_file())+len(output.encode())<=96*1024**2,'final96MiB audit cohort cap')
    (args.out / 'verification.json').write_text(output)
    print(args.out / 'verification.json')


if __name__ == '__main__':
    main()
