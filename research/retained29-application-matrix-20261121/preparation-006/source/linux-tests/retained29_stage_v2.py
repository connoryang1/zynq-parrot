"""Read-only stage inventory and allocation planning for the ABI29 v2 client.

No function in this module uploads, deletes, loads an overlay, or acquires a
second reservation. The caller must already hold the common session flock.
"""
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import shlex
import tarfile

import retained29_protocol as p

REMOTE_BASE='/home/xilinx/zynq-parrot/cosim/black-parrot-example'
REMOTE_ZYNQ=REMOTE_BASE+'/zynq'
SUFFIXES=('bit','hwh','map')
MUTATION_RESERVE_BYTES=16*1024*1024
MUTATION_RESERVE_INODES=16

# Executed only by an explicitly launched serialized supervisor, via read-only
# SSH. Missing is distinct from unreadable, symlink, changing file, and I/O error.
REMOTE_AUDIT=r'''
import hashlib,json,os,stat,sys
request=json.loads(sys.argv[1]);files={};filesystems={}
for name,path in request.items():
    parent=os.path.dirname(path);fs=os.statvfs(parent);device=os.stat(parent).st_dev
    key=str(device)
    row=dict(device=device,allocation_unit=fs.f_frsize,available_bytes=fs.f_bavail*fs.f_frsize,available_inodes=fs.f_favail)
    if key in filesystems:
        filesystems[key]['available_bytes']=min(filesystems[key]['available_bytes'],row['available_bytes'])
        filesystems[key]['available_inodes']=min(filesystems[key]['available_inodes'],row['available_inodes'])
    else:filesystems[key]=row
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    except FileNotFoundError:files[name]=dict(path=path,device=device,missing=True);continue
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):raise ValueError('nonregular inventory file: '+path)
        sha=hashlib.sha256()
        for chunk in iter(lambda:stream.read(1024*1024),b''):sha.update(chunk)
        after=os.fstat(stream.fileno())
    signature=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if signature(before)!=signature(after):raise ValueError('file changed while hashing: '+path)
    files[name]=dict(path=path,device=device,missing=False,bytes=after.st_size,sha256=sha.hexdigest())
print(json.dumps(dict(files=files,filesystems=filesystems),sort_keys=True))
'''


def local_bundle(admission):
    """Bind every member of the already verified local package, not bit alone."""
    artifact=admission['artifacts']['package'];p.verify_binding(artifact)
    package=Path(artifact['path'])
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(package.read_bytes(),validate=False)),mode='r:xz') as archive:
        all_members=archive.getmembers();members=[m for m in all_members if m.isfile()]
        bits=[m for m in members if m.name.endswith('.bit')]
        p.require(len(bits)==1,'exactly one local package bit')
        stem=bits[0].name[:-4];p.require(re.fullmatch(r'[A-Za-z0-9_-]+',stem),'safe local artifact stem')
        p.require(set(m.name for m in members)=={stem+'.'+s for s in SUFFIXES}
                  and len(members)==len(all_members)==3,'exact local BIT/HWH/MAP bundle required')
        bundle={}
        for suffix in SUFFIXES:
            member=archive.getmember(stem+'.'+suffix);data=archive.extractfile(member).read()
            p.require(len(data)>0,'nonempty package member')
            bundle[suffix]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    p.require(bundle['bit']['sha256']==admission['artifacts']['bit']['sha256'],'local bundle bit binding')
    return dict(stem=stem,members=bundle,package=artifact)


def request_paths(admission,bundle,load_stem):
    p.require(re.fullmatch(r'[A-Za-z0-9_-]+',load_stem),'safe load stem')
    nbf=Path(admission['artifacts']['nbf']['path']).name
    package=Path(admission['artifacts']['package']['path']).name
    p.require(re.fullmatch(r'[A-Za-z0-9_.-]+\.nbf',nbf) and re.fullmatch(r'[A-Za-z0-9_.-]+',package),'safe stage names')
    return dict(nbf=REMOTE_ZYNQ+'/'+nbf,package=REMOTE_BASE+'/'+package,
                **{side+'.'+suffix:REMOTE_ZYNQ+'/'+stem+'.'+suffix
                   for side,stem in (('actual',bundle['stem']),('load',load_stem)) for suffix in SUFFIXES})


def inventory_command(admission,bundle,load_stem):
    request=request_paths(admission,bundle,load_stem)
    remote='python3 -c '+shlex.quote(REMOTE_AUDIT)+' '+shlex.quote(json.dumps(request,sort_keys=True))
    return ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',admission['host'],remote]


def expected_files(admission,bundle):
    return dict(nbf=admission['artifacts']['nbf'],package=admission['artifacts']['package'],
                **{side+'.'+suffix:bundle['members'][suffix] for side in ('actual','load') for suffix in SUFFIXES})


