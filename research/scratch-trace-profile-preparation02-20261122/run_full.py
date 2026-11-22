#!/usr/bin/env python3
"""New scratch/trace0 fullcore gate; default offline, requires reviewed selection."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import shutil
import sys
import time
sys.dont_write_bytecode=True
import materialize as source
import budget
import dryrun
sys.path.insert(0,str(source.PREVIOUS))
import software_owned_v2 as owned

HERE=Path(__file__).resolve().parent
ROOT=source.SOURCE
OLD=Path('/home/coyang/zynq-parrot-retained-dense')
INSTALL=Path('/home/coyang/zynq-parrot-linux-research/install')
READER=Path('/home/coyang/fpga-artifacts/context-resume/retained-use-observation-20261121/fst-reader/fst_events')
READER_SHA='a9227fe2368ab376b7700a08e044b81c18261432dadeb89e8baeafab021f7541'
FIXTURE=Path('/home/coyang/zynq-parrot-linux-fit1280/research/retained-control-abi-20261121/advisory-fixture-cold08/manifest.json')
FST_CAP=150*1024**2
STRICT=ROOT/'testing/rtl/retained-advisory-trace/validate.py'
COUNTER=OLD/'research/retained-use-observation-20261121/verify_counters.py'
GENERATED_GEOMETRY=OLD/'research/retained-maintenance-acyclic-20261121/bind_geometry.py'


def require(ok,message):
    if not ok:raise ValueError(message)
def bind(path):return source.bind(path)
def full_bind(path):
    r=bind(path);s=Path(path).stat();r.update(inode=s.st_ino,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns);return r
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def validate_selection(path,sha):
    require(bind(path)['sha256']==sha,'external ROOT selection SHA')
    a=json.loads(Path(path).read_text())
    require(a['state']=='ROOT-APPROVED scratch-only trace0 fullcore selection','capacity/software selection remains pending')
    require(a['schema']=='scratch-trace0-fullcore-v1' and a['BP']==source.BP and a['trace']==0,'exact scratch-only feature/profile')
    require(isinstance(a['lines'],int) and not isinstance(a['lines'],bool) and 1<=a['lines']<=65535,'explicit balanced capacity selection')
    require(a['geometry']==dict(sets=256,epoch=8,line_bytes=64,l1_i_bytes=32768,l1_d_bytes=32768,l2_bytes=16384,resident=2,logical=4,aclk_mhz=20,delay=0),'unchanged actual ordinary topology')
    require(a['workers']==8 and a['cache']=='off','8workers/cacheoff')
    prep=json.loads(Path(a['source_preparation']['path']).read_text());require(bind(a['source_preparation']['path'])==a['source_preparation'],'source preparation binding')
    require(prep['state']=='PASS exact scratch-only source prepared; no compiler/model/reader; final capacity pending','exact prepared source lineage')
    for row in prep['files']:require(bind(row['path'])==row,'prepared source changed')
    require(source.git(ROOT,'rev-parse','HEAD').decode().strip()==a['TOP'],'exact selected actual TOP')
    for row in prep['repositories']:
        require(source.git(Path(row['path']),'rev-parse','HEAD').decode().strip()==row['head'] and not source.git(Path(row['path']),'status','--porcelain','--untracked-files=normal').decode(),'all real source repositories clean and pinned')
    design=(ROOT/'cosim/black-parrot-example/Makefile.design').read_text()
    for key in ('BP_RETAINED_I_LINES','BP_RETAINED_D_LINES'):
        require(int(re.search(r'^'+key+r'\s*\?=\s*(\d+)\s*$',design,re.M)[1])==a['lines'],'selected capacity must equal committed source defaults')
    literal=module('literal_scratch_validator',STRICT)
    require(literal.ROOT==ROOT and bind(STRICT)['sha256']=='53eaca9a63bb31efa5571b6eb12279e1779339d4d3821f50488e7846f19d5d21','literal actual source tool-root before any reader')
    require(bind(READER)['sha256']==READER_SHA,'fixed admitted reader')
    for role in ('integrity','advisory'):
        for k in ('elf','nbf'):require(bind(a['programs'][role][k]['path'])==a['programs'][role][k],'selected exact program')
    require(a['programs']['advisory']['elf']['sha256']=='3fe096173e3a63b2656c1fadf0a058a328fb5f1ee375be652176408856f897b8' and a['programs']['advisory']['nbf']['sha256']=='627662f775f9c2645e5b5687a9df3bfaed25d42265e125a0386047ebe1daad4b','unchanged cold08')
    software=json.loads(Path(a['software_proof']['path']).read_text());require(bind(a['software_proof']['path'])==a['software_proof'],'ROOT actual integrity software proof')
    require(software['state'].startswith('PASS') and software['commands'],'complete actual software preparation')
    for command in software['commands']:
        life=command.get('ownership',command)
        require(life['returncode']==0 and not life.get('owned_group_remaining') and life.get('failure') is None,'software tools completed')
        if 'log' in command:require(bind(command['log']['path'])==command['log'],'actual software command log')
    require(software['expected']==dict(i_lines=a['lines'],d_lines=a['lines'],sets=256),'matching compiled integrity geometry')
    for role in ('integrity','advisory'):
        for k in ('elf','nbf'):require(software['programs'][role][k]==a['programs'][role][k],'programs bound by accepted actual software preparation')
    return a

def commands():
    recipe=OLD/'research/hp0-response-path-20261121/full-system-delay200-10/source-before.json.gz'
    import gzip
    command=json.loads(gzip.decompress(recipe.read_bytes()))['command_prefix']
    command=[v.replace('/home/coyang/zynq-parrot-linux-capacity',str(ROOT)) for v in command]
    command=[v for v in command if not v.startswith(('BP_RETAINED_BUFFER=','BP_RETAINED_I_LINES=','BP_RETAINED_D_LINES=','BP_RETAINED_SETS=','BP_RETAINED_OBSERVE=','BP_CACHE_MISS_TRACE='))]
    command=[('BP_AXI_RESPONSE_DELAY=0' if v.startswith('BP_AXI_RESPONSE_DELAY=') else 'VERILATOR_BUILD_JOBS=8' if v.startswith('VERILATOR_BUILD_JOBS=') else v) for v in command]
    command+=['BP_CACHE_MISS_TRACE=0','ZP_IMPORT_DIR='+str(ROOT/'import'),'COSIM_VSRC_DIR='+str(ROOT/'cosim/v'),'OBJCACHE=']
    return command

def validate_prior_layout_failure():
    path=budget.PRIOR_BASE/'full01/session.json';q=json.loads(path.read_text())
    require(q['state']=='FAIL preserved, no accepted result' and q['error']=="ValueError('command failed make-preflight')",'exact preserved V1 layout-only failure')
    require([c['label'] for c in q['commands']]==['make-preflight'] and 'model' not in q,'no prior clean/build/model/native/reader may be relabeled')
    require(q['prepared']['sha256']=='b35615fa82d6e393a0afc74c314fb01cb309a92258ea757db8c2db2e617173ca','exact original ROOT preparation')
    first=q['commands'][0];life=first['ownership']
    require(life['returncode']==2 and not life['owned_group_remaining'] and life['failure'] is None,'actual old Make failure with clean group')
    require(bind(first['log']['path'])==first['log'],'original failure log unchanged')
    text=Path(first['log']['path']).read_text();require('../Makefile.design' in text and 'No such file or directory' in text,'actual wrong parent-design path')
    inherited=json.loads((HERE/'inherited-v1-sources.json').read_text())
    for row in inherited['files']:require(bind(row['path'])==row,'original V1 source byte preserved')
    return dict(session=bind(path),log=first['log'],sources=bind(HERE/'inherited-v1-sources.json'))

def actual_sources(runtime,lines):
    metadata=runtime/'obj_dir/Vbsg_nonsynth_zynq_testbench__verFiles.dat';text=metadata.read_text();rows={}
    for line in text.splitlines():
        m=re.fullmatch(r'S\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+"([^"]+)"',line)
        if not m:continue
        size,inode,ct,cn,mt,mn=map(int,m.groups()[:6]);p=Path(m[7]);p=p if p.is_absolute() else runtime/p
        row=full_bind(p)
        require((row['bytes'],row['inode'],row['ctime_ns'],row['mtime_ns'])==(size,inode,ct*10**9+cn,mt*10**9+mn),'actual consumed source metadata')
        rows[str(p.resolve())]=row
    command=next(line for line in text.splitlines() if line.startswith('C '))
    for token in ('--assert','--trace-fst','--build-jobs 8','-DBSG_HIDE_FROM_SYNTHESIS'):
        require(token in command,'actual build scope '+token)
    for key,value in [('ACLK_MHZ',20),('BP_RETAINED_BUFFER',1),('BP_RETAINED_I_LINES',lines),('BP_RETAINED_D_LINES',lines),('BP_RETAINED_SETS',256),('BP_RETAINED_OBSERVE',1),('BP_AXI_RESPONSE_DELAY',0),('BP_CACHE_MISS_TRACE',0)]:
        require(re.search(r'(?<!\S)-D'+key+'='+str(value)+r'(?=\s|"|$)',command),'actual hardware define '+key)
    require('BP_CUSTOM_BASE_CFG' not in command and 'BP_NUM_THREADS' not in command,'named static configuration only')
    for p in (ROOT/'cosim/black-parrot-example/v/top_zynq.sv',ROOT/'import/black-parrot/bp_me/src/v/cce/bp_uce.sv',ROOT/'import/black-parrot/bp_common/src/v/bp_retained_line_store.sv'):
        require(str(p) in rows,'selected source actually consumed')
    stamps=list((runtime/'obj_dir').glob('.build_config-*'));require(len(stamps)==1,'one actual model stamp')
    for token in ('cfge_bp_unicore_zynqparrot_prefetch16k_cfg','-miss-trace0','-assert-bsgsimhidden-support','BP_RETAINED_I_LINES_'+str(lines),'BP_RETAINED_D_LINES_'+str(lines)):
        require(token in stamps[0].name,'effective model stamp '+token)
    return dict(sources=rows,metadata=bind(metadata)),bind(stamps[0])

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--selection',type=Path,required=True);ap.add_argument('--selection-sha256',required=True)
    ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--execute',action='store_true');ap.add_argument('--prepared-sha256');a=ap.parse_args()
    require(a.prepare_only!=a.execute,'explicit prepare-only or ROOT execution')
    selected=validate_selection(a.selection,a.selection_sha256);prior=validate_prior_layout_failure();budget.check()
    out=budget.BASE/'full01';prepared=budget.BASE/'prepared01.json'
    require(not out.exists(),'fresh fullcore attempt; no retry')
    helpers=[bind(p) for p in HERE.glob('*.py')]+[bind(source.PREVIOUS/'software_owned_v2.py'),bind(COUNTER),bind(COUNTER.with_name('build_full.py')),bind(GENERATED_GEOMETRY),bind(STRICT),bind(ROOT/'testing/check_run.py'),bind(FIXTURE)]
    plan=dict(state='PREPARED actual Make-n passed; scratch trace0 fullcore pending',selection=bind(a.selection),sources=helpers,command=commands(),prior_layout_failure=prior,
              native_ms=dict(integrity=600000,advisory=180000),outer_seconds=dict(build=3600,integrity=780,advisory=240,strict=660,counter=240,parameters=660),
              FST_bytes=FST_CAP,own_work_cap=budget.OWN_CAP,cleanup_seconds=5,archive='NONE automatic; preserve generated sources/PCH/objects for later qualified observation clone')
    budget.BASE.mkdir(exist_ok=True)
    if a.prepare_only:
        require(not prepared.exists(),'fresh preparation')
        plan['actual_make_preflight']=dryrun.perform(budget.BASE/'preflight01',commands(),selected['lines'],budget.check)
        write(prepared,plan);print(prepared);return
    require(bind(prepared)['sha256']==a.prepared_sha256,'external exact ROOT preparation SHA')
    saved=json.loads(prepared.read_text());preflight=saved.pop('actual_make_preflight')
    require(saved==plan and bind(preflight['path'])==preflight,'exact prepared flow/actual dryrun binding')
    dryrun.verify(preflight['path'],commands(),selected['lines'])
    out.mkdir();runtime=dryrun.layout(out)
    (out/'tmp').mkdir();env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(out/'tmp'),CCACHE_DISABLE='1',SCCACHE_DISABLE='1',OBJCACHE='')
    env['LD_LIBRARY_PATH']=str(INSTALL/'lib')+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    for key in list(env):
        if key.startswith(('BP_RETAINED_','BP_AXI_RESPONSE_DELAY','BP_CACHE_MISS_TRACE')):env.pop(key)
    source_proof=json.loads(Path(selected['source_preparation']['path']).read_text())
    record=dict(state='RUNNING clean fullcore',selection=bind(a.selection),prepared=bind(prepared),commands=[],inputs=helpers,
        source_tree_baseline=selected['TOP'],source_bp=selected['BP'],source_repositories=source_proof['repositories'],source_preparation=selected['source_preparation'],software_proof=selected['software_proof'],
        geometry=dict(i_lines=selected['lines'],d_lines=selected['lines'],sets=256,epoch=8,line_bytes=64,observe=1,cache_miss_trace=0,delay=0,resident=2,logical=4,l2_bytes=16384,aclk_mhz=20),
        environment={k:env[k] for k in ('LD_LIBRARY_PATH','CCACHE_DISABLE','SCCACHE_DISABLE','OBJCACHE','TMPDIR')})
    def run(label,argv,cwd=out,timeout=120,native=False):
        entry=dict(label=label,argv=list(map(str,argv)),cwd=str(cwd),timeout_s=timeout);record['commands'].append(entry);write(out/'session.json',record)
        def limits():
            resource.setrlimit(resource.RLIMIT_CORE,(0,0));cap=FST_CAP if native else 512*1024**2;resource.setrlimit(resource.RLIMIT_FSIZE,(cap,cap))
        life=None;started=time.monotonic()
        try:
            with (out/(label+'.log')).open('wb') as log:life=owned.run(entry['argv'],cwd,env,log,timeout,budget.check,limits)
        except BaseException as error:life=getattr(error,'owned_receipt',dict(failure=repr(error)));raise
        finally:
            write(out/(label+'-owned.json'),life);entry.update(ownership=life,returncode=life.get('returncode'),log=bind(out/(label+'.log')),elapsed_seconds=time.monotonic()-started);write(out/'session.json',record)
        require(life['returncode']==0,'command failed '+label) if not native else None
        return life['returncode']
    try:
        run('make-preflight',commands()+['-n','build'],runtime)
        run('clean',commands()+['clean'],runtime)
        run('build',commands()+['build'],runtime,3600)
        actual,stamp=actual_sources(runtime,selected['lines']);write(out/'actual-source-list.json',actual)
        model=runtime/'obj_dir/Vbsg_nonsynth_zynq_testbench';record.update(model=full_bind(model),model_stamp=stamp,actual_source_list=bind(out/'actual-source-list.json'))
        facts,paths=module('generated_scratch_geometry',GENERATED_GEOMETRY).inspect(out,record['model']['sha256'])
        write(out/'generated-geometry.json',dict(state='PASS actual generated STATIC16KiB L2 geometry',facts=facts,auditor=bind(GENERATED_GEOMETRY),snapshot_paths=list(map(str,paths))))
        run('loader',['ldd',model]);require('not found' not in (out/'loader.log').read_text(),'actual libraries resolved')
        for role in ('integrity','advisory'):
            dest=out/role;dest.mkdir()
            for key,name in [('elf','prog.riscv'),('nbf','prog.nbf')]:shutil.copyfile(selected['programs'][role][key]['path'],dest/name);require(bind(dest/name)['sha256']==selected['programs'][role][key]['sha256'],'copied exact program')
            native_ms,deadline=(600000,780) if role=='integrity' else (180000,240)
            argv=[model,'+c_args=prog.nbf '+str(native_ms),'+bsg_trace='+str(dest/'trace.fst')]
            write(dest/'admission.json',dict(selection=bind(a.selection),model=record['model'],sources=record['actual_source_list'],argv=list(map(str,argv))))
            rc=run(role+'-run',argv,dest,deadline,True);shutil.copyfile(out/(role+'-run.log'),dest/'run.log');write(dest/'process.json',dict(returncode=rc))
            check=['python3','-B',ROOT/'testing/check_run.py',dest/'run.log','--exit-code',str(rc)]
            if role=='integrity':check+=['--test','mt_large_retained_system_test']
            run(role+'-checker',check)
            text=(dest/'run.log').read_text();require(text.count('Verilator assertion setting restored to 1')==1,'runtime assertions restored')
            values=re.findall(r'RETAINED_USE_COUNTERS version=1 i_hits=(\d+) d_hits=(\d+) i_published=(\d+) d_published=(\d+) i_write_beats=(\d+) d_write_beats=(\d+) saturating_bits=16 reset=axi_only',text)
            if role=='advisory':require(len(values)==1 and tuple(map(int,values[0]))==(1,1,1,1,8,8),'actual GP0 observer')
            write(dest/'verification.json',dict(state='PASS complete scoped wholecore and actual GP0 1hit/1publish/8writes per lane; strict closed trace audit pending' if role=='advisory' else 'PASS complete checked integrity',actual_returncode=rc,
                counter_values=values[0] if role=='advisory' else None,sources=record['actual_source_list'],trace=bind(dest/'trace.fst'),files=[full_bind(dest/n) for n in ('admission.json','process.json','run.log','prog.riscv','prog.nbf','trace.fst')]))
        # Correct literal root is preflighted again against actual consumption.
        strict=module('actual_scratch_validator',STRICT);require(strict.ROOT==ROOT,'actual tool-root before reader');strict.source_bindings(out/'actual-source-list.json')
        target=out/'advisory';rc=json.loads((target/'process.json').read_text())['returncode']
        run('strict',['python3','-B',STRICT,'--fst',target/'trace.fst','--reader',READER,'--model-source-list',out/'actual-source-list.json','--fixture-manifest',FIXTURE,'--log',target/'run.log','--exit-code',str(rc),'--reader-timeout','600','--out',out/'strict01'],timeout=660)
        run('counter',['python3','-B',COUNTER,'--fst',target/'trace.fst','--reader',READER,'--strict-proof',out/'strict01/verification.json','--run-proof',target/'verification.json','--out',out/'counter01'],timeout=240)
        run('parameters',['python3','-B',HERE/'geometry.py','--fst',target/'trace.fst','--reader',READER,'--lines',str(selected['lines']),'--out',out/'parameters01'],timeout=660)
        require(json.loads((out/'strict01/verification.json').read_text())['accepted'] is True,'strict payload/realwrites/Iretire')
        require(json.loads((out/'counter01/verification.json').read_text())['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8]),'independent counter transitions')
        for row in actual['sources'].values():require(full_bind(row['path'])==row,'compiled input unchanged through complete gate')
        require(full_bind(model)==record['model'],'model unchanged')
        validate_selection(a.selection,a.selection_sha256)
        record.update(state='PASS scratch-only trace0 clean fullcore integrity/cold08 strict512b-eight-real-writes-Iretire-counter-geometry-source-audits',
            closed_audits={n:bind(out/p) for n,p in [('strict','strict01/verification.json'),('counter','counter01/verification.json'),('parameters','parameters01/verification.json'),('generated_l2','generated-geometry.json')]},scope='Synthetic correctness only; no area/fit/FPGA/application or all-slot claim; preserve all original generated objects/PCH for qualified clone.')
    except BaseException as error:record.update(state='FAIL preserved, no accepted result',error=repr(error));raise
    finally:write(out/'session.json',record);print(out/'session.json',record['state'])


if __name__=='__main__':main()
