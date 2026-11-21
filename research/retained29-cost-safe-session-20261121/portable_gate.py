#!/usr/bin/env python3
"""Run the COST host suite in a minimal tree without capacity diagnostics."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'linux-tests'))
import retained29_protocol as base
import retained29_cost_protocol as cost

TESTS=('test_retained29_cost_protocol','test_retained29_cost_admission','test_retained29_safe_session')


def run(output):
    output.mkdir()
    names=set(cost.SOURCE_FILES)
    visited=set()
    pending=[ROOT/'linux-tests'/(name+'.py') for name in TESTS]
    while pending:
        path=pending.pop();name=str(path.relative_to(ROOT))
        if name in names and name.startswith('linux-tests/test_'):continue
        # Track every visited module separately: production modules may already
        # be present in SOURCE_FILES but their test-only imports still matter.
        names.add(name)
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            modules=([a.name for a in node.names] if isinstance(node,ast.Import) else
                [node.module] if isinstance(node,ast.ImportFrom) and node.module else [])
            for module in modules:
                candidate=ROOT/'linux-tests'/(module+'.py')
                if candidate.is_file() and str(candidate.relative_to(ROOT)) not in visited:
                    visited.add(str(candidate.relative_to(ROOT)));pending.append(candidate)
    names.update(('linux-tests/resume_workload.h','linux-tests/retained29_regex_workload.h',
        'research/retained-trigger-accounting-20261121/closed-cost01/verification.json',
        'research/retained29-session-preparation-20261121/closed-preparation-002/probe-present.DRAFT.json',
        'research/retained29-session-preparation-20261121/closed-preparation-002/benchmark-functional.DRAFT.json'))
    base.require(not any('capacity' in name for name in names),'capacity dependency in portable import closure')
    with tempfile.TemporaryDirectory(prefix='r29-cost-portable-',dir='/tmp') as tmp:
        copy=Path(tmp);manifest={}
        for name in sorted(names):
            src=ROOT/name;dst=copy/name;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(src.read_bytes())
            record=base.binding(src);manifest[name]=dict(bytes=record['bytes'],sha256=record['sha256'])
        base.require(not (copy/'linux-tests/test_retained_capacity_recovery_v3.py').exists()
            and not list((copy/'research').glob('retained-capacity*')),'capacity artifacts must be absent')
        env={key:value for key,value in os.environ.items() if key not in ('PYTHONPATH','R29_COST_HOST_FIXTURE_DIR')}
        command=[sys.executable,'-B','-m','unittest','-v',*TESTS]
        result=subprocess.run(command,cwd=copy/'linux-tests',env=env,text=True,capture_output=True,timeout=120)
        (output/'stdout.log').write_text(result.stdout);(output/'stderr.log').write_text(result.stderr)
        value=dict(state='PASS isolated portable46 host checks' if result.returncode==0 else 'FAIL isolated portable host checks',
            command=command,returncode=result.returncode,source_tree=manifest,capacity_modules_present=False,
            capacity_research_present=False,pythonpath_removed=True,physical_actions=0,
            scope='Only isolated host mocks/inert ARM bytes; no board calls or target execution.',
            logs={name:base.binding(output/name) for name in ('stdout.log','stderr.log')})
        (output/'verification.json').write_text(json.dumps(value,indent=2)+'\n')
        base.require(result.returncode==0 and 'Ran 46 tests' in result.stderr and result.stderr.rstrip().endswith('OK'),'portable46 gate failed')
        return base.binding(output/'verification.json')


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: portable_gate.py NEW_OUTPUT')
    run(Path(sys.argv[1]).resolve())
