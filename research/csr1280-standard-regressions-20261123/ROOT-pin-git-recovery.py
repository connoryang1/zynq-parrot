from pathlib import Path
import json,hashlib,subprocess,os
O=Path(__file__).parent
P=Path('/run/user/1001/zp-csr-unmasked1280-fullcore-20261122-01/source-preparation.json')
raw=P.read_bytes();assert hashlib.sha256(raw).hexdigest()=='6edd515e1418e46d7e0ed9fd8bf2a0ba578a25e7aa338f5a9e1f37ca26aeb4ca'
data=json.loads(raw);rows=[];ref='refs/recovery/linux-retained1280-20261123'
env=dict(os.environ,GIT_OPTIONAL_LOCKS='0')
def git(repo,*args):return subprocess.check_output(['git','--git-dir='+str(repo),*args],env=env,timeout=30)
for r in data['repositories']:
 alt=r['optional_alternates'];head=r['head'];private=Path(r['private_git_dir'])
 assert len(head)==40
 if alt:
  ap=Path(alt['path']);b=ap.read_bytes();assert len(b)==alt['bytes'] and hashlib.sha256(b).hexdigest()==alt['sha256']
  lines=b.decode().splitlines();assert len(lines)==1
  objects=Path(lines[0]);assert objects.is_absolute() and objects.name=='objects' and objects.is_dir()
  assert str(objects).startswith('/home/coyang/zynq-parrot/.git/') and not(objects/'info/alternates').exists()
  repo=objects.parent
  payload=git(repo,'cat-file','commit',head);assert hashlib.sha1(b'commit '+str(len(payload)).encode()+b'\0'+payload).hexdigest()==head
  prior=git(repo,'for-each-ref','--format=%(objectname)',ref).decode().strip();assert prior in ('',head)
  if not prior:git(repo,'update-ref',ref,head,'0'*40)
  assert git(repo,'rev-parse',ref).decode().strip()==head
  rows.append(dict(source_path=r['path'],head=head,durable_common_git_dir=str(repo),durable_objects=str(objects),recovery_ref=ref,commit_payload_bytes=len(payload),commit_payload_sha256=hashlib.sha256(payload).hexdigest(),archive_includes_objects=False,recovery='Preserved durable HOME common objects and explicit GC root ref; full working source/private Git metadata archived separately'))
 else:
  payload=git(private,'cat-file','commit',head);assert hashlib.sha1(b'commit '+str(len(payload)).encode()+b'\0'+payload).hexdigest()==head
  assert not(private/'objects/info/alternates').exists()
  rows.append(dict(source_path=r['path'],head=head,private_git_dir=str(private),commit_payload_bytes=len(payload),commit_payload_sha256=hashlib.sha256(payload).hexdigest(),archive_includes_objects=True,recovery='All private object files are part of complete SOURCE archive; no external alternate'))
assert len(rows)==9
q=dict(ROOT_verified=True,state='PASS all9 exact Git commit objects and recovery roots; external object bodies explicitly outside32MiB native archive',source_preparation=dict(path=str(P),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()),repositories=rows,all_durable_HOME_external_stores_preserved=True,all_working_source_and_private_git_to_be_archived=True,scope='Recovery evidence only, no model/FPGA/app acceptance')
p=O/'ROOT-git-recovery.json';assert not p.exists();p.write_text(json.dumps(q,indent=2)+'\n');print(p,hashlib.sha256(p.read_bytes()).hexdigest())
