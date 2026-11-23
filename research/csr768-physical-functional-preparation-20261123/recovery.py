"""V3 durable own-guard witness plus live-helper detection; fixed paths only."""
import json
import re
import shlex

RPC=r'''
import hashlib,json,os,pathlib,re,stat,subprocess,sys
root=pathlib.Path('/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq')
logs=pathlib.Path('/home/xilinx/bp-logs')
proc=pathlib.Path('/proc')
lock=logs/'.control-program.lock'
request=json.loads(sys.argv[1]);assert set(request)=={'action','context','witness'}
action=request['action'];context=request['context'];witness=request['witness']
assert action in ('probe','witness','remove-owned-stale')
old='2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30'
new='9c2648f1a9d2ceab2645895fdad74a5bc2c2ce62ad8f1161c6b3b72e74da42fa'
helper='de54badda52bcf716daaed5155d9be8674b3f0c137e0e411be075c7685c1db90'
nbfs={'d-enabled':'4a8512dfa3074997c7e6ecf63a733a5cc597595c455308397a7f3a88090d6921',
 'd-off':'b60a50bba248fd8c54a7cc1385a2e25eb852f1a7a53e39b162c479ed9087e9d4',
 'i-enabled':'047f330163a22ba0eda3ec8cd559f655a718bec8300b4113c745a86f4d764267'}
def metadata(s):return dict(device=s.st_dev,inode=s.st_ino,mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)
def read(path):
 fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as stream:
  first=os.fstat(stream.fileno());assert stat.S_ISREG(first.st_mode)
  data=stream.read();last=os.fstat(stream.fileno())
 assert metadata(first)==metadata(last) and first.st_size==last.st_size
 return dict(metadata(last),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()),data
def guard():
 if not os.path.lexists(str(lock)):return None
 first=lock.lstat();assert stat.S_ISDIR(first.st_mode) and first.st_uid==os.geteuid(),'unknown guard directory'
 assert sorted(p.name for p in lock.iterdir())==['owner'],'unknown guard contents'
 owner,data=read(lock/'owner');assert owner['uid']==os.geteuid() and re.fullmatch(rb'[1-9][0-9]*\n',data),'unknown guard owner'
 last=lock.lstat();assert metadata(first)==metadata(last),'guard changed while witnessing'
 return dict(directory=metadata(last),owner_file=owner,pid=int(data.strip()))
def active(pattern,full=False):
 result=subprocess.run(['pgrep','-f' if full else '-x',pattern],stdout=subprocess.PIPE)
 assert result.returncode in (0,1),'process inspection failed'
 return [int(pid) for pid in result.stdout.split()] if result.returncode==0 else []
def probe():
 boot=(proc/'sys/kernel/random/boot_id').read_text().strip();assert re.fullmatch('[0-9a-f-]{36}',boot)
 control,_=read(root/'control-program');source,_=read(root/'run-blackparrot-interactive')
 return dict(boot_id=boot,guard=guard(),control_sha256=control['sha256'],helper_sha256=source['sha256'],
  active_control=active('control-program'),active_script=active('[s]cript .*control-program',True),
  active_helper=active('[r]un-blackparrot-interactive([[:space:]]|$)',True))
def known(current):
 assert current['control_sha256'] in (old,new) and current['helper_sha256']==helper,'unknown runner/helper'
def valid_context(c):
 assert set(c)=={'token','role','pid','log','bit_sha256','preflight'} and re.fullmatch('[0-9a-f]{16}',c['token'])
 assert c['role'] in nbfs and type(c['pid']) is int and c['pid']>0 and re.fullmatch('[0-9a-f]{64}',c['bit_sha256'])
 stem='retained-capacity768-'+c['role'];pattern=re.escape(str(logs)+'/'+stem+'-interactive-')+r'[0-9]{8}T[0-9]{6}Z-'+str(c['pid'])+r'\.log'
 assert re.fullmatch(pattern,c['log']),'bound helper/NBF log identity'
 prior=c['preflight'];known(prior)
 assert prior['control_sha256']==new and prior['guard'] is None and not prior['active_control'] and not prior['active_script'] and not prior['active_helper'],'prior idle absent guard/helper'
def owned_process(c):
 path=proc/str(c['pid'])
 if not path.exists():return 'absent'
 argv=(path/'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
 expected=[str(root/'run-blackparrot-interactive'),'retained-capacity768-'+c['role']+'.nbf',nbfs[c['role']],new,'300000',c['bit_sha256']]
 assert [a.decode() for a in argv[1:]]==expected and pathlib.Path(argv[0].decode()).name=='bash','owner PID is not our bound helper'
 return 'exact-bound-live-helper'
def descendant(pid,owner):
 for _ in range(64):
  if pid==owner:return True
  path=proc/str(pid)/'status'
  if not path.exists():return False
  match=re.search(r'^PPid:\s*(\d+)$',path.read_text(),re.M)
  if not match:return False
  parent=int(match[1])
  if parent in (0,pid):return False
  pid=parent
 return False
current=probe()
if action=='probe':
 assert context is None and witness is None
 print(json.dumps(current,sort_keys=True));sys.exit(0)
valid_context(context);known(current)
if action=='witness':
 assert witness is None and current['boot_id']==context['preflight']['boot_id'],'old boot witness required before own power'
 if current['guard'] is not None:assert current['guard']['pid']==context['pid'],'unknown/new guard owner'
 owner_state=owned_process(context)
 assert all(descendant(pid,context['pid']) for pid in current['active_control']+current['active_script']+current['active_helper']),'unowned active program/script'
 assert guard()==current['guard'],'guard changed during witness'
 # Persist the exact board-side identity before the caller may hard-cut power.
 # The host separately fsyncs this returned witness before invoking power.
 synced=[]
 if current['guard'] is not None:
  for path,flags,label in ((lock/'owner',os.O_RDONLY|os.O_NOFOLLOW,'owner'),
                          (lock,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,'guard-directory')):
   fd=os.open(str(path),flags)
   try:os.fsync(fd)
   finally:os.close(fd)
   synced.append(label)
 fd=os.open(str(logs),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(fd)
 finally:os.close(fd)
 synced.append('logs-parent');os.sync()
 durable=probe();known(durable)
 assert durable['boot_id']==current['boot_id'] and durable['guard']==current['guard'],'guard/boot changed during sync'
 assert durable['control_sha256']==current['control_sha256'] and durable['helper_sha256']==current['helper_sha256']
 assert all(descendant(pid,context['pid']) for pid in durable['active_control']+durable['active_script']+durable['active_helper']),'unowned active process after sync'
 owner_state=owned_process(context)
 value=dict(schema='bp-capacity-owned-guard-witness-v2',context=context,old_boot_id=durable['boot_id'],guard=durable['guard'],
  helper_process_state=owner_state,active_control=durable['active_control'],active_script=durable['active_script'],active_helper=durable['active_helper'],
  guard_durable=True,synced_paths=synced,sync_complete=True)
 print(json.dumps(value,sort_keys=True));sys.exit(0)
assert witness['schema']=='bp-capacity-owned-guard-witness-v2' and witness['context']==context
assert witness['guard_durable'] is True and witness['sync_complete'] is True,'durable pre-power witness required'
assert witness['old_boot_id']==context['preflight']['boot_id'] and current['boot_id']!=witness['old_boot_id'],'verified new boot required'
assert not current['active_control'] and not current['active_script'] and not current['active_helper'] and not (proc/str(context['pid'])).exists(),'active process/PID reuse after reboot'
removed=False
if current['guard'] is not None:
 assert witness['guard'] is not None and current['guard']==witness['guard'],'changed/unknown guard after reboot'
 assert current['guard']['pid']==context['pid'] and guard()==witness['guard'],'same proven owned stale guard only'
 os.unlink(str(lock/'owner'));os.rmdir(str(lock));removed=True
fd=os.open(str(logs),os.O_RDONLY|os.O_DIRECTORY)
try:os.fsync(fd)
finally:os.close(fd)
os.sync()
after=probe();known(after)
assert after['boot_id']==current['boot_id'] and after['guard'] is None and not after['active_control'] and not after['active_script'] and not after['active_helper']
print(json.dumps(dict(state='PASS own-session stale guard recovery after verified reboot',removed=removed,witness=witness,after=after,durable=True),sort_keys=True))
'''


def command(host,action,context=None,witness=None):
    if host!='xilinx@192.168.4.35' or action not in ('probe','witness','remove-owned-stale'):
        raise ValueError('fixed own-session recovery operation only')
    request=dict(action=action,context=context,witness=witness)
    return ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',host,
        'python3 -c '+shlex.quote(RPC)+' '+shlex.quote(json.dumps(request,sort_keys=True))]


def idle(probe,expected=None):
    import retained_capacity_diagnostic as p
    p.require(probe['guard'] is None and not probe['active_control'] and not probe['active_script'] and not probe['active_helper'],'unknown/preexisting guard or active program/helper')
    p.require(probe['helper_sha256']==p.HELPER and probe['control_sha256'] in (p.OLD,p.RUNNER),'actual known runner/helper')
    if expected is not None:p.require(probe['control_sha256']==expected,'actual expected runner')
    return probe
