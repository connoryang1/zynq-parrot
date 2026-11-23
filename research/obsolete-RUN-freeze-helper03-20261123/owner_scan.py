"""Read-only qualified producer scan; exact copied function bodies, no retirement API."""
import json,os,re
from pathlib import Path
PRODUCER_UID=1001
def require(v,m):
 if not v:raise ValueError(m)

def proc_identity(p):
 s=(p/'stat').read_text();fields=s[s.rfind(')')+2:].split();return dict(pid=int(p.name),startticks=int(fields[19]),state=fields[0],ppid=int(fields[1]),pgid=int(fields[2]),sid=int(fields[3]))


def owner_scan(roots,allowlist):
 patterns=[re.compile(re.escape(str(p))+r'(?=/|\s|$|[\"\x27])') for p in roots];matches=[];races=[];skipped=[];service_skips=[]
 def hit(value):return any(pattern.search(value) for pattern in patterns)
 for p in Path('/proc').glob('[0-9]*'):
  try:
   before=proc_identity(p);status=(p/'status').read_text();uids=next(l.split()[1:] for l in status.splitlines() if l.startswith('Uid:'));euid=int(uids[1])
   if euid!=PRODUCER_UID:
    skipped.append(dict(pid=int(p.name),startticks=before['startticks'],comm=(p/'comm').read_text().strip(),euid=euid));continue
   comm=(p/'comm').read_text().strip();identity=dict(pid=before['pid'],startticks=before['startticks'],ppid=before['ppid'],comm=comm,euid=euid)
   if identity in allowlist:
    confirmed=proc_identity(p);require(all(confirmed[k]==before[k] for k in ('pid','startticks','ppid')),'service identity changed before exact exemption')
    service_skips.append(dict(identity=identity,scope='ROOT-declared long-lived nonproducer service; inaccessible details not inspected'));continue
   evidence=[]
   for name in ('cwd','exe'):
    try:v=os.readlink(p/name)
    except FileNotFoundError:continue
    if hit(v):evidence.append(dict(kind=name,value=v))
   args=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
   if hit(args):evidence.append(dict(kind='argv',value=args))
   for f in (p/'fd').iterdir():
    try:v=os.readlink(f)
    except FileNotFoundError:continue
    if hit(v):evidence.append(dict(kind='fd',value=v))
   for line in (p/'maps').read_text().splitlines():
    if hit(line):evidence.append(dict(kind='maps',value=line))
   after=proc_identity(p)
   require(before['startticks']==after['startticks'],'PID reuse during ownership scan')
   if evidence:matches.append(dict(identity=after,evidence=evidence))
  except (FileNotFoundError,ProcessLookupError):races.append(int(p.name))
  except PermissionError:raise ValueError('cannot prove UID1001 producer absence due /proc permissions: '+p.name)
 require(not matches,'old pool still has active user: '+json.dumps(matches[:3]))
 return dict(state='PASS no current UID1001 old-pool argv/cwd/exe/fd/maps users; other UIDs out of scope',producer_euid=PRODUCER_UID,not_global_all_UID_absence=True,matches=matches,exited_during_scan=races,other_UID_processes_skipped=skipped,ROOT_exact_nonproducer_services_skipped=service_skips)

