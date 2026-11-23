#!/usr/bin/env python3
"""ROOT-only four unchanged architectural tests on the NEW qualified clone."""
import argparse,importlib.util,json,os,resource,shutil,sys
from pathlib import Path
sys.dont_write_bytecode=True
STD_ROOT=Path(__file__).resolve().parent
CLONE_HELPER=STD_ROOT.parent/'csr768-observation-preparation02-20261123/helper'
SOFTWARE=Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr-unmasked256-regression-preparation-20261122/software')
sys.path.insert(0,str(CLONE_HELPER))
from common import *
from host_flow import ADMISSION,validate,command,loader
TESTS=('mt_context_csr_rebind_test','mt_umode_nonresident_sv39_data_handoff_test','mt_resident_reseed_irq_test','mt_protected_rpc_hardware_test')
INSTALL=Path('/home/coyang/zynq-parrot-linux-research/install')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--worker',required=True,action='store_true');ap.add_argument('--approval-sha',required=True);args=ap.parse_args()
    require(os.getpid()==os.getpgrp(),'one outer owned ROOT phase')
    require(bind(ADMISSION)['sha256']==args.approval_sha,'ROOT frozen clone admission')
    a=json.loads(ADMISSION.read_text());p=validate(a)
    flow=json.loads((STAGE/'flow.json').read_text())
    require(flow['state']=='PASS-one-CSR768-observation-qualification','new clone must qualify before regressions')
    verify(flow['build']);verify(flow['qualification'])
    build=json.loads(Path(flow['build']['path']).read_text());binary=Path(build['binary']['path']);verify(build['binary'])
    require(build['original_model']['sha256']==MODEL_SHA,'not an old hardware model')
    checked=json.loads(Path(flow['qualification']['path']).read_text())
    require(len(checked['domains'])==5 and all(x['literal_bytes_equal'] for x in checked['domains'].values()),'complete five-domain gate')
    proof=json.loads((STD_ROOT/'software-recipe.json').read_text())
    for row in proof['inputs']:verify(row)
    out=STAGE/'architectural-regressions01';out.mkdir();state=dict(state='RUNNING four unchanged tests on new qualified clone',model=bind(binary),scope='architectural/CSR/privilege correctness only',tests=[]);save(out/'session.json',state)
    spec=importlib.util.spec_from_file_location('new_source_protocol_checker',SP/'testing/check_run.py');checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    try:
        for name in TESTS:
            validate(a);folder=out/name;folder.mkdir();elf=folder/'prog.riscv';mem=folder/'prog.mem';nbf=folder/'prog.nbf'
            source=SOFTWARE/(name+'.c')
            argv=[str(INSTALL/'bin/riscv64-unknown-elf-gcc'),'-o',str(elf),str(source),'-O2','-I'+str(SP/'software/include'),'-I'+str(INSTALL/'riscv64-unknown-elf/include'),'--specs='+str(INSTALL/'riscv64-unknown-elf/lib/dramfs.specs'),'--specs='+str(INSTALL/'riscv64-unknown-elf/lib/perch.specs'),'-DNUM_THREADS=2','-DBP_NUM_THREADS=2','-DBP_NUM_CONTEXTS=4','-DBENCH_DIAGNOSTIC=0','-DBENCH_BARRIER=0']
            command(argv,folder,folder/'compile.log',60)
            command([str(INSTALL/'bin/riscv64-unknown-elf-objdump'),'-dr',str(elf)],folder,folder/'disassembly.log',30)
            command([str(INSTALL/'bin/riscv64-unknown-elf-objcopy'),'-O','verilog',str(elf),str(mem)],folder,folder/'objcopy.log',30)
            mem.write_text(mem.read_text().replace('@8','@0'))
            command([sys.executable,'-B',proof['nbf_script']['path'],'--skip_zeros','--config','--debug','--mem',str(mem),'--ncpus','1'],folder,nbf,60)
            require(elf.stat().st_size<4*1024**2 and nbf.stat().st_size<4*1024**2,'small private software artifacts')
            (folder/'loader.log').write_text(loader(binary,p))
            env={k:v for k,v in os.environ.items() if not k.startswith(('BSG_RUNTIME_PATCH_','BSG_TRACE_'))};env.update(p['environment'])
            run=[str(binary),'+c_args=prog.nbf 180000','+bsg_trace='+str(folder/'trace.fst')]
            # All children stay in this outer phase PG for bounded cleanup.
            import subprocess,time
            def limits():resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
            start=time.monotonic()
            with (folder/'run.log').open('wb') as log:
                child=subprocess.Popen(run,cwd=folder,env=env,stdout=log,stderr=subprocess.STDOUT,preexec_fn=limits)
                try:rc=child.wait(timeout=360)
                finally:
                    if child.poll() is None:child.kill();child.wait()
            require((folder/'trace.fst').stat().st_size<16*1024**2,'regression raw trace cap')
            checker.check_transcript((folder/'run.log').read_text(),rc,test=name)
            row=dict(test=name,state='PASS checked architectural return on new qualified model',source=bind(source),elf=bind(elf),nbf=bind(nbf),trace=bind(folder/'trace.fst'),returncode=rc,seconds=time.monotonic()-start,argv=run,log=bind(folder/'run.log'));save(folder/'verification.json',row);state['tests'].append(row);save(out/'session.json',state)
        verify(build['binary']);validate(a);require([x['test'] for x in state['tests']]==list(TESTS),'all four in fixed order')
        state['state']='PASS four unchanged architectural tests on new CSR-unmasked qualified model; no performance claim'
    except BaseException as error:state.update(state='FAIL preserve architectural attempt; no retry',error=repr(error));raise
    finally:save(out/'session.json',state)


if __name__=='__main__':main()
