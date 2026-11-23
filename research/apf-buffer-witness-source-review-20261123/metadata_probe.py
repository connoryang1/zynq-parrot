#!/usr/bin/env python3
"""Unadmitted read-only APF discovery; no device, memory, ioctl or library call."""
import argparse,gzip,hashlib,json,os,resource,signal,stat,sys,time
from pathlib import Path
DEADLINE=20
OUTPUT=524288
READ_CAP=1048576
EXE='/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq/control-program'
LIB='/usr/lib/libcma.so'
WRAPPER='/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq/run-blackparrot-interactive'
FILES={EXE:'2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30',LIB:'126301f9575d119f3b12e41bc2ce26df79a0fdae210169da3bf4b6548dd1fdd3',WRAPPER:'de54badda52bcf716daaed5155d9be8674b3f0c137e0e411be075c7685c1db90'}
SYMBOLS={'xlnk_bufpool','xlnk_bufpool_alloc_point','xlnk_bufpool_size','xlnk_buflen','xlnk_phyaddr','xlnk_userbuf','xlnk_buf_process','xlnk_bufcacheable','xlnk_allocbuf','xlnk_freebuf','xlnk_mmap','xlnk_ioctl','xlnk_recover_resource','xlnk_release','xlnk_vma_close','xlnk_probe'}
def need(ok,message):
 if not ok:raise RuntimeError(message)
def read(path,limit):
 with Path(path).open('rb')as f:
  b=f.read(limit+1)
 need(len(b)<=limit,'fixed read bound '+str(path));return b
def digest(b):return hashlib.sha256(b).hexdigest()
def describe(path):
 try:
  p=Path(path);s=p.lstat();d=dict(path=str(p),mode=s.st_mode,device=s.st_dev,inode=s.st_ino,size=s.st_size)
  if p.is_symlink():d['target']=os.readlink(str(p))
  return d
 except OSError as e:return dict(path=str(path),error=repr(e))
def proc_identity(pid):
 raw=read('/proc/%d/stat'%pid,16384).decode();end=raw.rfind(')');fields=raw[end+2:].split()
 return dict(pid=pid,comm=raw[raw.find('(')+1:end],startticks=int(fields[19]),ppid=int(fields[1]),state=fields[0],exe=os.readlink('/proc/%d/exe'%pid))
def safe_text(path,cap=65536):
 try:
  b=read(path,cap);return dict(path=str(path),bytes=len(b),sha256=digest(b),text=b.decode('utf-8','replace'))
 except (OSError,RuntimeError)as e:return dict(path=str(path),error=repr(e))
