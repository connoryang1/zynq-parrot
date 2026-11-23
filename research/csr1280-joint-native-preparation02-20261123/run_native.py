#!/usr/bin/env python3
"""One separately funded joint1280 native case, after all three single-role audits."""
import argparse,fcntl,importlib.util,json,os,re,resource,shutil,signal,sys
from pathlib import Path
sys.dont_write_bytecode=True
import contract as c


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--preparation',type=Path,required=True);ap.add_argument('--preparation-sha256',required=True);ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    c.require(args.execute,'SOURCE ONLY default; fresh ROOT authority required')
    p,program=c.load(args.preparation,args.preparation_sha256);stage=c.BASE;out=stage/'joint';owned=False
    handlers={s:signal.getsignal(s)for s in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP)}
    def interrupted(s,f):raise RuntimeError('joint native caught signal '+str(s))
    for s in handlers:signal.signal(s,interrupted)
    try:
        with (stage/'acquisition.lock').open('a')as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);c.check_budget(stage,p)
            c.archive.write_json(stage/'runtime-sources.json',p['runtime_sources']);out.mkdir(exist_ok=False);owned=True
            with c.resource_phase(stage,p,out,out/'resource-phase.json')as guard:
                shutil.copyfile(program['elf']['path'],out/'prog.riscv');shutil.copyfile(program['nbf']['path'],out/'prog.nbf')
                coverage=c.native.verify_coverage(out/'prog.riscv',out/'prog.nbf',program['symbols']['retained_joint_capacity_config']['address'],0xc641000000000000)
                command=[p['model']['path'],'+c_args=prog.nbf 1800000','+bsg_trace='+str(out/'trace.fst')]
                ad=dict(schema='csr1280-joint-capacity-stream-native-v1',role='joint',preparation=c.bind(args.preparation),runtime_sources=c.bind(stage/'runtime-sources.json'),program=p['program'],model=p['model'],compiled_sources=p['compiled_sources'],reader=p['reader'],elf=c.bind(out/'prog.riscv'),nbf=c.bind(out/'prog.nbf'),coverage=coverage,command=command,native_runtime_ms=1800000,outer_timeout_s=1980,fst_cap_bytes=c.CAPS['raw_per_case'])
                c.archive.write_json(out/'admission.json',ad)
                env=dict(os.environ)
                for name in ('BSG_RUNTIME_PATCH_ADDR','BSG_RUNTIME_PATCH_VALUE','BSG_TRACE_TIMEOUT_S'):env.pop(name,None)
                c.require(set(p['environment'])=={'LD_LIBRARY_PATH'},'qualified runtime environment only');env.update(p['environment'])
                def limits():
                    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(c.CAPS['raw_per_case'],)*2)
                def allowance():return c.CAPS['other_total']-sum(f.stat().st_size for f in stage.rglob('*')if f.is_file()and f.name!='trace.fst'and 'joint-audit'not in f.parts)-65536
                process=c.native.owned_run(command,out,env,out/'run.log',1980,limits,guard,allowance)
                c.archive.write_json(out/'process.json',dict(returncode=process.returncode))
                spec=importlib.util.spec_from_file_location('actual1280_joint_run_checker',c.SOURCE/'testing/check_run.py');checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
                text=(out/'run.log').read_text(errors='replace');checker.check_transcript(text,process.returncode)
                marker='[BSG-PASS] retained JOINT capacity checked both full64B payloads completed'
                c.require(text.count(marker)==1 and text.index(marker)<checker.CORE_PASS.search(text).start(),'full joint guest before CORE PASS')
                rows=re.findall(r'RETAINED_JOINT_CAPACITY_CONFIG ([^\r\n]+)',text);c.require(len(rows)==1,'one exact joint config')
                config=dict(word.split('=')for word in rows[0].split())
                expected=dict(version='1',i_lines='1280',d_lines='1280',sets='256',line_bytes='64',data_base='0x%016x'%program['data_base'],code_base='0x%016x'%program['code_base'],code_stride='192',control='3',copy='0')
                c.require(config==expected and len(rows[0].split())==len(expected),'actual joint both-lane geometry/source-control')
                fields=re.findall(r'RETAINED_USE_COUNTERS version=1 i_hits=(\d+) d_hits=(\d+) i_published=(\d+) d_published=(\d+) i_write_beats=(\d+) d_write_beats=(\d+) saturating_bits=16 reset=axi_only',text)
                c.require(len(fields)==1,'one six-word actual counter row');values=list(map(int,fields[0]));c.require(values==c.counters_for('joint'),'exact nonsaturated actual both-lane counts')
                c.load(args.preparation,args.preparation_sha256);c.check_budget(stage,p)
                c.archive.write_json(out/'verification.json',dict(state='PASS joint1280 checked execution/primary counters; full167 per-address audit pending',role='joint',config=config,counters=values,actual_returncode=process.returncode,admission=c.bind(out/'admission.json'),files=[c.bind(out/name)for name in ('prog.riscv','prog.nbf','run.log','process.json','trace.fst','run.owned.json')],limits='Independent full167 joint per-address/GP0 audit still pending. Simulation only; no FPGA/fit/application/performance inference.'))
            proof=json.loads((out/'verification.json').read_text());proof.update(resource_phase=c.bind(out/'resource-phase.json'),sealed_inputs=c.bind(out/'sealed-exit.json'));c.archive.write_json(out/'verification.json',proof)
            c.check_native(stage,p,args.preparation,c.bind(out/'verification.json')['sha256']);c.check_budget(stage,p);print(out/'verification.json')
    except BaseException as error:
        for s in handlers:signal.signal(s,signal.SIG_IGN)
        if owned:
            if(out/'verification.json').exists():(out/'verification.json').rename(out/'FAILED-verification.json')
            c.archive.write_json(out/'FAIL.json',dict(state='FAIL STOP joint; no retry/limit raise',error=repr(error)))
        raise
    finally:
        for s,h in handlers.items():signal.signal(s,h)

if __name__=='__main__':main()
