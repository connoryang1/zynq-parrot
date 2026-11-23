"""Owned forked accounting process; no scanner shares the parser's GIL."""
from contextlib import contextmanager
import ctypes,json,multiprocessing,os,signal,time,threading
from pathlib import Path
clock=time.monotonic


def require(ok,msg):
    if not ok:raise ValueError(msg)
def identity(pid):
    s=Path('/proc',str(pid),'stat').read_text();f=s[s.rfind(')')+2:].split()
    return dict(pid=pid,pgid=int(f[2]),startticks=int(f[19]))
def group_state(pgid):
    rows=[]
    for p in Path('/proc').glob('[0-9]*/stat'):
        try:
            s=p.read_text();f=s[s.rfind(')')+2:].split()
            if int(f[2])==pgid:rows.append(dict(pid=int(p.parent.name),state=f[0],ppid=int(f[1]),pgid=pgid))
        except (FileNotFoundError,PermissionError,ProcessLookupError):pass
    return rows

def _scanner(pipe,check,owner,nonce):
    os.setsid()
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,signal.SIG_DFL)
    stats=dict(interval_s=.25,poll_gap_limit_s=1,scans=0,max_poll_gap_s=0,max_scan_seconds=0,max_callback_age_s=0)
    prior=None
    def send(kind,**kw):pipe.send(dict(kind=kind,nonce=nonce,**kw))
    try:
        send('ready',identity=identity(os.getpid()))
        final=False
        while True:
            require(identity(owner['pid'])==owner,'accounting owner PID/startticks changed')
            start=clock()
            if prior is not None:
                gap=start-prior;stats['max_poll_gap_s']=max(stats['max_poll_gap_s'],gap);require(gap<=1,'phase resource poll gap over1s')
            prior=start;resources=check();duration=clock()-start
            if isinstance(resources,dict) and 'mutable_output_bytes' in resources:
                value=resources['mutable_output_bytes']
                stats.setdefault('initial_mutable_output_bytes',value)
                stats['max_mutable_output_bytes']=max(stats.get('max_mutable_output_bytes',value),value)
                stats['last_resources']=resources
            stats['max_scan_seconds']=max(stats['max_scan_seconds'],duration);require(duration<=.5,'process accounting scan exceeded0.5s')
            stats['scans']+=1;send('sample',completed=clock(),stats=dict(stats))
            if final:send('done',stats=dict(stats));return
            if pipe.poll(.25):
                command=pipe.recv();require(command==dict(command='final',nonce=nonce),'accounting control message')
                final=True
    except BaseException as e:
        try:send('error',error=repr(e),stats=dict(stats))
        finally:raise
    finally:pipe.close()

@contextmanager
def phase(check,receipt):
    # Fork before the FST reader/its monitor thread exists. The closure is the
    # admitted accounting function; this child never execs a model/tool.
    ctx=multiprocessing.get_context('fork');parent,child=ctx.Pipe(duplex=True)
    lock=threading.Lock()
    nonce=os.urandom(16).hex();owner=identity(os.getpid());proc=None;ready=None;last=None;stats={};done=False;error=None;max_age=0;states=[];reaped=[]
    libc=ctypes.CDLL(None,use_errno=True);previous=ctypes.c_int()
    require(libc.prctl(37,ctypes.byref(previous),0,0,0)==0 and libc.prctl(36,1,0,0,0)==0,'accounting subreaper setup')
    def drain_locked():
        nonlocal ready,last,stats,done
        while parent.poll(0):
            try:msg=parent.recv()
            except EOFError:break
            require(msg.get('nonce')==nonce,'accounting heartbeat nonce')
            kind=msg['kind']
            if kind=='ready':
                ready=msg['identity'];require(ready['pid']==proc.pid and ready['pgid']==proc.pid,'own accounting process group')
            elif kind=='sample':
                require(ready is not None,'heartbeat before ownership');last=msg['completed'];stats=msg['stats']
            elif kind=='done':done=True;stats=msg['stats']
            elif kind=='error':stats=msg['stats'];raise ValueError(msg['error'])
            else:raise ValueError('unknown accounting heartbeat')
    def drain():
        with lock:drain_locked()
    def state_value(key):
        with lock:return {'last':last,'done':done}[key]
    def guard():
        nonlocal max_age
        # Reader-monitor and event-parser callbacks can enter concurrently.
        # A Connection has one byte stream: serialize the COMPLETE poll/recv
        # transaction together with the shared decoded heartbeat state.
        with lock:
            drain_locked();require(last is not None,'no completed accounting snapshot')
            age=clock()-last;max_age=max(max_age,age);require(age<=1,'phase resource snapshot stale over1s')
            require(proc.is_alive(),'accounting process exited before final request')
    try:
        proc=ctx.Process(target=_scanner,args=(child,check,owner,nonce),daemon=True);proc.start();child.close()
        end=clock()+1
        while state_value('last') is None:
            drain();require(proc.is_alive(),'accounting process failed during initial scan');require(clock()<end,'initial accounting snapshot exceeded1s');time.sleep(.005)
        yield guard
        guard()
        with lock:parent.send(dict(command='final',nonce=nonce))
        end=clock()+5
        while not state_value('done'):
            drain()
            if state_value('done'):break
            require(clock()<end,'final accounting/owned cleanup exceeded5s');time.sleep(.005)
        proc.join(timeout=max(.001,end-clock()));require(proc.exitcode==0,'accounting process final nonzero')
    except BaseException as e:error=e;raise
    finally:
        handlers={s:signal.signal(s,signal.SIG_IGN) for s in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP,signal.SIGALRM)}
        try:
            with lock:owned_ready=ready
            remaining=False
            if proc is not None and proc.pid is not None:
                end=clock()+5
                if owned_ready:states.append(dict(phase='before_cleanup',members=group_state(proc.pid)))
                if proc.is_alive():
                    try:
                        if owned_ready:os.killpg(proc.pid,signal.SIGKILL)
                        else:os.kill(proc.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                proc.join(timeout=max(.001,end-clock()))
                while True:
                    try:pid,status=os.waitpid(-proc.pid,os.WNOHANG)
                    except ChildProcessError:break
                    if pid==0:break
                    reaped.append(dict(pid=pid,status=status))
                remaining=bool(group_state(proc.pid)) if owned_ready else proc.is_alive()
                if owned_ready:states.append(dict(phase='after_cleanup',members=group_state(proc.pid)))
                if remaining and error is None:error=RuntimeError('accounting owned group remains')
            with lock:parent.close()
            with lock:
                final_stats=dict(stats);final_age=max_age
            final_stats.update(parent_pipe_serialized=True,failure=repr(error) if error else None,max_callback_age_s=final_age,monitor_kind='separate-owned-process',owned_pgid=proc.pid if owned_ready else None,returncode=proc.exitcode if proc is not None and proc.pid is not None else None,owned_group_remaining=remaining,group_states=states,reaped_owned_children=reaped,teardown_bound_s=5)
            if libc.prctl(36,previous.value,0,0,0) and error is None:
                error=OSError(ctypes.get_errno(),'accounting subreaper restore');final_stats['failure']=repr(error)
            Path(receipt).write_text(json.dumps(final_stats,indent=2)+'\n')
        finally:
            for s,h in handlers.items():signal.signal(s,h)
        if error is not None:raise error
