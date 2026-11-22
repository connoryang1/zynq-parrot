"""Verbatim per-VM inventory/ACK functions extracted from qualified mapping05 worker."""
import hashlib,json,os
from pathlib import Path
VENDOR_NAMES={'vivado','vivado_lab','xelab','xsim','xsimk','xsimk.exe','xvlog','xsc','vitis_hls','v++','planahead'}
VENDOR_LAUNCHERS={'run_vivado_2024_2.sh','launch_synthesis.sh'}
class ForeignJob(RuntimeError):pass
class Deferred(RuntimeError):pass
def require(ok,msg):
 if not ok:raise ValueError(msg)
def utc():
 import datetime
 return datetime.datetime.now(datetime.timezone.utc).isoformat()
def stat_row(pid):
 p=Path('/proc')/str(pid);text=(p/'stat').read_text();end=text.rfind(')');fields=text[end+2:].split()
 return dict(pid=int(pid),comm=text[text.find('(')+1:end],ppid=int(fields[1]),pgid=int(fields[2]),state=fields[0],startticks=int(fields[19]))

def process_rows():
 rows=[]
 for p in Path('/proc').glob('[0-9]*'):
  try:
   rec=stat_row(p.name);cmd=(p/'cmdline').read_bytes().split(b'\0');rec['argv']=[x.decode(errors='replace') for x in cmd if x]
   if stat_row(p.name)['startticks']!=rec['startticks']:continue
   rows.append(rec)
  except (FileNotFoundError,ProcessLookupError):continue
  except PermissionError:
   # Kernel process identity remains the basic global vendor check. Never
   # expose unrelated inaccessible command lines or search credentials.
   try:rec=stat_row(p.name);rec['argv']=[];rec['cmdline_unreadable']=True;rows.append(rec)
   except (FileNotFoundError,ProcessLookupError):continue
 return rows

def is_vendor(row):
 if row['comm'].lower() in VENDOR_NAMES:return True
 if row['comm'].lower() in ('pgrep','ps','grep'):return False
 return any(str(arg).split('/')[-1].lower() in VENDOR_NAMES|VENDOR_LAUNCHERS for arg in row.get('argv',[]))

def vendor_inventory(rows,allowed_pgid=None):
 result=[]
 for r in rows:
  if not is_vendor(r) or (allowed_pgid is not None and r['pgid']==allowed_pgid):continue
  item={k:r[k] for k in ('pid','comm','ppid','pgid','state','startticks')}
  item['executable']=r.get('argv',[''])[0] if r.get('argv') else None
  item['argv_sha256']=hashlib.sha256('\0'.join(r.get('argv',[])).encode()).hexdigest();result.append(item)
 return result

def empty_inventory():
 rows=vendor_inventory(process_rows());
 if rows:raise Deferred('global vendor/launcher inventory busy: '+json.dumps(rows,sort_keys=True))
 return dict(utc=utc(),vendor_processes=[])

def validate_ack(record,identity,admission_sha,claim=None):
 for k in ('hostname','pid','startticks','pgid','nonce'):
  require(record.get(k)==identity[k],'ROOT ownership receipt identity changed '+k)
 require(record.get('admission_sha256')==admission_sha and record.get('linux_claim_state')=='ACK','ROOT Linux CAD claim revoked/changed')
 if claim is not None:require(record.get('linux_claim')==claim,'current ACK Linux claim changed')
 require(record.get('basis')=='coordinator conditional release + ROOT perVM onejobprotocol','ownership basis changed')
