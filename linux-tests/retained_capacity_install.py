"""Fixed-path reviewed atomic runner swap; caller must own common reservation."""
import json
import re
import shlex

RPC=r'''
import hashlib,json,os,pathlib,stat,subprocess,sys
root=pathlib.Path('/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq')
lock=pathlib.Path('/home/xilinx/bp-logs/.control-program.lock')
request=json.loads(sys.argv[1]);assert set(request)=={'action','token','original'}
action=request['action'];token=request['token']
assert action in ('inspect','install','restore') and len(token)==16 and all(c in '0123456789abcdef' for c in token)
old='2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30'
new='9c2648f1a9d2ceab2645895fdad74a5bc2c2ce62ad8f1161c6b3b72e74da42fa'
helper='de54badda52bcf716daaed5155d9be8674b3f0c137e0e411be075c7685c1db90'
def read(path):
 fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as stream:
  before=os.fstat(stream.fileno());assert stat.S_ISREG(before.st_mode)
  data=stream.read();after=os.fstat(stream.fileno())
 assert (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
 return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),mode=stat.S_IMODE(after.st_mode),uid=after.st_uid,gid=after.st_gid)
assert not os.path.lexists(str(lock)),'existing board program lock; never remove its owner/guard here'
assert subprocess.run(['pgrep','-x','control-program'],stdout=subprocess.PIPE).returncode==1,'active program'
control=root/'control-program';before=read(control);assert before['sha256'] in (old,new)
assert read(root/'run-blackparrot-interactive')['sha256']==helper
metadata={k:before[k] for k in ('mode','uid','gid')}
if action=='inspect':
 assert request['original'] is None
else:
 original=request['original'];assert set(original)=={'mode','uid','gid'} and all(type(v) is int for v in original.values())
 assert metadata==original and before['uid']==os.geteuid(),'preserve reviewed ownership/mode; no generic privilege bypass'
 temporary=root/('.bp-capacity-'+token+('-new' if action=='install' else '-old'))
 expected=new if action=='install' else old
 if action=='install':assert before['sha256']==old,'install starts only from actual accepted2dd'
 if before['sha256']!=expected:
  staged=read(temporary);assert staged['sha256']==expected and staged['uid']==original['uid'] and staged['gid']==original['gid']
  os.chmod(str(temporary),original['mode'])
  fd=os.open(str(temporary),os.O_RDONLY|os.O_NOFOLLOW)
  try:os.fsync(fd)
  finally:os.close(fd)
  assert read(control)==before,'installed runner changed during staging'
  os.replace(str(temporary),str(control))
 fd=os.open(str(control),os.O_RDONLY|os.O_NOFOLLOW)
 try:os.fsync(fd)
 finally:os.close(fd)
 fd=os.open(str(root),os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
 os.sync()
 after=read(control);assert after['sha256']==expected and all(after[k]==original[k] for k in original)
 assert read(root/'run-blackparrot-interactive')['sha256']==helper
 print(json.dumps(dict(action=action,before=before,after=after,original=original,helper_sha256=helper,durable=True),sort_keys=True))
 sys.exit(0)
print(json.dumps(dict(action=action,before=before,original=metadata,helper_sha256=helper),sort_keys=True))
'''


def command(host,action,token,original=None):
    if host!='xilinx@192.168.4.35' or action not in ('inspect','install','restore') or not re.fullmatch(r'[0-9a-f]{16}',token):
        raise ValueError('fixed diagnostic runner publication only')
    request=dict(action=action,token=token,original=original)
    return ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',host,
        'python3 -c '+shlex.quote(RPC)+' '+shlex.quote(json.dumps(request,sort_keys=True))]


def temporary(token,kind):
    if not re.fullmatch(r'[0-9a-f]{16}',token) or kind not in ('new','old'):raise ValueError('fixed owned temporary')
    return '/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq/.bp-capacity-'+token+'-'+kind
