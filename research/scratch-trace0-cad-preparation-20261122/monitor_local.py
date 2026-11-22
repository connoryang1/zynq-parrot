#!/usr/bin/env python3
"""Observe one ROOT-admitted local bp1 job; no launch or SSH exists here."""
from pathlib import Path
import argparse,fcntl,hashlib,json,re,subprocess,time
from budget import LIMITS,violations as budget_violations
HERE=Path(__file__).resolve().parent
LOCAL=['python3','-B','-']

def bind(p):
 raw=p.read_bytes();return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def write(p,v):
 tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(v,indent=2)+'\n');tmp.replace(p)
def check_bindings(admission):
 if admission.get('launchable') is not True:raise RuntimeError('UNLAUNCHABLE: exact local ROOT/source/clock admission is not promoted')
 if admission['schema']!='scratch1792-trace0-local-clean-cad-v2' or admission['configuration']['top']!='4dadebbfdddfe958eff432b7f87280cfb9b5d991' or admission['configuration']['bp']!='7566c67aad9b93f5546fcc5e258e405402a47850':raise RuntimeError('wrong exact candidate')
 config=admission['configuration']
 expected_env=dict(ZP_REPO_DIR='/home/coyang/zynq-parrot-linux-scratch-profile',ZP_FPGA_SEED_REPO_DIR='/home/coyang/zynq-parrot-linux-scratch-profile',ZP_FPGA_LOG_ROOT=config['log_root'],ZP_FPGA_WORK_ROOT=config['work_root'],FPGA_CFG='e_bp_unicore_zynqparrot_prefetch16k_cfg',FPGA_VIVADO_THREADS='8',FPGA_NUM_THREADS='2',FPGA_NUM_CONTEXTS='4',FPGA_ACLK_MHZ='20',FPGA_SPARSE_SOURCE='1',FPGA_CACHE_MISS_TRACE='0')
 launch=admission['direct_launch']
 if launch['environment']!=expected_env or launch['argv']!=['/home/coyang/zynq-parrot-linux-capacity/codex-skills/bp-fpga-synthesis/scripts/launch_synthesis.sh','start'] or launch['working_directory']!=expected_env['ZP_REPO_DIR']:raise RuntimeError('direct launch differs from exact source/profile/configuration')
 for name in ('fullcore','root_release'):
  item=admission['prerequisites'].get(name)
  if not item or item.get('ROOT_verified') is not True or not item.get('binding'):raise RuntimeError('missing ROOT verified prerequisite: '+name)
  if bind(Path(item['binding']['path']))!=item['binding']:raise RuntimeError('prerequisite changed: '+name)
 full=json.loads(Path(admission['prerequisites']['fullcore']['binding']['path']).read_text())
 if not full['state'].startswith('PASS scratch-only1792 trace0 composite first-native') or full['model']['sha256']!='3f3e8b766f19746cb434e99200c0bde49853e4c0cc27aeec7a0dbacec7f6b2df':raise RuntimeError('exact accepted fullcore missing')
 if full['source_tree_baseline']!=admission['configuration']['top'] or full['source_bp']!=admission['configuration']['bp'] or full['geometry']['cache_miss_trace']!=0:raise RuntimeError('fullcore source/profile mismatch')
 archive=admission['prerequisites']['fullcore']['source_archive']
 if bind(Path(archive['path']))!=archive:raise RuntimeError('changed durable fullcore archive binding')
 release=json.loads(Path(admission['prerequisites']['root_release']['binding']['path']).read_text())
 for key,value in [('state','ROOT ADMITTED local clean CAD'),('top',admission['configuration']['top']),('bp',admission['configuration']['bp']),('launch',admission['direct_launch']),('resources',LIMITS)]:
  if release.get(key)!=value:raise RuntimeError('ROOT release exact configuration mismatch: '+key)
 if release.get('holds_released') is not True:raise RuntimeError('ROOT CAD holds not released')
 if release.get('operational_bindings')!=admission['operational_bindings']:raise RuntimeError('ROOT release operational source mismatch')
 for expected in admission['bindings']:
  if bind(Path(expected['path']))!=expected:raise RuntimeError('changed bound input: '+expected['path'])
 if admission['resources']!=LIMITS:raise RuntimeError('budget constants differ from frozen admission')
