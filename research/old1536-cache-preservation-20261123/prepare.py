from pathlib import Path
import json,hashlib,stat,shutil
O=Path(__file__).parent
BASE=Path('/run/user/1001/zp-csr-unmasked1536-fullcore-20261122-01')
I=BASE/'archive64-records01/inventory.json'
assert hashlib.sha256(I.read_bytes()).hexdigest()=='ff464c3aa838984274f4cde51d56035804f4e97f164492ac3e2113cc12b3c579'
old=json.loads(I.read_bytes());selected=[r for r in old['excluded']if r['reason']=='rebuildable compiled host cache only; complete byte inventory retained']
assert len(selected)==147 and sum(r['bytes']for r in selected)==85970984
roots=[BASE/'full01/verilator/obj_dir',BASE/'scoped-csr01/build/obj'];rows=[]
for r in selected:
 p=Path(r['path']);s=p.lstat();assert p.parent in roots and p.suffix in {'.o','.a'} and stat.S_ISREG(s.st_mode) and not s.st_mode&0o111 and s.st_nlink==1
 assert [s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_ino,stat.S_IMODE(s.st_mode)]==r['stat']
 h=hashlib.sha256(p.read_bytes()).hexdigest();assert h==r['sha256']
 rows.append(dict(path=str(p),relative=str(p.relative_to(BASE)),bytes=s.st_size,mode=s.st_mode,device=s.st_dev,inode=s.st_ino,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns,nlink=1,sha256=h))
q=dict(state='ROOT reviewed147 exact inactive unfit1536 native compiled caches; new complete cache archive/readback and scoped owner checks required before unlink',rows=rows,total_bytes=85970984,original_pool=str(BASE),old_inventory=dict(path=str(I),bytes=I.stat().st_size,sha256=hashlib.sha256(I.read_bytes()).hexdigest()),scope='Only the147 explicitly excluded rebuildable .o/.a files; preserve both models,generatedCPP/headers,all FST,programs,SOURCE/privateGit,current1280 and allFPGA outputs')
(O/'manifest.json').write_text(json.dumps(q,indent=2)+'\n')
P=Path('/home/coyang/.codex/research-reviews/blackparrot/linux-cache-pack03-20261123/pack.py');raw=P.read_text();assert hashlib.sha256(raw.encode()).hexdigest()=='b12886ea8731c254be39741cc9b53b1248f1e2485afbf4795775c1406a0dca7e'
needle="  assert comm not in {'make','gmake','ninja','gcc','g++','cc1','cc1plus','ar','verilator','verilator_bin'},(str(proc),comm)\n"
assert raw.count(needle)==1
replacement="  # Current FPGA make is unrelated. Refuse any actor naming the frozen old pool.\n  argv=(proc/'cmdline').read_bytes().split(b'\\0')\n  for token in argv:\n   value=token.decode(errors='replace').split('=',1)[-1]\n   assert not(value==M['original_pool'] or value.startswith(M['original_pool']+'/')),('old pool argv owner',str(proc))\n"
raw=raw.replace(needle,replacement)
needle="   except FileNotFoundError:pass\n except (FileNotFoundError,ProcessLookupError):pass"
assert raw.count(needle)==1
replacement="   except FileNotFoundError:pass\n  # Inspect only after readable FD namespace; exact two known desktop FD\n  # exceptions stay recorded and do not become general permission exemptions.\n  for name in ('cwd','exe'):\n   target=os.readlink(proc/name)\n   assert not(target==M['original_pool'] or target.startswith(M['original_pool']+'/')),('old pool cwd/exe owner',str(proc),name)\n  maps=(proc/'maps').read_text()\n  assert M['original_pool']+'/' not in maps,('old pool mapped owner',str(proc))\n except (FileNotFoundError,ProcessLookupError):pass"
raw=raw.replace(needle,replacement)
needle=" assert digest(p)==r['sha256']\n";assert raw.count(needle)==1
raw=raw.replace(needle," assert s.st_ctime_ns==r['ctime_ns'] and s.st_nlink==r['nlink']==1\n"+needle)
(O/'pack.py').write_text(raw)
review=dict(ROOT_approved=True,manifest_sha256=hashlib.sha256((O/'manifest.json').read_bytes()).hexdigest(),packer_sha256=hashlib.sha256((O/'pack.py').read_bytes()).hexdigest(),parent_packer_sha256='b12886ea8731c254be39741cc9b53b1248f1e2485afbf4795775c1406a0dca7e',changes='Replace global compiler/make exclusion with exactoldpool argv/cwd/exe/maps plus existing selectedFD scan; add originalctime/nlink check. Same codec/caps/allbyte readback/stableoriginals/unlink sequence.',archive_cap_bytes=33554432,metadata_cap_bytes=2097152,wall_seconds=125,AS_bytes=1073741824,no_CURRENT1280_or_FPGA_mutation=True)
(O/'ROOT-scope-review.json').write_text(json.dumps(review,indent=2)+'\n');print(json.dumps(review))
