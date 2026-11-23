#!/usr/bin/env python3
"""ROOT-only five-command continuation; default prints source-only plan."""
import argparse,hashlib,importlib.util,inspect,json,os,re,resource,shutil,signal,socket,stat,sys,time,uuid
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
PLAN=HERE/'plan.json'
FINAL=HERE/'admission.FINAL.json'
OLD=HERE.parent/'csr-canonical-snapshot-worker-preparation-20261123'
RUN01=Path('/run/user/1001/zp-csr-canonical-snapshot-component-20261123-01')
RUN=Path('/run/user/1001/zp-csr-canonical-snapshot-component-20261123-02')
CLAIM='ONE five-command canonical CSR continuation; old FAIL unchanged; no synthesis'
def require(ok,message):
    if not ok:raise RuntimeError(message)
def bind(path):
    path=Path(path);b=path.read_bytes();return dict(path=str(path),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def verify(row):require(bind(row['path'])==row,'binding drift '+row['path'])
def module(name,row):
    verify(row);s=importlib.util.spec_from_file_location(name,row['path']);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m

def check_log(text,label,rc):
    lines=[line.rstrip('\r')for line in text.splitlines()]
    width=[tuple(map(int,m))for m in re.findall(r'(?m)^CSR_CANONICAL_WIDTH expanded=(\d+) encoded=(\d+) contexts=(\d+)\s*$',text)]
    require(len(width)==1 and width[0][0]==1666 and 0<width[0][1]<1666 and width[0][2]==4, 'actual codec width marker')
    positives=[line for line in lines if re.fullmatch(r'CSR_PRIMARY_EQUIVALENCE_PASS checks=\d+ cycles=\d+ reads=\d+ saves=\d+ reloads=\d+',line)]
    negatives=[line for line in lines if re.fullmatch(r'CSR_PRIMARY_NEGATIVE_DETECTED interface=mepc bit=2 cycles=\d+ checks=\d+',line)]
    fatal_lines=[line for line in lines if re.match(r'^(?:Fatal:|FATAL_ERROR|FATAL:)',line)]
    if label in ('noncanonical','reconstruction'):
        marker='CSR_CANONICAL_NONCANONICAL_WRITE' if label=='noncanonical' else 'CSR_CANONICAL_RECONSTRUCTION_MISMATCH'
        require(rc==0 and text.count(marker)==1 and not positives and not negatives, 'exact expected HDL-fatal negative, nonzero native exit')
        require(len(fatal_lines)==1 and marker in fatal_lines[0], 'only expected target assertion fatal')
        require('CSR_PRIMARY_MISMATCH'not in text and 'fixed HDL watchdog'not in text, 'no unrelated mismatch/timeout')
        return dict(expected_assertion=marker,actual_returncode=rc,expanded_bits=width[0][0],encoded_bits=width[0][1],contexts=width[0][2],raw_tool_error_lines=[line for line in lines if re.match(r'^(?:ERROR:|Error:)',line)])
    require(rc==0 and not fatal_lines and not any(re.match(r'^(?:ERROR:|Error:)',line)for line in lines), 'normal/MEPC exact native0, no fatal/error')
    require(not any(marker in text for marker in ('CSR_PRIMARY_MISMATCH','CSR_CANONICAL_NONCANONICAL_WRITE','CSR_CANONICAL_RECONSTRUCTION_MISMATCH')), 'no codec/primary assertion')
    if label=='negative':require(len(negatives)==1 and not positives,'original MEPC negative terminal')
    else:
        require(len(positives)==1 and not negatives,'one exact positive terminal')
        sweep='CSR_CANONICAL_REAL_PRODUCER_SWEEP_PASS banks=2 contexts=4 fields=26 inputbits=64 writes=13312'
        require(lines.count(sweep)==1, 'complete unchanged-oracle real producer sweep')
    return dict(marker=(negatives if label=='negative'else positives)[0],expanded_bits=width[0][0],encoded_bits=width[0][1],contexts=width[0][2])


def inventory(root):
    rows=[]
    for p in sorted(root.rglob('*')):
        st=p.lstat();require(not p.is_symlink(),'old stage unknown symlink')
        if p.is_file():rows.append(dict(relative=str(p.relative_to(root)),mode=stat.S_IMODE(st.st_mode),binding=bind(p)))
    return rows

def prior(p,old):
    verify(p['prior_session']);d=json.loads(Path(p['prior_session']['path']).read_text())
    require(d['state']=='FAIL preserved; no retry' and d['error']=="RuntimeError('native returncode noncanonical')",'only known original RC assumption failure')
    require(d['source_endcheck']=='PASS' and d['ownership_final']['linux_claim_state']=='RELEASED' and not d['ownership_final']['owned_group_remaining'],'old final lifecycle and source checks')
    cs=d['commands'];require([r['label']for r in cs]==['xvlog-global','xvlog-RTL','xelab','negative','noncanonical'],'exact completed first five')
    for r in cs:
        o=r['owned'];require(o['returncode']==0 and o['failure'] is None and not o['owned_group_remaining'],'actual prior native0 and lifecycle '+r['label'])
        if 'log'in r:verify(r['log'])
    for label in ('negative','noncanonical'):
        text=(RUN01/(label+'.log')).read_text()
        a=check_log(text,label,0);require(a['encoded_bits']==741,'actual prior741 width')
        require(re.search(r'(?m)^\*{6} xsim v2024\.2 \(64-bit\)',text),'prior actual Xsim2024.2')
        require('## run all' in text and '## quit' in text,'controlled run-all then normal quit')
        if label=='noncanonical':require('Time: 825 ns 'in text and '$finish called at time : 825 ns'in text,'exact retained noncanonical target event')
    text=(RUN01/'xelab.log').read_text()
    require(re.search(r'(?m)^Vivado Simulator v2024\.2(?:\.0)?\s*$',text),'actual prior elaborator2024.2')
    threads=re.findall(r'Using (\d+) slave threads\.',text);require(len(threads)==1 and 0<int(threads[0])<=8,'prior workers<=8')
    rtl=(RUN01/'xvlog-RTL.log').read_text()
    copies=d['source_copies'];old.verify_copies(copies)
    require(len(copies)==34 and sum(bool(r['mutation'])for r in copies)==1,'unchanged17 normal plus17 mutant copies')
    normal=[r for r in copies if r['arm']=='normal'];require(len(normal)==17 and all(r['copy']['path']in rtl for r in normal),'prior analyzed17 RTL')
    for row in d['negative_snapshot']+d['noncanonical_snapshot']:verify(row['binding'])
    require((OLD/'run.tcl').read_bytes()==b'run all\nquit\n','byte-exact unchanged normal-quit Tcl')
    return dict(prior_session=p['prior_session'],original_state=d['state'],original_error=d['error'],original_commands=5,original_actual_native_codes=[0]*5,MEPC=check_log((RUN01/'negative.log').read_text(),'negative',0),noncanonical=check_log((RUN01/'noncanonical.log').read_text(),'noncanonical',0),correction='only check_log rc!=0 -> rc==0; native0 unchanged and no shell mask')

def load(sha,execute):
    p=json.loads(PLAN.read_text());require(p['schema']=='csr-canonical-five-command-continuation-v2','fixed plan')
    for row in p['inputs']:verify(row)
    require(bind(Path(__file__))in p['inputs'],'actual continuation source')
    if not execute:return p,None,None,None
    require(sha and bind(FINAL)['sha256']==sha,'ROOT exact FINAL SHA required')
    f=json.loads(FINAL.read_text());require(f['schema']=='csr-canonical-five-command-admission-v2' and f['launchable']is True,'DRAFT cannot execute')
    require(f['source_plan']==bind(PLAN) and f['limits']==p['limits'],'exact new prospective plan and bounds')
    require(f['linux_claim']==CLAIM,'one fixed continuation scope')
    verify(f['ROOT_release']);r=json.loads(Path(f['ROOT_release']['path']).read_text())
    require(r.get('allow_csr_canonical_five_command_continuation')is True and r.get('source_plan')==bind(PLAN) and r.get('linux_claim')==CLAIM,'explicit release for continuation only')
    other=f['fixed_OTHER_reservations'];require(set(other)=={'RUN_bytes','HOME_bytes'}and all(type(x)is int and x>=0 for x in other.values()),'fixed OTHER priced')
    require(r.get('fixed_OTHER_reservations')==other,'release same OTHER')
    old=module('frozen_csr_worker01',p['old_worker']);op,of=old.load(p['old_admission']['sha256'],True)
    require(socket.gethostname()==op['target_hostname'],'same actual tool host')
    require(f['tool_inputs']==of['tool_inputs'],'same exact2024.2 tools/glbl')
    for x in f['tool_inputs'].values():verify(x)
    expected=inspect.getsource(old.check_log).replace('rc!=0','rc==0')
    require(inspect.getsource(check_log)==expected,'pure checker exact one-comparison derivation; original diagnostic text retained')
    return p,f,old,op

def budget(p,f,old):
    z=p['limits'];run=old.usage(RUN01)+old.usage(RUN)
    source=old.usage(OLD)+old.usage(old.PREP)+old.CODEC.stat().st_size+old.usage(HERE)
    require(source<=z['source_packet_bytes'] and source<=z['HOME_family_bytes'],'whole old+new source/authority family')
    require(run<=z['RUN_bytes'],'whole old+new RUN cap')
    o=f['fixed_OTHER_reservations']
    require(shutil.disk_usage(RUN.parent).free>=z['RUN_floor_bytes']+z['RUN_bytes']-run+o['RUN_bytes'],'shared RUN remaining plus floor and ALL OTHER')
    require(shutil.disk_usage(HERE).free>=z['HOME_floor_bytes']+z['HOME_family_bytes']-source+o['HOME_bytes'],'shared HOME remaining plus floor and ALL OTHER')
    mem=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines()if x.startswith('MemAvailable:'))
    require(mem>=z['MemAvailable_floor_bytes'],'6GiB host memory floor')
    return dict(shared_RUN_bytes=run,shared_HOME_source_bytes=source,MemAvailable_bytes=mem)