def inspect(pid,expected_start):
 before=proc_identity(pid);need(before['startticks']==expected_start,'specified PID/startticks binding');need(before['exe']==EXE,'exact existing controller path; no start/attach')
 exe=read('/proc/%d/exe'%pid,READ_CAP);need(digest(exe)==FILES[EXE],'actual process executable exact2dd')
 maps=safe_text('/proc/%d/maps'%pid,262144);need('text'in maps,'readable exact process maps')
 mapping=[];xlnk=[]
 for line in maps['text'].splitlines():
  f=line.split(None,5);need(len(f)>=5,'proc maps shape');lo,hi=[int(x,16)for x in f[0].split('-')];name=f[5]if len(f)==6 else''
  row=dict(start=lo,end=hi,bytes=hi-lo,permissions=f[1],file_offset=int(f[2],16),device=f[3],inode=int(f[4]),path=name)
  if 'xlnk'in name:
   row['candidate_APF_slot_if_pinned_mmap_ABI']=row['file_offset']>>16;row['extent_authority']=False;xlnk.append(row)
  if 'libcma.so'in name:mapping.append(row)
 need(len(xlnk)<=32 and len(mapping)<=16,'bounded selected VMA sets')
 fd=[]
 paths=sorted(Path('/proc/%d/fd'%pid).iterdir(),key=lambda p:int(p.name));need(len(paths)<=256,'selected process fd cap')
 for p in paths:
  target=os.readlink(str(p))
  if 'xlnk'in target:fd.append(dict(fd=int(p.name),target=target,metadata=describe(p),fdinfo=safe_text('/proc/%d/fdinfo/%s'%(pid,p.name),16384)))
 smaps=read('/proc/%d/smaps'%pid,8*1048576).decode('utf-8','replace');blocks=[];selected=False;current=[]
 for line in smaps.splitlines():
  if line and '-'in line.split()[0]and len(line.split())>=5:
   if selected:blocks.append('\n'.join(current))
   selected='xlnk'in line;current=[line]if selected else[]
  elif selected:current.append(line)
 if selected:blocks.append('\n'.join(current))
 need(len(blocks)<=32 and sum(map(len,blocks))<=131072,'xlnk smaps metadata cap')
 after=proc_identity(pid);need(after['pid']==before['pid']and after['startticks']==before['startticks']and after['exe']==before['exe'],'PID identity stable across metadata snapshot')
 return dict(identity_before=before,identity_after=after,executable_sha256=digest(exe),maps=maps,libcma_VMA_metadata=mapping,xlnk_VMA_metadata=xlnk,xlnk_FD_metadata=fd,xlnk_smaps_metadata=blocks,driver_extent_or_lifetime_proved=False)
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute',action='store_true');ap.add_argument('--admission',type=Path);ap.add_argument('--admission-sha256');a=ap.parse_args()
 if not a.execute:print(json.dumps(dict(state='UNADMITTED metadata-only source; no discovery executed',ioctl=False,memory_reads=False,device_opens=False,PID=None)));return
 need(a.admission is not None and a.admission_sha256,'ROOT exact admission required');raw=read(a.admission,65536);need(digest(raw)==a.admission_sha256,'exact ROOT authority');r=json.loads(raw.decode())
 need(r['schema']=='apf-readonly-metadata-discovery-v1'and r['ROOT_approved']is True,'unadmitted cannot execute')
 need(r.get('common_flock_held_by_ROOT_wrapper')is True and r.get('common_flock_receipt')is not None,'caller must use existing ROOT common flock; no new lock protocol')
 need(r['probe_sha256']==digest(read(Path(__file__),65536)),'actual probe source binding')
 need(r['limits']==dict(seconds=20,output_bytes=524288,AS_bytes=134217728),'fixed metadata bounds')
 # No acquisition or verification of a flock is claimed by this child. ROOT's
 # existing owned SSH/common-flock wrapper must validate its own receipt.
 signal.signal(signal.SIGALRM,lambda s,f:(_ for _ in ()).throw(RuntimeError('fixed20s metadata deadline')));signal.alarm(DEADLINE)
 resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(134217728,)*2)
 need(os.geteuid()==0,'ROOT wrapper must supply existing authorized root read context');start=time.monotonic();o=dict(state='RUNNING metadata discovery only',authority_sha256=a.admission_sha256,caller_common_flock_receipt=r['common_flock_receipt'],no_new_privileges=True,no_ioctl_or_device_memory_reads=True,no_controller_launch_attach_signal=True,errors=[])
 try:
  o['boot_id']=safe_text('/proc/sys/kernel/random/boot_id',4096);o['uname']=list(os.uname())
  o['identities']=[]
  for path,sha in FILES.items():
   b=read(path,READ_CAP);need(digest(b)==sha,'retained exact file changed '+path);o['identities'].append(dict(path=path,bytes=len(b),sha256=sha))
  notes=read('/sys/kernel/notes',65536);o['kernel_notes']=dict(bytes=len(notes),sha256=digest(notes),hex=notes.hex())
  cfg=read('/proc/config.gz',131072);text=gzip.decompress(cfg).decode();keys=('CONFIG_XILINX_APF','CONFIG_KALLSYMS','CONFIG_PROC_KCORE','CONFIG_DEVKMEM','CONFIG_STRICT_DEVMEM','CONFIG_DEBUG_FS','CONFIG_PROC_PAGE_MONITOR','CONFIG_IKCONFIG','CONFIG_CMA','CONFIG_DMA_CMA','CONFIG_ARCH_DMA_ADDR_T','CONFIG_PHYS_ADDR_T','CONFIG_ARM_LPAE','CONFIG_IOMMU','CONFIG_ARM_SMMU','CONFIG_DEBUG_INFO','CONFIG_DEBUG_INFO_BTF')
  o['kernel_config']=dict(compressed_bytes=len(cfg),sha256=digest(cfg),selected_lines=[l for l in text.splitlines()if any(k in l for k in keys)])
  o['global_metadata']=[safe_text(p,cap)for p,cap in [('/proc/devices',32768),('/proc/iomem',262144),('/proc/meminfo',32768),('/proc/sys/kernel/kptr_restrict',4096),('/proc/sys/kernel/yama/ptrace_scope',4096),('/sys/class/xlnk/xlnk/dev',4096),('/sys/class/xlnk/xlnk/uevent',8192),('/sys/kernel/tracing/events/cma/cma_alloc/format',16384),('/sys/kernel/tracing/events/cma/cma_release/format',16384),('/sys/kernel/debug/tracing/events/cma/cma_alloc/format',16384),('/sys/kernel/debug/tracing/events/cma/cma_release/format',16384)]]
  o['interface_metadata_only']=[describe(p)for p in ('/dev/xlnk','/dev/mem','/dev/kmem','/proc/kcore','/sys/kernel/btf/vmlinux','/sys/class/xlnk','/sys/bus/platform/drivers/xlnk','/sys/module/xlnk')]
  o['interface_directory_entries']=[]
  for p in ('/sys/class/xlnk','/sys/bus/platform/drivers/xlnk','/sys/module/xlnk'):
   try:
    names=sorted(Path(p).iterdir());need(len(names)<=128,'fixed shallow interface cap');o['interface_directory_entries'].append(dict(path=p,entries=[describe(x)for x in names]))
   except OSError as e:o['errors'].append(dict(path=p,error=repr(e)))
  sym=[];consumed=0
  try:
   with Path('/proc/kallsyms').open('rt')as f:
    for line in f:
     consumed+=len(line);need(consumed<=16*1048576,'kallsyms metadata input cap');cols=line.split()
     if len(cols)>=3 and cols[2]in SYMBOLS:sym.append(line.rstrip())
   need(len(sym)<=128,'filtered symbols cap');o['selected_kernel_symbols']=dict(lines=sym,input_bytes=consumed,absence_or_zero_is_not_implementation_proof=True)
  except OSError as e:o['errors'].append(dict(path='/proc/kallsyms',error=repr(e)))
  pid=r.get('existing_control_PID');ticks=r.get('existing_control_startticks')
  if pid is None:o['process']=dict(state='NO_EXISTING_PID_SELECTED; no per-buffer witness')
  else:
   need(type(pid)is int and pid>1 and type(ticks)is int and ticks>0,'exact ROOT PID/startticks');o['process']=inspect(pid,ticks)
   o['forbidden_process_interfaces_metadata_only']=[describe('/proc/%d/%s'%(pid,n))for n in ('mem','pagemap','map_files')]
  for path,sha in FILES.items():need(digest(read(path,READ_CAP))==sha,'end exact deployed file changed '+path)
  need(safe_text('/proc/sys/kernel/random/boot_id',4096)==o['boot_id'],'boot identity stable')
  o['file_and_boot_endcheck']='PASS'
  o['state']='PASS bounded metadata discovery; APF allocation extent/lifetime NOT proved'
 except BaseException as e:o.update(state='FAIL/PARTIAL metadata preserved; no retry or side effects',error=repr(e))
 finally:
  o['elapsed_seconds']=time.monotonic()-start;signal.alarm(0);out=json.dumps(o,separators=(',',':'));need(len(out.encode())<=OUTPUT,'whole512KiB output bound');print(out,flush=True)
 if not o['state'].startswith('PASS'):raise SystemExit(1)
if __name__=='__main__':main()
