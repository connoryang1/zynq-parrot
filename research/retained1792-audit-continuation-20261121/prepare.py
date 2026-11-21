#!/usr/bin/env python3
"""ROOT-only preparation; never runs a model or FST reader."""
import argparse
import fcntl
import json
import continuation as c


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--approve-continuation', action='store_true')
    args=p.parse_args()
    c.require(args.approve_continuation, 'default offline; explicit ROOT review required')
    stage=c.STAGE
    with (stage/'acquisition.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        c.check_stop()
        original=stage/'preparation.json'
        old,program=c.old.load(original,c.ADMISSION_SHA)
        c.old.check_native(stage,'d-enabled',old,original,c.NATIVE_SHA)
        c.require(not (stage/'d-off').exists() and not (stage/'i-enabled').exists(), 'no later native already started')
        c.require(not c.audit_output(stage,'d-enabled').exists(), 'attempt2 not rerunnable')
        c.require(not (stage/'d-enabled-audit/acceptance.json').exists(), 'failed attempt1 remains failed')
        bridge=dict(schema='retained1792-audit-continuation-v1',
            state='ROOT-APPROVED audit attempt2; inherited native only',
            original_preparation=c.bind(original), inherited_native_sha256=c.NATIVE_SHA,
            failed_attempt=c.bind(c.STOP), caps=c.CAPS, geometry=c.GEOMETRY, sources=c.sources(),
            change=dict(phase='read-only audit only', old_HOME_floor=3*1024**3,
                new_HOME_floor=1024**3,native_HOME_floor=3*1024**3))
        c.validate_bridge(bridge)
        c.AUDIT_PHASE=True
        c.check_budget(stage,old)
        out=stage/'audit-continuation.json'
        with out.open('x') as f: json.dump(bridge,f,indent=2);f.write('\n')
        c.load(out,c.bind(out)['sha256'])
        c.check_budget(stage,old)
    print(json.dumps(c.bind(out),sort_keys=True))


if __name__=='__main__': main()
