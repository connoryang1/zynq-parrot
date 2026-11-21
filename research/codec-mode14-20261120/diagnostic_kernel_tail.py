#!/usr/bin/env python3
"""Diagnostic-only console-tail extension; delegate all board ownership unchanged.

Use the existing five positional session arguments before its options. The
output basename must contain "diagnostic". No new guest/runtime flag is added.
"""
from datetime import datetime,timezone
import hashlib
import inspect
import json
from pathlib import Path
import shutil
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'linux-tests'))
import pexpect
import run_resume_workload_session as session
import run_scheduler_pipe_hint as guest
from run_scheduler_tagged_replay import KERNEL_FAILURE_MARKER

BASE_SPAWN=pexpect.spawn
TAIL_SECONDS=20.0
MATCH_FIELDS=('before','after','match','match_index')


def binding(path):
    path=Path(path);b=path.read_bytes()
    return dict(path=str(path.resolve()),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


class KernelTailSpawn(BASE_SPAWN):
    """Keep the original kernel-failure outcome after one bounded tail drain."""
    def expect_list(self,pattern_list,timeout=-1,searchwindowsize=-1,async_=False,**kw):
        outcome=super().expect_list(pattern_list,timeout,searchwindowsize,async_,**kw)
        if (not isinstance(outcome,int) or not 0<=outcome<len(pattern_list)
                or pattern_list[outcome] is not KERNEL_FAILURE_MARKER
                or getattr(self,'_diagnostic_tail_done',False)):
            return outcome
        self._diagnostic_tail_done=True
        original={name:getattr(self,name) for name in MATCH_FIELDS}
        started=time.monotonic()
        event=dict(kind='kernel-failure-tail',limit_seconds=TAIL_SECONDS,end='interrupted',
                   original_outcome=outcome,original_failure=original['match'].group(0))
        try:
            # Reading through the original pexpect engine preserves its normal
            # logfile_read stream. The failure guard will abort, not resume
            # application processing, after this single observation window.
            tail=super().expect_list([pexpect.EOF,pexpect.TIMEOUT],timeout=TAIL_SECONDS)
            event['end']='eof' if tail==0 else 'timeout' if tail==1 else 'unexpected-tail-outcome'
        except pexpect.EOF:
            event['end']='eof-exception'
        except pexpect.TIMEOUT:
            event['end']='timeout-exception'
        except Exception as error:
            # A capture error must not replace or disguise the matched kernel
            # failure. Original caller still sees its original failure index.
            event.update(end='capture-error',capture_error=repr(error))
        finally:
            event['elapsed_seconds']=time.monotonic()-started
            for name,value in original.items():setattr(self,name,value)
            events=getattr(self,'diagnostic_events',None)
            if events is not None:events.append(event)
        return outcome


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if len(argv)<5 or any(arg.startswith('-') for arg in argv[:5]):
        raise ValueError('Use existing five positional session arguments before options; diagnostic output basename required')
    output=Path(argv[4]).resolve()
    if 'diagnostic' not in output.name.lower():
        raise ValueError('Output basename must identify diagnostic; never use a performance slot')
    if output.exists():raise FileExistsError('Diagnostic session output must be new')
    admission=json.loads((HERE/'admission.json').read_text())
    source8={relative:binding(ROOT/relative)['sha256'] for relative in session.HOST_SOURCES}
    if source8!=admission['host_sources']:raise ValueError('Base source8 differs from frozen codec study')
    # This separate metadata directory never pre-creates or mutates the actual
    # session output. session.main retains its original lock-before-mkdir rule.
    extra=output.with_name(output.name+'-diagnostic-host')
    extra.mkdir()
    snapshot=extra/Path(__file__).name
    shutil.copyfile(__file__,snapshot)
    events=[]
    record=dict(state='diagnostic-only wrapper starting',diagnostic_only=True,
        excluded_from_performance_inference=True,tail_limit_seconds=TAIL_SECONDS,
        argv_forwarded_unchanged=argv,session_output=str(output),
        extra_source=binding(snapshot),invoked_extra_source=binding(__file__),
        base_source8_sha256=source8,pexpect_version=pexpect.__version__,
        base_expect_source=binding(inspect.getsourcefile(BASE_SPAWN.expect_list)),
        started_utc=datetime.now(timezone.utc).isoformat(),tail_events=events,
        ownership='Unchanged run_resume_workload_session.main owns global/program locks, staging and recovery',
        scope='Observation after exact kernel failure guard only; original failure outcome restored, never promoted to PASS')
    metadata=extra/'diagnostic-wrapper.json'
    def save():metadata.write_text(json.dumps(record,indent=2)+'\n')
    save()
    class SessionTailSpawn(KernelTailSpawn):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self.diagnostic_events=events
    original_spawn=guest.pexpect.spawn
    try:
        guest.pexpect.spawn=SessionTailSpawn
        result=session.main(argv)
        record.update(state='diagnostic delegate returned; excluded from performance',delegate_return=result)
        return result
    except BaseException as error:
        record.update(state='diagnostic delegate failed; excluded from performance',delegate_error=repr(error))
        raise
    finally:
        guest.pexpect.spawn=original_spawn
        record.update(ended_utc=datetime.now(timezone.utc).isoformat(),
            base_source8_unchanged=all(binding(ROOT/r)['sha256']==digest for r,digest in source8.items()),
            extra_source_unchanged=binding(__file__)['sha256']==record['invoked_extra_source']['sha256'])
        save()


if __name__=='__main__':
    raise SystemExit(main())