def poll(config):
 # repr generates a Python literal; it is sent on stdin, never interpolated in a shell.
 script=('CONFIG='+repr(config)+'\n').encode()+(HERE/'identity.py').read_bytes()+b'\n'+(HERE/'remote_probe.py').read_bytes()
 r=subprocess.run(LOCAL,input=script,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40)
 if r.returncode:raise RuntimeError('read-only local poll failed; no signal sent: '+r.stderr.decode(errors='replace')[-2048:])
 return json.loads(r.stdout),r.stdout

def violations(s,config):
 return list(s['identity_violations'])+budget_violations(s['resources'],s['worker_elapsed_seconds'],config['resources'])
def ownership(s,config,pid,startticks):
 w=s.get('worker');desc={p['pid'] for p in s['descendants']}
 return bool(w and w['pid']==pid and w['startticks']==startticks and w['pgrp']==w['sid']==pid and ('worker '+config['job']+' '+config['top']) in w['argv'] and all(p['pid'] in desc for p in s['worker_group']) and all(p['pid'] in desc for p in s['all_vivado']))
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--admission',default=str(HERE/'admission-source04.DRAFT.json'));ap.add_argument('--admission-sha256',required=True);ap.add_argument('--job',required=True)
 mode=ap.add_mutually_exclusive_group(required=True);mode.add_argument('--preflight',action='store_true');mode.add_argument('--execute',action='store_true')
 ap.add_argument('--worker-pid',type=int);ap.add_argument('--worker-startticks',type=int)
 args=ap.parse_args();p=Path(args.admission).resolve()
 if bind(p)['sha256']!=args.admission_sha256:raise RuntimeError('admission hash mismatch')
 admission=json.loads(p.read_text());check_bindings(admission)
 if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-4dadebbfd',args.job):raise RuntimeError('unexpected job/revision identity')
 config=dict(admission['configuration'],job=args.job,resources=admission['resources'],evidence_root=str(HERE))
 if args.preflight:
  s,_=poll(config);reasons=violations(s,config)
  if s['all_vivado']:reasons.append(dict(kind='prelaunch_vendor_not_idle'))
  if s['resources']['work_root_exists']:reasons.append(dict(kind='prelaunch_work_root_not_fresh',path=config['work_root']))
  print(json.dumps(dict(state='PASS' if not reasons else 'REFUSED',resources=s['resources'],violations=reasons,mutations=0),indent=2))
  return 1 if reasons else 0
 if not args.worker_pid or not args.worker_startticks:raise RuntimeError('execute requires exact worker PID and startticks')
 # No build/vendor launch exists here. ROOT separately owns the pinned direct launcher and HOLD release.
 with (HERE/'monitor.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  baseline,raw=poll(config)
  if not ownership(baseline,config,args.worker_pid,args.worker_startticks):raise RuntimeError('initial exact ownership unproven; no signal sent')
  out=HERE/('run-'+args.job);out.mkdir(exist_ok=False)
  (out/'poll-001.json').write_bytes(raw);index=1;prior=baseline;failures=0
  identity=dict(job=args.job,worker=baseline['worker'],admission=bind(p),bindings=admission['bindings'],poll_interval_seconds=90,configuration=config,mutations='Only maintained cancellation on admitted bounds/features after exact owner/startticks/ancestry recheck; no vendor/board launch')
  write(out/'monitor-identity.json',identity)
  while True:
   s=prior if index==1 else None
   if s is None:
    delay=max(0,90-(time.time()-prior['epoch']))
    if delay:time.sleep(delay)
    try:s,raw=poll(config);failures=0
    except Exception as e:
     failures+=1;print('MONITOR_OBSERVATION_FAILURE '+repr(e),flush=True)
     if failures>=3:raise
     time.sleep(90);continue
    if s['epoch']-prior['epoch']<60:raise RuntimeError('poll interval guard')
    (out/('poll-%03d.json'%index)).write_bytes(raw)
   reasons=violations(s,config)
   record=dict(utc=s['utc'],status=s['status'],poll='poll-%03d.json'%index,resources=s['resources'],worker_elapsed_seconds=s['worker_elapsed_seconds'],features=s['feature_state'],reports=[r['binding'] for r in s['reports']],feedback_warnings=s['feedback_warnings'],identity_violations=s['identity_violations'],bound_violations=reasons,latest_milestones=s['milestones'][-6:])
   old={p['pid']:p for p in prior['all_vivado']};record['CPU_advancement']=[]
   for proc in s['all_vivado']:
    q=old.get(proc['pid'])
    if q and q['startticks']==proc['startticks'] and '/unwrapped/' in proc['argv']:
     record['CPU_advancement'].append(dict(pid=proc['pid'],CPU_seconds=((proc['utime_ticks']+proc['stime_ticks'])-(q['utime_ticks']+q['stime_ticks']))/s['ticks_per_second']))
   write(out/'live-status.json',record)
   stage=lambda x:[(m['path'],m['line'],m['text']) for m in x['milestones'] if not any(w in m['text'] for w in ('WARNING','ERROR','posedge_clk','CONFIG','set ::env'))][-1:]
   changed=index==1 or s['status']!=prior['status'] or s['feature_state']!=prior['feature_state'] or [r['binding']['sha256'] for r in s['reports']]!=[r['binding']['sha256'] for r in prior['reports']] or bool(s['feedback_warnings'])!=bool(prior['feedback_warnings']) or bool(reasons)
   if changed or stage(s)!=stage(prior):print(json.dumps(record),flush=True)
   if s['status']!='RUNNING':
    check_bindings(admission);write(out/'terminal-status.json',record)
    if s['status']=='PASS' and s['feature_state']!='PASS actual seven defines/three contexts/20MHz-8MHz/source':raise RuntimeError('worker PASS lacks complete actual source/profile/clock acceptance')
    print('MONITOR_TERMINAL '+s['status'],flush=True);return 0 if s['status']=='PASS' else 1
   if reasons:
    fresh,raw=poll(config);(out/'pre-cancel-identity.json').write_bytes(raw)
    if fresh['status']!='RUNNING':print('BOUND_TERMINAL_NO_CANCEL',flush=True);prior=s;index+=1;continue
    if not violations(fresh,config):print('BOUND_RECHECK_CLEARED_NO_CANCEL',flush=True);prior=s;index+=1;continue
    check_bindings(admission)
    if not ownership(fresh,config,args.worker_pid,args.worker_startticks):raise RuntimeError('exact ownership proof failed; no signal sent')
    argv=['bash',str(HERE/'cancel_local.sh'),args.job,config['log_root']]
    write(out/'cancellation-reason.json',dict(reasons=violations(fresh,config),worker=fresh['worker'],verified_all_vivado_descendants=True,argv=argv))
    with (out/'maintained-cancel.log').open('wb') as log:r=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,timeout=50)
    print('MAINTAINED_CANCEL_EXIT '+str(r.returncode),flush=True)
    post,raw=poll(config);(out/'post-cancel-status.json').write_bytes(raw)
    if post['all_vivado'] or post['worker'] or post['status']!='CANCELLED':raise RuntimeError('terminal cancellation/process disappearance unproven')
    check_bindings(admission);write(out/'terminal-status.json',dict(status='CANCELLED',cause=violations(fresh,config),post_snapshot='post-cancel-status.json'))
    print('MONITOR_TERMINAL CANCELLED_BOUND_OR_IDENTITY',flush=True);return 0
   prior=s;index+=1
if __name__=='__main__':raise SystemExit(main())