def verify_prior_durable_stage(admission,artifact):
    """Closed full-stage log permits read-only reuse before power is removed."""
    p.require(artifact is not None,'read-only cache reuse requires closed durable-stage proof')
    p.verify_binding(artifact);lines=p.clean_lines(Path(artifact['path']).read_text())
    expected=['PACKAGE_OK=1','PACKAGE_SHA256='+admission['artifacts']['package']['sha256'],
              'STAGE_DURABLE_SYNC_OK=1',
              'NBF_OK='+Path(admission['artifacts']['nbf']['path']).name+':'+admission['artifacts']['nbf']['sha256'],
              'BOARD_BIT_SHA256='+admission['artifacts']['bit']['sha256'],'STAGE_OK=1']
    positions=[]
    for marker in expected:
        p.require(lines.count(marker)==1,'closed durable-stage binding missing/duplicate: '+marker)
        positions.append(lines.index(marker))
    p.require(all(a<b for a,b in zip(positions,positions[1:])),'closed durable-stage marker order')


def plan(admission,bundle,load_stem,inventory,rollback=None):
    """Return exact reuse or a conservative peak plan; never silently fall back.

    rollback is required for mutation. Its original member bindings must match
    inventory and durable local copies; restoration temporaries coexist with
    failed target allocations, so their full size is ADDED before reserve.
    """
    paths=request_paths(admission,bundle,load_stem);expected=expected_files(admission,bundle)
    p.require(set(inventory)=={'files','filesystems'} and set(inventory['files'])==set(paths),'exact remote inventory schema')
    matched={};files=inventory['files'];systems=inventory['filesystems']
    for key,path in paths.items():
        row=files[key];p.require(row['path']==path and str(row['device']) in systems,'remote path/filesystem binding')
        p.require(type(row['missing']) is bool,'explicit missing status')
        if row['missing']:
            p.require(set(row)=={'path','device','missing'},'missing remote file fields');matched[key]=False
        else:
            p.require(set(row)=={'path','device','missing','bytes','sha256'} and type(row['bytes']) is int and row['bytes']>=0
                      and re.fullmatch(r'[0-9a-f]{64}',row['sha256']),'remote file fields')
            matched[key]=all(row[k]==expected[key][k] for k in ('bytes','sha256'))
    for key,fs in systems.items():
        p.require(str(fs['device'])==key and type(fs['allocation_unit']) is int and fs['allocation_unit']>0
                  and type(fs['available_bytes']) is int and fs['available_bytes']>=0
                  and type(fs['available_inodes']) is int and fs['available_inodes']>=0,'remote statvfs fields')
    common=dict(schema='bp-retained29-stage-v2',matched=matched,load_stem=load_stem,paths=paths)
    if all(matched.values()):
        # Stage itself allocates no target bytes/inodes. Subsequent guest logs
        # and board-side program lock are separate; this is not a no-write run.
        return dict(common,action='reuse-complete',stage_nbf=False,stage_required=False,budget={},
                    stage_allocated_bytes=0,stage_allocated_inodes=0,rollback_required=False)
    p.require(rollback is not None,'mutation requires verified original rollback bundle')
    p.require(set(rollback)==set(SUFFIXES),'original rollback triplet')
    for suffix,artifact in rollback.items():
        p.verify_binding(artifact);row=files['load.'+suffix]
        p.require(not row['missing'] and all(row[k]==artifact[k] for k in ('bytes','sha256')),'original loader bundle changed/missing')
    additions={}
    def add(key,size):
        fskey=str(files[key]['device']);fs=systems[fskey];unit=fs['allocation_unit']
        budget=additions.setdefault(fskey,dict(target_bytes=0,target_inodes=0,rollback_bytes=0,rollback_inodes=0))
        budget['target_bytes']+=((size+unit-1)//unit)*unit;budget['target_inodes']+=1
    add('package',admission['artifacts']['package']['bytes'])
    if not matched['nbf']:add('nbf',admission['artifacts']['nbf']['bytes'])
    for suffix in SUFFIXES:
        add('actual.'+suffix,bundle['members'][suffix]['bytes'])
        if load_stem!=bundle['stem']:add('load.'+suffix,bundle['members'][suffix]['bytes'])
        fskey=str(files['load.'+suffix]['device']);unit=systems[fskey]['allocation_unit']
        budget=additions[fskey];budget['rollback_bytes']+=((rollback[suffix]['bytes']+unit-1)//unit)*unit
        budget['rollback_inodes']+=1
    for fskey,budget in additions.items():
        budget['required_bytes']=budget['target_bytes']+budget['rollback_bytes']+MUTATION_RESERVE_BYTES
        budget['required_inodes']=budget['target_inodes']+budget['rollback_inodes']+MUTATION_RESERVE_INODES
        budget['available_bytes']=systems[fskey]['available_bytes'];budget['available_inodes']=systems[fskey]['available_inodes']
        p.require(budget['available_bytes']>=budget['required_bytes'],'insufficient stage/rollback bytes on filesystem '+fskey)
        p.require(budget['available_inodes']>=budget['required_inodes'],'insufficient stage/rollback inodes on filesystem '+fskey)
    return dict(common,action='stage-package-only' if matched['nbf'] else 'stage-package-and-nbf',
                stage_nbf=not matched['nbf'],stage_required=True,budget=additions,rollback_required=True)


def helper_argv(admission,decision,scripts):
    p.require(decision['stage_required'],'cache hit must not invoke stage helper')
    argv=[str(scripts/'stage_pynq_artifacts.sh'),admission['artifacts']['package']['path'],admission['host']]
    if decision['stage_nbf']:argv.append(admission['artifacts']['nbf']['path'])
    return argv
