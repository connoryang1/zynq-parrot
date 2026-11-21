#!/usr/bin/env python3
"""Default-offline safe wrapper for unchanged present and fixed functional roles."""
import argparse
import json
from pathlib import Path

import retained29_safe_functional_protocol as p
import retained29_safe_session as safe
import run_retained29_session as original


def guest(a,core,path,env,runner):return original.run_guest(core,path,env,runner=runner)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('admission',type=Path,nargs='?')
    parser.add_argument('--execute',type=Path);parser.add_argument('--request-recovery',type=Path);args=parser.parse_args(argv)
    if args.request_recovery is not None:
        p.require(args.admission is None and args.execute is None,'recovery-only request has no guest arguments')
        safe.request_recovery(args.request_recovery);return
    p.require(args.admission is not None,'wrapper admission required');a=json.loads(args.admission.read_text())
    if args.execute is not None:safe.execute(a,args.execute,p,guest,admission_record=p.binding(args.admission))
    elif a.get('state')=='DRAFT-UNLAUNCHABLE':print('RETAINED29_SAFE_FUNCTIONAL_DRAFT_UNLAUNCHABLE=1')
    else:p.validate_admission(a);print('RETAINED29_SAFE_FUNCTIONAL_OFFLINE_ADMISSION_OK=1')


if __name__=='__main__':main()
