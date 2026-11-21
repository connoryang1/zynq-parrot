#!/usr/bin/env python3
"""Run one canonical reservation and retain its actual subprocess outcome."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

import retention_operations as operations

OPERATIONS_SHA = '77f84b2e48249e0c01db8fafd4a639a15e65a5844967bb704bc2ef4397c12230'
TABLE_SHA = '2251c7a46c685d48aa2c80b4b55c1a75a556d6029737e86f28475f29cc634640'
ABSENT_PROOF = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/retention-absent46-20261121/functional-admission.json')


def now():
    return datetime.now(timezone.utc).isoformat()


def start_ticks():
    # The parenthesized comm field may contain spaces; field3 follows it.
    return int(Path('/proc/self/stat').read_text().rsplit(') ', 1)[1].split()[19])


def run_one(slot, provenance, dependency_records):
    """No retries, recovery, shell interpolation, or performance decisions."""
    receipt = Path(slot['supervisor_receipt'])
    output = Path(slot['session_manifest']).parent
    receipt.parent.mkdir(parents=True, exist_ok=True)
    if receipt.exists() or output.exists():
        raise FileExistsError('Receipt/session already exists; preserve and review it')
    # Atomic per-slot claim prevents duplicate producers before either wrapper
    # has acquired the physical-board lock. Claims are retained, never reused.
    with receipt.with_suffix('.claim').open('x') as claim:
        claim.write(json.dumps(dict(pid=os.getpid(), start_ticks=start_ticks(), argv=slot['argv'])) + '\n')
    record = dict(label=slot['label'], argv=slot['argv'], session_manifest=slot['session_manifest'],
                  pid=os.getpid(), start_ticks=start_ticks(), started_utc=now(),
                  state='failed', runner_exit=None, **provenance)
    error = None
    try:
        result = subprocess.run(slot['argv'], check=False)
        record['runner_exit'] = result.returncode
        if result.returncode != 0:
            raise RuntimeError('Serialized wrapper returned nonzero; inspect its recovery before any next action')
        session = json.loads(Path(slot['session_manifest']).read_text())
        if session.get('state') != 'complete' or 'released_utc' not in session:
            raise RuntimeError('Wrapper exit0 lacks complete/released session evidence')
        for binding in dependency_records:
            if operations.frozen.artifact(Path(binding['path'])) != binding:
                raise RuntimeError('Supervisor dependency changed: ' + binding['path'])
        record['state'] = 'complete'
    except BaseException as caught:
        error = caught
        record['error'] = repr(caught)
    finally:
        record['finished_utc'] = now()
        # Exactly one claimed producer can create this ending receipt. Keep a
        # partial write as a refusal if the host itself fails during writing.
        with receipt.open('x') as stream:
            stream.write(json.dumps(record, indent=2) + '\n')
    if error is not None:
        raise error
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label', choices=('pilot', 'R1a', 'R1b', 'F1a', 'F1b', 'F2a', 'F2b', 'R2a', 'R2b'))
    args = parser.parse_args(argv)
    if operations.frozen.sha(Path(operations.__file__)) != OPERATIONS_SHA or operations.frozen.sha(operations.TABLE) != TABLE_SHA:
        raise ValueError('Reviewed operations/table changed')
    _, _, _, slots, bindings = operations.inputs()
    index = next(i for i, slot in enumerate(slots) if slot['label'] == args.label)
    proof = json.loads(ABSENT_PROOF.read_text())
    if proof.get('state') != 'bounded absent capability functional gate PASS':
        raise ValueError('Bounded unsupported-hardware gate has not passed')
    if proof['session']['path'] != str(ABSENT_PROOF.parent / 'session.json'):
        raise ValueError('Wrong bounded compatibility session')
    operations.frozen.reverify_bindings(proof)
    bindings += [operations.frozen.artifact(ABSENT_PROOF), operations.frozen.artifact(Path(__file__))]
    if index:
        previous = operations.complete_prefix(slots[index - 1]['label'])
        if previous['next_argv'] != slots[index]['argv']:
            raise ValueError('Completed prefix does not authorize this fixed slot')
        bindings += previous['bindings']
    provenance = dict(operations_source_sha256=OPERATIONS_SHA, argv_table_sha256=TABLE_SHA,
                      validator_source_sha256=operations.VALIDATOR_SHA,
                      producer=operations.frozen.artifact(Path(__file__)),
                      bounded_absent_gate=operations.frozen.artifact(ABSENT_PROOF),
                      ownership='Only unchanged serialized wrapper owns physical reservation and recovery')
    return run_one(slots[index], provenance, bindings)


if __name__ == '__main__':
    raise SystemExit(main())