def commands(old,op):
    result=[]
    for label,seconds,cwd,argv in old.commands(op)[5:]:
        # Only output CWDs move. All17 inputs-mutant and run.tcl remain old byte-bound paths.
        result.append((label,seconds,RUN/cwd.relative_to(RUN01),list(map(str,argv))))
    require([x[0]for x in result]==['positive','xvlog-global-mutant','xvlog-RTL-mutant','xelab-mutant','reconstruction'],'exact remaining five')
    return result

def main():
    a=argparse.ArgumentParser();a.add_argument('--execute',action='store_true');a.add_argument('--admission-sha256');args=a.parse_args()
    p,f,old,op=load(args.admission_sha256,args.execute)
    if not args.execute:
        print(json.dumps(dict(state='UNADMITTED source-only continuation; no tools/inventory',source_plan=bind(PLAN),prior=p['prior_session'],remaining=p['remaining_commands'],limits=p['limits']),indent=2));return
    require(not RUN.exists(),'fresh02; no automatic retry')
    promoted=prior(p,old);old_rows=inventory(RUN01)
    owned=old.load_module('software_owned_v2',op['owned_worker']);q=old.load_module('csr_continuation_qualified_worker',op['qualified_worker']);require(q.owned is owned,'same qualified owned API')
    idle=q.empty_inventory();initial=budget(p,f,old);RUN.mkdir();(RUN/'tmp').mkdir();(RUN/'build-mutant').mkdir()
    identity=dict(hostname=socket.gethostname(),pid=os.getpid(),pgid=os.getpgrp(),startticks=q.stat_row(os.getpid())['startticks'],nonce=uuid.uuid4().hex)
    receipt=dict(schema='bp1-root-pervm-cad-ownership-receipt-v1',**identity,admission_sha256=args.admission_sha256,linux_claim_state='ACK',linux_claim=CLAIM,basis='coordinator conditional release + ROOT perVM onejobprotocol',atomic_global_lock=False,initial_idle=idle)
    ack=RUN/'ROOT-ownership.json';q.save(ack,receipt);q.save(RUN/'ROOT-ownership-initial.json',receipt)
    q.save(RUN/'old01-readonly-inventory.json',old_rows)
    state=dict(state='RUNNING five-command continuation; prior FAIL retained',admission=bind(FINAL),source_plan=bind(PLAN),promotion=promoted,initial_resources=initial,commands=[],old01_inventory=bind(RUN/'old01-readonly-inventory.json'))
    active=None;armed=False;started=time.monotonic()
    def guard():
        nonlocal active
        require(time.monotonic()-started<p['limits']['whole_seconds'],'fixed continuation deadline')
        budget(p,f,old);require(bind(FINAL)['sha256']==args.admission_sha256,'FINAL unchanged')
        q.validate_ack(json.loads(ack.read_text()),identity,args.admission_sha256,CLAIM)
        rows=q.process_rows()
        if armed and active is None:
            children=[r for r in rows if r['ppid']==os.getpid()and r['pgid']==r['pid']];require(len(children)<=1,'one owned tool group')
            if children:active={k:children[0][k]for k in ('pid','pgid','startticks')}
        leader=next((r for r in rows if active and r['pid']==active['pid']and r['startticks']==active['startticks']),None)
        require(not q.vendor_inventory(rows,active['pgid']if leader else None),'foreign vendor/launcher; abort only own group')
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(p['limits']['RUN_bytes'],)*2);resource.setrlimit(resource.RLIMIT_AS,(p['limits']['per_process_AS_bytes'],)*2)
    def interrupt(sig,frame):raise RuntimeError('ROOT continuation signal '+str(sig))
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,interrupt)
    try:
        for label,seconds,cwd,argv in commands(old,op):
            load(args.admission_sha256,True);old.verify_copies(json.loads(Path(p['prior_session']['path']).read_text())['source_copies']);guard()
            if label in ('positive','reconstruction'):
                cwd.mkdir();state[label+'_snapshot']=old.physical_snapshot(RUN01/'build-normal'if label=='positive'else RUN/'build-mutant',cwd)
            entry=dict(label=label,timeout_seconds=seconds,cwd=str(cwd),argv=argv);state['commands'].append(entry);q.save(RUN/'session.json',state)
            active=None;armed=True
            with (RUN/(label+'.log')).open('wb')as log:
                try:entry['owned']=owned.run(argv,cwd,dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(RUN/'tmp')),log,seconds,guard,limits)
                except BaseException as e:
                    entry['owned']=getattr(e,'owned_receipt',dict(failure=repr(e),owned_group_remaining=False,scope='prePopen refusal'));raise
            armed=False;o=entry['owned'];require(o['failure']is None and not o['owned_group_remaining']and o['returncode']==0,'actual native0 and lifecycle '+label)
            if active:require(o['owned_pgid']==active['pgid'],'actual own group identity')
            active=None;entry['log']=bind(RUN/(label+'.log'));text=Path(entry['log']['path']).read_text()
            if label in ('positive','reconstruction'):
                entry['analysis']=check_log(text,label,o['returncode']);require(entry['analysis']['encoded_bits']==741,'same actual741 codec')
                require(re.search(r'(?m)^\*{6} xsim v2024\.2 \(64-bit\)',text),'actual Xsim2024.2')
                require('## run all'in text and '## quit'in text,'same controlled normal-quit Tcl')
            if label=='xvlog-RTL-mutant':
                copies=json.loads(Path(p['prior_session']['path']).read_text())['source_copies'];rows=[r for r in copies if r['arm']=='mutant'];require(len(rows)==17 and all(r['copy']['path']in text for r in rows),'all17 exact existing mutant inputs analyzed')
            if label=='xelab-mutant':
                require(re.search(r'(?m)^Vivado Simulator v2024\.2(?:\.0)?\s*$',text),'actual2024.2 elaborator');t=re.findall(r'Using (\d+) slave threads\.',text);require(len(t)==1 and 0<int(t[0])<=8,'actual<=8 workers');entry['actual_xelab_slave_threads']=int(t[0])
            guard();q.save(RUN/'session.json',state)
        require(len(state['commands'])==5,'five commands only')
        state['state']='PASS composite behavioral canonical real-two-bank13312 sweep + original MEPC + canonicality/reconstruction target fatals; old01 FAIL unchanged; not mapped/fullcore'
    except BaseException as e:
        state.update(state='FAIL continuation preserved; no retry',error=repr(e));raise
    finally:
        for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,signal.SIG_IGN)
        armed=False
        try:
            load(args.admission_sha256,True);prior(p,old);require(inventory(RUN01)==old_rows,'ALL old01 file bytes/modes/membership unchanged');state['source_endcheck']='PASS';state['old01_endcheck']='PASS complete read-only byte/mode/membership inventory';state['final_global_idle']=q.empty_inventory()
        except BaseException as e:state.update(state='FAIL source/old01-endcheck',endcheck_error=repr(e))
        remaining=bool(active and owned.group_state(active['pgid']))or any(x.get('owned',{}).get('owned_group_remaining',False)for x in state['commands'])
        if remaining:state['state']='FAIL own group remains; claim HELD'
        release=dict(receipt,linux_claim_state='HELD_OWNED_GROUP_REMAINS'if remaining else 'RELEASED',owned_group_remaining=remaining,outcome=state['state'])
        try:
            current=json.loads(ack.read_text())
            if all(current.get(k)==identity[k]for k in identity)and current.get('linux_claim_state')=='ACK':q.save(ack,release)
            else:q.save(RUN/'ROOT-ownership-final.json',release)
        except BaseException as e:
            state.update(state='FAIL ownership receipt',ownership_release_error=repr(e));q.save(RUN/'ROOT-ownership-final.json',release)
        state.update(elapsed_seconds=time.monotonic()-started,ownership_final=release);q.save(RUN/'session.json',state)
    require(state['state'].startswith('PASS composite'),'final composite acceptance')
if __name__=='__main__':main()
