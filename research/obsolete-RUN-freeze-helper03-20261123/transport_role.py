"""Exact established ROOT-declared PTY transport exception; metadata checks only."""
import os
from pathlib import Path
import owner_scan

TRANSPORT=dict(pid=1704225,startticks=102224035,euid=1001,ppid=1704150,comm='sshd',argv=['sshd: coyang@pts/0'])
PARENT=dict(pid=1704150,startticks=102223901,euid=0,ppid=805,comm='sshd',argv=['sshd: coyang [priv]'])
CHILD=dict(pid=1704226,startticks=102224050,euid=1001,ppid=1704225,comm='tmux: client',argv=['tmux','new-session','-A','-s','main'])


def direct_children(pid):
    result=[]
    for entry in Path('/proc').glob('[0-9]*'):
        try:
            row=owner_scan.proc_identity(entry)
        except (FileNotFoundError,ProcessLookupError):
            continue
        if row['ppid']==pid:result.append(row['pid'])
    return sorted(result)


def metadata(expected,children):
    p=Path('/proc')/str(expected['pid'])
    before=owner_scan.proc_identity(p)
    status=(p/'status').read_text()
    uids=next(line.split()[1:] for line in status.splitlines() if line.startswith('Uid:'))
    actual=dict(pid=before['pid'],startticks=before['startticks'],euid=int(uids[1]),
        ppid=before['ppid'],comm=(p/'comm').read_text().strip(),
        argv=[v.decode('utf-8') for v in (p/'cmdline').read_bytes().split(b'\0') if v])
    seen=direct_children(expected['pid'])
    after=owner_scan.proc_identity(p)
    owner_scan.require(actual==expected and sorted(seen)==children,'exact authenticated transport PID/UID/argv/parent/sole-child role differs')
    owner_scan.require(all(before[k]==after[k] for k in ['pid','startticks','ppid','pgid','sid']),
                       'transport identity changed during metadata read')
    return dict(identity=actual,children=sorted(seen),pgid=before['pgid'],sid=before['sid'],child_relation_scope='point-in-time PPID metadata, not continuous monitoring')


def allow_identity():
    return {k:TRANSPORT[k] for k in ['pid','startticks','ppid','comm','euid']}


def check(proof,worker_sha,output):
    owner_scan.require(proof['schema']=='ROOT-authenticated-PTY-tmux-nonproducer-v1'
        and proof['ROOT_verified'] is True and proof['ROOT_fresh_role_declaration_for_this_admission'] is True,
        'fresh ROOT authenticated-role proof required')
    owner_scan.require(proof['worker_sha256']==worker_sha and proof['output']==output,
                       'role exception scoped to this exact worker/output, not a generic sshd exemption')
    owner_scan.require(proof['transport']==TRANSPORT and proof['parent']==PARENT and proof['child']==CHILD,
                       'only the exact ROOT-observed transport chain is admitted')
    owner_scan.require(proof['ROOT_no_sftp_or_oldpool_producer_role'] is True
        and proof['ROOT_acknowledges_FD_maps_uninspected'] is True
        and proof['scope']=='operational unused-RUN write stop; no deletion and all actual files kept',
        'role assumption and uninspected-view limitation must be explicit')
    # No FD/maps/cwd/exe read is claimed for the transport or privileged parent.
    # CHILD is NOT exempted: the unchanged scanner checks it like every user process.
    views=dict(parent=metadata(PARENT,[TRANSPORT['pid']]),
        transport=metadata(TRANSPORT,[CHILD['pid']]),child=metadata(CHILD,[]))
    return views
