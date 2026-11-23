#!/usr/bin/env python3
"""Host build only: ordinary-header no-PCH generation then explicit eight-job make."""
import json,os,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
REAL=Path('/home/coyang/zynq-parrot-linux-research/install/bin/verilator')
def main():
 args=sys.argv[1:]
 if args==['--version']:return subprocess.call([str(REAL)]+args)
 if '--build' not in args:return subprocess.call([str(REAL)]+args)
 args.remove('--build')
 require='--build-jobs' in args and args[args.index('--build-jobs')+1]=='8'
 if not require:raise ValueError('exact eight inner workers')
 generated=[str(REAL)]+args
 print('CSR_NO_PCH_GENERATE '+json.dumps(generated),flush=True)
 rc=subprocess.call(generated)
 if rc:return rc
 obj=Path('obj_dir');mk=obj/'Vbsg_nonsynth_zynq_testbench.mk'
 if not mk.is_file():raise ValueError('actual generated model makefile missing')
 argv=['make','-C',str(obj),'-f',mk.name,'-f',str(HERE/'no-pch.mk'),'-j8','OBJCACHE=']
 print('CSR_NO_PCH_COMPILE '+json.dumps(argv),flush=True)
 rc=subprocess.call(argv,env=dict(os.environ,CCACHE_DISABLE='1',SCCACHE_DISABLE='1',OBJCACHE=''))
 if list(obj.rglob('*.gch')):raise ValueError('PCH forbidden')
 return rc
if __name__=='__main__':sys.exit(main())
