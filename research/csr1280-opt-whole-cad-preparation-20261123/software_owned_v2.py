"""V2 own-group reap before liveness; live descendants remain a failure."""
import ctypes
import os
import signal
import subprocess
import time


class CommandInterrupted(RuntimeError):pass


def group_state(pgid):
    rows=[]
    for path in __import__('pathlib').Path('/proc').glob('[0-9]*/stat'):
        try:
            text=path.read_text();fields=text[text.rfind(')')+2:].split()
            if int(fields[2])==pgid:rows.append(dict(pid=int(path.parent.name),state=fields[0],ppid=int(fields[1]),pgrp=pgid))
        except (FileNotFoundError,ProcessLookupError,PermissionError):pass
    return sorted(rows,key=lambda r:r['pid'])


def run(argv,cwd,env,log,timeout,guard,limits):
    guard();process=None;failure=None;start=time.monotonic();remaining=False;states=[];reaped=[]
    libc=ctypes.CDLL(None,use_errno=True);old=ctypes.c_int()
    if libc.prctl(37,ctypes.byref(old),0,0,0) or libc.prctl(36,1,0,0,0):raise OSError(ctypes.get_errno(),'subreaper ownership')
    def caught(sig,frame):raise CommandInterrupted('software command signal '+str(sig))
    handlers={s:signal.signal(s,caught) for s in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP)}
    def alive():
        try:os.killpg(process.pid,0);return True
        except ProcessLookupError:return False
    def reap_own():
        while True:
            try:pid,status=os.waitpid(-process.pid,os.WNOHANG)
            except ChildProcessError:return
            if pid==0:return
            reaped.append(dict(pid=pid,status=status))
    try:
        process=subprocess.Popen(list(map(str,argv)),cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
        while process.poll() is None:
            guard()
            if time.monotonic()-start>=timeout:raise TimeoutError('fixed software tool deadline')
            try:process.wait(timeout=min(.25,max(.001,timeout-(time.monotonic()-start))))
            except subprocess.TimeoutExpired:pass
        states.append(dict(phase='normal_parent_exit_before_reap',members=group_state(process.pid)))
        reap_own()
        states.append(dict(phase='normal_parent_exit_after_reap',members=group_state(process.pid)))
        if alive():raise RuntimeError('software tool returned with live owned descendants after reap')
        guard()
    except BaseException as error:
        failure=error
        if process is not None:states.append(dict(phase='exception_before_cleanup',members=group_state(process.pid)))
    finally:
        for s in handlers:signal.signal(s,signal.SIG_IGN)
        if process is not None:
            end=time.monotonic()+5
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            try:
                process.wait(timeout=max(.001,end-time.monotonic()))
                while True:
                    reap_own()
                    if not alive():break
                    if time.monotonic()>=end:remaining=True;break
                    time.sleep(.01)
            except BaseException as error:
                if failure is None:failure=error
                remaining=True
        if libc.prctl(36,old.value,0,0,0) and failure is None:failure=OSError(ctypes.get_errno(),'restore subreaper')
        for s,h in handlers.items():signal.signal(s,h)
    if process is not None:states.append(dict(phase='cleanup_complete',members=group_state(process.pid)))
    life=dict(group_states=states,reaped_owned_children=reaped,argv=list(map(str,argv)),owned_pgid=process.pid if process is not None else None,returncode=process.returncode if process is not None else None,
        failure=repr(failure) if failure is not None else None,owned_group_remaining=remaining,
        timeout_s=timeout,teardown_s=5,elapsed_s=time.monotonic()-start)
    if remaining:
        error=RuntimeError('owned software process group remains after5s');error.owned_receipt=life;raise error
    if failure is not None:
        failure.owned_receipt=life
        raise failure
    return life
