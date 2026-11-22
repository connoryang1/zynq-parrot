#!/usr/bin/env python3
"""Bounded, host-only synthetic checks; never invokes a physical collector."""
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started=time.monotonic();limit=90;remaining=False;failure=None;code=None
    files=[ROOT/'linux-tests'/name for name in (
        'analyze_retained29_capacity_csr_study.py','run_retained29_capacity_csr_study.py',
        'test_analyze_retained29_capacity_csr_study.py','test_run_retained29_capacity_csr_study.py')]
    before={str(p):sha(p) for p in files}
    # Includes the current active cohort's fixed HOME OTHER and 16MiB delta.
    assert shutil.disk_usage(ROOT).free>=2415919104+43305308+16*1024**2+10*1024**2
    assert sum(p.stat().st_size for p in HERE.rglob('*') if p.is_file())<1024**2
    with tempfile.TemporaryDirectory(prefix='csr-capacity-study-host-') as td:
        temp=Path(td);log=temp/'host-tests.log'
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=td)
        def limits():
            resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2)
            resource.setrlimit(resource.RLIMIT_FSIZE,(8*1024**2,)*2)
            resource.setrlimit(resource.RLIMIT_CPU,(60,)*2)
        argv=[sys.executable,'-B','-m','unittest','-v',
              'test_analyze_retained29_capacity_csr_study','test_run_retained29_capacity_csr_study']
        with log.open('wb') as stream:
            child=subprocess.Popen(argv,cwd=ROOT/'linux-tests',stdout=stream,stderr=subprocess.STDOUT,
                env=env,start_new_session=True,preexec_fn=limits)
            try:
                while child.poll() is None:
                    if time.monotonic()-started>limit:raise RuntimeError('fixed90s host gate deadline')
                    if sum(p.stat().st_size for p in temp.rglob('*') if p.is_file())>8*1024**2:raise RuntimeError('fixed8MiB isolated output cap')
                    if shutil.disk_usage(ROOT).free<2415919104+43305308+18*1024**2:raise RuntimeError('host reserve')
                    time.sleep(.1)
                code=child.wait()
            except BaseException as error:failure=repr(error)
            finally:
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                child.wait(timeout=5)
                try:os.killpg(child.pid,0);remaining=True
                except ProcessLookupError:remaining=False
        (HERE/'host-tests.log').write_bytes(log.read_bytes())
    after={str(p):sha(p) for p in files}
    proof=dict(scope='TEST ONLY synthetic host qualification; no board/vendor/model/reader',
        argv=argv,returncode=code,failure=failure,elapsed_s=time.monotonic()-started,
        wall_limit_s=limit,cpu_limit_s=60,address_space_limit_bytes=256*1024**2,
        isolated_output_cap_bytes=8*1024**2,owned_group_remaining=remaining,
        sources_unchanged=before==after,sources=before,log_sha256=sha(HERE/'host-tests.log'))
    (HERE/'host-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof,indent=2))
    assert code==0 and failure is None and not remaining and before==after


if __name__=='__main__':main()
