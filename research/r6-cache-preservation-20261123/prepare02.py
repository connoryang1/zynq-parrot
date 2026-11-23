from pathlib import Path
import hashlib,json,stat,shutil,subprocess,os
O=Path(__file__).parent
C=Path('/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/csr1536-cad03-terminal-sizing-20261123/cache-candidates.json')
q=json.loads(C.read_bytes())['R6_conditional_only']
ROOT=Path(q['root'])/'zynq-parrot-fpga-20261121T220319Z-eb7d39013'
assert (ROOT/'.git').read_text()=='gitdir: /home/coyang/zynq-parrot/.git/worktrees/zynq-parrot-fpga-20261121T220319Z-eb7d39013\n'
tracked=set(subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z'],env=dict(os.environ,GIT_OPTIONAL_LOCKS='0')).decode().split('\0'))
rows=[];cut=1795305600000000000
for item in q['directories']:
 root=Path(item['directory']);assert ROOT in root.parents and root.is_dir()
 for p in sorted(root.glob('*.rtd')):
  s=p.lstat();assert stat.S_ISREG(s.st_mode) and not s.st_mode&0o111 and s.st_nlink==1 and s.st_mtime_ns<cut and s.st_dev==2050
  assert str(p.relative_to(ROOT)) not in tracked
  h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(1048576),b''):h.update(b)
  rows.append(dict(path=str(p),relative=str(p.relative_to('/home/coyang')),bytes=s.st_size,mode=s.st_mode,device=s.st_dev,inode=s.st_ino,mtime_ns=s.st_mtime_ns,sha256=h.hexdigest()))
assert len(rows)==130 and sum(r['bytes'] for r in rows)==213594504
(O/'manifest.json').write_text(json.dumps(dict(state='ROOT exact generated untracked RTD scope; inactivity/archive verification required before unlink',rows=rows,total_bytes=sum(r['bytes'] for r in rows),scope=q['directories'],authorization='Persisting user-authorized reversible inactive generated cache cleanup; preserve source, netlists/checkpoints, images, traces, executables and logs'),indent=2)+'\n')
p=Path('/home/coyang/.codex/research-reviews/blackparrot/linux-cache-pack03-20261123/pack.py');raw=p.read_text();assert hashlib.sha256(raw.encode()).hexdigest()=='b12886ea8731c254be39741cc9b53b1248f1e2485afbf4795775c1406a0dca7e'
assert raw.count('33554432')==3 and raw.count('START<120')==1
raw=raw.replace('33554432','67108864').replace('START<120','START<180');(O/'pack.py').write_text(raw)
profile=Path('/home/coyang/fpga-artifacts/context-resume/csr1280-native-authority-20261123/ROOT-resource-profile.json');v=json.loads(profile.read_bytes());need=v['HOME_floor_bytes']+32*1024**2+v['other_HOME_bytes']+66*1024**2
assert shutil.disk_usage(O).free>=need,(shutil.disk_usage(O).free,need)
r=dict(ROOT_approved=True,scope='130 exact R6 .Xil/incrSyn untracked .rtd nonexecutables; no netlist/checkpoint deletion',manifest_sha256=hashlib.sha256((O/'manifest.json').read_bytes()).hexdigest(),packer_sha256=hashlib.sha256((O/'pack.py').read_bytes()).hexdigest(),parent_packer_sha256='b12886ea8731c254be39741cc9b53b1248f1e2485afbf4795775c1406a0dca7e',only_packer_changes='32MiB archive cap ->64MiB;120s internal deadline ->180s',archive_cap_bytes=64*1024**2,metadata_cap_bytes=2*1024**2,wall_seconds=185,AS_bytes=1024**3,profile=dict(path=str(profile),sha256=hashlib.sha256(profile.read_bytes()).hexdigest()),HOME_before=shutil.disk_usage(O).free,HOME_required_including_all_old_future_and_floors=need,all_other_reserves_retained=True,explicit_git_tracking_check=True)
(O/'ROOT-scope-review.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
