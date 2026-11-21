#!/usr/bin/env python3
"""Fixed1280/256 profile of the frozen64-line real-SRAM capacity auditor."""
import argparse
import gzip
import json
from pathlib import Path
import subprocess
import threading

import audit
import generate
from build import ROOT, bind, require


def source_bindings(source_list):
    """Require the consumed model's paths and byte-identical local audit sources."""
    compiled = json.loads(Path(source_list).read_text())['sources']
    result = []
    for suffix in ('bp_top/src/v/bp_unicore_lite.sv', 'bp_me/src/v/cce/bp_uce.sv',
                   'bp_common/src/v/bp_retained_line_store.sv', 'bp_fe/src/v/bp_fe_icache.sv',
                   'bp_be/src/v/bp_be_dcache/bp_be_dcache.sv'):
        matches = [record for path, record in compiled.items() if path.endswith('/import/black-parrot/' + suffix)]
        require(len(matches) == 1, 'one exact consumed critical source: ' + suffix)
        actual = bind(matches[0]['path'])
        local = bind(ROOT / 'import/black-parrot' / suffix)
        require(actual['sha256'] == matches[0]['sha256'] == local['sha256'] and actual['bytes'] == local['bytes'],
                'actual model/local critical RTL identity: ' + suffix)
        result.append(actual)
    return result


class Validator(audit.Validator):
    def __init__(self, program, role):
        require(program['max_lines'] == 1280 and program['max_sets'] == 256, 'fixed1280/256 generated bounds')
        super().__init__(program, role)
        self.lines, self.sets = 1280, 256
        self.targets = {}
        for slot in range(self.lines):
            index = (slot & ~255) + ((slot * 0xaaaaaaaaaaaaaaab) & 255)
            addr = program['code_base'] + 192 * index if self.lane == 'i' else program['data_base'] + 64 * slot
            self.targets[addr] = dict(slot=slot, index=index,
                                     words=generate.code_words(index) if self.lane == 'i' else generate.data_words(slot))

    def finish(self):
        result = super().finish()
        result['sets'] = self.sets
        result['limits'] = ('Only actual1280/1280 retained partitions,256 sets; ordinary L1 remains64 sets/8 ways. '
                            'Physical aggregate counters are weaker than per-address model proof. No FPGA/fit/speedup claim.')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('case', 'reader', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    run = json.loads((args.case / 'verification.json').read_text())
    admission = json.loads((args.case / 'admission.json').read_text())
    require(admission['schema'] == 'retained-capacity-correctness1280-v1', 'fixed1280 admission')
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
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=error, text=True)
        timer = threading.Timer(3600, process.kill)
        timer.daemon = True
        timer.start()
        try:
            def stream():
                for line in process.stdout:
                    saved.write(line)
                    yield line
            for t, clocks, values in audit.edges(stream(), selected):
                validator.sample(t, clocks, values)
            require(process.wait() == 0, 'reader completion within fixed3600s offline-audit bound')
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            timer.cancel()
    result = validator.finish()
    require(bind(fst) == before, 'closed FST unchanged')
    result['bindings'] = dict(fst=before, run=bind(args.case / 'verification.json'), admission=bind(args.case / 'admission.json'),
                              program=bind(admission['program']['path']), auditor=bind(__file__), inherited_auditor=bind(audit.__file__),
                              reader=bind(args.reader), selection=bind(selection), events=bind(args.out / 'selected-events.tsv.gz'))
    (args.out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(args.out / 'verification.json')


if __name__ == '__main__':
    main()
