#!/usr/bin/env python3
"""Directed full-payload checks plus per-evaluation original/private RAM equivalence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
BP = ROOT / 'import/black-parrot'
RTL = BP / 'bp_common/src/v/bp_retained_line_store.sv'
GOLDEN = ROOT / 'testing/rtl/retained-line-store'
REFERENCE = 'e10992a3eea3ba2ef6ae3ccb42ff5e8c658286a8'
GEOMETRIES = [(0,0),(64,0),(0,64),(64,64),(128,128),(256,256),
              (512,512),(1024,1024),(1280,1280),(1320,1320),(1536,1536),(93,131)]


def artifact(path):
    path = Path(path).resolve()
    return dict(path=str(path), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def file_limit():
    resource.setrlimit(resource.RLIMIT_FSIZE, (64*1024*1024,)*2)


def generate(output):
    old = subprocess.check_output(['git','show',REFERENCE+':bp_common/src/v/bp_retained_line_store.sv'], cwd=BP).decode()
    new = RTL.read_text()
    tail = '    localparam int ways_lp'
    assert old[old.index(tail):] == new[new.index(tail):], 'FSM/policy/assertion tail changed'
    reference = old.replace('module bp_retained_line_store', 'module bp_retained_line_store_before', 1)
    assert reference != old
    (output/'bp_retained_line_store_before.sv').write_text(reference)
    wrapper = (GOLDEN/'retained_line_store_wrapper.sv').read_text()
    wrapper = wrapper.replace('   );', '   , output logic equivalence_mismatch_o\n   );', 1)
    start = wrapper.index('  bp_retained_line_store\n')
    end = wrapper.index('  assign debug_data_v_o')
    instance = wrapper[start:end].replace('bp_retained_line_store\n', 'bp_retained_line_store_before\n', 1).replace(')) dut\n', ')) reference\n', 1)
    widths = {'lookup_ready_o':'[1:0]', 'resp_v_o':'[1:0]', 'resp_hit_o':'[1:0]',
              'resp_data0_o':'[511:0]', 'resp_data1_o':'[511:0]', 'insert_ready_o':'[1:0]',
              'insert_done_o':'[1:0]', 'insert_published_o':'[1:0]', 'busy_o':'[1:0]', 'epoch_wrap_o':'[1:0]'}
    declarations = ''
    for name,width in widths.items():
        declarations += f'  logic {width} ref_{name};\n'
        # Port identifiers remain unchanged; only the connected expression changes.
        instance = instance.replace('('+name+')', '(ref_'+name+')')
    instance = instance.replace('{resp_data1_o,resp_data0_o}', '{ref_resp_data1_o,ref_resp_data0_o}')
    compares = [f'({name} != ref_{name})' for name in widths if not name.startswith('resp_data')]
    compares += [f'(resp_v_o[{lane}] && resp_hit_o[{lane}] && (resp_data{lane}_o != ref_resp_data{lane}_o))' for lane in range(2)]
    # Check unchanged logical global RAM access timing/address/payload as well as clients.
    compares += [f'(dut.{name} != reference.{name})' for name in ('tag_v','tag_w','data_v','data_w')]
    for lane in range(2):
        for kind in ('tag','data'):
            compares += [f'(dut.{kind}_v[{lane}] && (dut.{kind}_addr[{lane}] != reference.{kind}_addr[{lane}]))',
                         f'(dut.{kind}_v[{lane}] && dut.{kind}_w[{lane}] && (dut.{kind}_wdata[{lane}] != reference.{kind}_wdata[{lane}]))']
    wrapper = wrapper.replace('endmodule', declarations+instance+'  assign equivalence_mismatch_o =\n    '+'\n    | '.join(compares)+';\nendmodule')
    (output/'retained_line_store_wrapper.sv').write_text(wrapper)
    driver = (GOLDEN/'driver.cpp').read_text()
    assert driver.count('d->eval();') == 3
    driver = driver.replace('uint64_t ticks=0;', 'uint64_t ticks=0, equivalence_samples=0;')
    driver = driver.replace('d->eval();', 'd->eval();++equivalence_samples;require(!d->equivalence_mismatch_o,"original/private RAM cycle mismatch");')
    driver = driver.replace('sim.checks();', 'sim.checks();std::printf("RETAINED_EQUIVALENCE_PASS samples=%llu\\n",(unsigned long long)sim.equivalence_samples);')
    (output/'driver.cpp').write_text(driver)
    return dict(reference_revision=REFERENCE, fsm_policy_assertion_tail_byte_identical=True,
                comparison='Every settled eval: all client controls, valid-hit 512-bit data, logical RAM enables/write enables and enabled global addresses/write data; existing directed assertions/checks retained.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verilator', type=Path, required=True)
    parser.add_argument('--geometry', nargs=2, type=int, action='append')
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    paths = [RTL, GOLDEN/'driver.cpp', GOLDEN/'retained_line_store_wrapper.sv', Path(__file__)]
    record = dict(state='running', scope='Component functional and cycle equivalence only; no synthesis, fit, full-core, physical or performance claim.',
                  sources=[artifact(p) for p in paths], commands=[], cases=[])
    def run(label, argv, cwd, timeout):
        log = output/(label+'.log')
        item = dict(label=label, argv=list(map(str,argv)), cwd=str(cwd), timeout_seconds=timeout)
        record['commands'].append(item); started=time.monotonic()
        try:
            with log.open('wb') as stream:
                result=subprocess.run(item['argv'],cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,
                                      timeout=timeout,preexec_fn=file_limit)
            item['returncode']=result.returncode
            if result.returncode: raise RuntimeError(label+' failed')
        finally:
            item.update(elapsed_seconds=time.monotonic()-started, log=artifact(log))
    try:
        assert shutil.disk_usage(output).free > 1024**3, 'less than 1 GiB free'
        source=output/'source';source.mkdir();record['generation']=generate(source)
        for p in paths: shutil.copyfile(p,source/('input-'+p.name))
        record['generated_sources']=[artifact(p) for p in sorted(source.iterdir())]
        run('version',[args.verilator,'--version'],output,10)
        for i,d in args.geometry or GEOMETRIES:
            assert min(i,d)>=0 and max(i,d)<=16384
            label=f'i{i}-d{d}';case=output/label;case.mkdir()
            run(label+'-build',[args.verilator,'--cc','--exe','--build','--trace-fst','--assert','-Wall',
                '--top-module','retained_line_store_wrapper',f'-GI_LINES={i}',f'-GD_LINES={d}',
                '-CFLAGS','-std=c++14','-j','2','--Mdir',case/'obj',RTL,
                source/'bp_retained_line_store_before.sv',source/'retained_line_store_wrapper.sv',source/'driver.cpp'],output,300)
            executable=case/'obj/Vretained_line_store_wrapper'
            for mode in ('inverted','different-periods'):
                runtime=case/mode;runtime.mkdir()
                command=label+'-'+mode
                run(command,[executable]+([mode] if mode=='different-periods' else []),runtime,120)
                text=(output/(command+'.log')).read_text()
                assert text.count(f'RETAINED_LINE_STORE_PASS I={i} D={d} clock={mode}')==1
                assert text.count('RETAINED_TEST_EXIT_CLEAN')==1
                samples=re.findall(r'^RETAINED_EQUIVALENCE_PASS samples=(\d+)$',text,re.M)
                assert len(samples)==1 and int(samples[0])>0
                rows=re.findall(r'^RETAINED_COUNTS lane=(\d) queries=(\d+) responses=(\d+) inserts=(\d+) terminals=(\d+) published=(\d+)$',text,re.M)
                assert len(rows)==2 and {r[0] for r in rows}=={'0','1'}
                assert all(r[1]==r[2] and r[3]==r[4] for r in rows)
                record['cases'].append(dict(i_lines=i,d_lines=d,clock_mode=mode,samples=int(samples[0]),counts=rows,
                    executable=artifact(executable),fst=artifact(runtime/'retained-line-store.fst')))
                print(label,mode,'PASS',samples[0],flush=True)
        assert record['sources']==[artifact(p) for p in paths], 'input drift'
        record['state']='PASS-private-single-port-directed-cycle-equivalence'
    except BaseException as error:
        record.update(state='FAIL-preserved-no-result',error=repr(error));raise
    finally:
        (output/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
        print(output,record['state'],flush=True)


if __name__=='__main__': main()
