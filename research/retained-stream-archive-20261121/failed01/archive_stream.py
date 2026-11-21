#!/usr/bin/env python3
"""Archive a complete validator input as a digest plus an explicit counter projection.

The validator receives every original byte, decoded without rewriting. The projection
is supplemental and never represents a full selected-signal archive. No FST is read
by this helper; a future reader integration must supply its actual completion status.
"""
import argparse
import gzip
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

COUNTERS = ('obs.hits', 'obs.published', 'obs.beats')
CAP = 32 * 1024 * 1024
RESERVE = 3 * 1024**3


def require(ok, message):
    if not ok:
        raise ValueError(message)


def bind(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
            size += len(chunk)
    return dict(path=str(path), bytes=size, sha256=digest.hexdigest())


def verify(record):
    require(bind(record['path']) == record, 'binding changed: ' + record['path'])


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def resource_guard(root, start, timeout):
    require(time.monotonic() - start < timeout, 'fixed replay deadline')
    used = sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    require(used <= CAP, 'combined qualification output cap32MiB')
    require(shutil.disk_usage(root).free >= RESERVE + CAP - used,
            'HOME3GiB plus remaining output reserve')


class FullStream:
    """One pass: exact-byte digest and projection; yield every line to the parser."""
    def __init__(self, stream, saved, guard=lambda: None):
        self.stream, self.saved, self.guard = stream, saved, guard
        self.digest = hashlib.sha256()
        self.bytes = self.lines = self.events = self.ends = 0
        self.handles = {}
        self.counter_events = 0
        self.exhausted = False

    def __iter__(self):
        for raw in self.stream:
            require(isinstance(raw, bytes) and len(raw) <= 1024 * 1024,
                    'bounded original binary lines required')
            self.digest.update(raw)
            self.bytes += len(raw)
            self.lines += 1
            if self.lines % 512 == 1:
                self.guard()
            line = raw.decode('ascii')
            fields = line.rstrip('\n').split('\t')
            keep = False
            if fields[0] == '#FST':
                keep = True
            elif fields[0] == '#SIGNAL' and fields[1] in COUNTERS:
                require(len(fields) == 5 and fields[2] == '32' and
                        fields[1] not in self.handles, 'exact counter declaration')
                self.handles[fields[1]] = int(fields[3])
                require(len(set(self.handles.values())) == len(self.handles),
                        'counter handles must be distinct')
                keep = True
            elif fields[0] == '#END':
                require(raw == b'#END\n' and self.ends == 0, 'one exact original EOF')
                self.ends += 1
                keep = True
            elif not fields[0].startswith('#'):
                self.events += 1
                if len(fields) == 3 and int(fields[1]) in self.handles.values():
                    self.counter_events += 1
                    keep = True
            if keep:
                self.saved.write(raw)
            # No event/declaration/address/time/data filtering before validation.
            yield line
        self.exhausted = True
        self.guard()

    def finish(self, reader_returncode):
        require(self.exhausted and self.ends == 1 and set(self.handles) == set(COUNTERS),
                'complete raw stream and three counter declarations')
        require(reader_returncode == 0, 'actual source reader must have completed0')
        return dict(sha256=self.digest.hexdigest(), bytes=self.bytes, lines=self.lines,
                    events=self.events, counter_events=self.counter_events,
                    exact_end_records=self.ends, reader_returncode=reader_returncode)


def validate_complete(stream, saved, selected, validator, edges, reader_returncode, guard=lambda: None):
    traced = FullStream(stream, saved, guard)
    for t, clocks, values in edges(traced, selected):
        validator.sample(t, clocks, values)
    digest = traced.finish(reader_returncode)
    return validator.finish(), digest


def load_auditor(source_dir, profile):
    sys.path.insert(0, str(Path(source_dir).resolve()))
    audit = importlib.import_module('audit')
    chosen = audit if profile == 64 else importlib.import_module('audit1280')
    require(len(audit.selection()) == 167, 'unchanged complete167 selection')
    sources = [bind(source_dir / name) for name in
               ('audit.py', 'audit1280.py', 'build.py', 'generate.py', 'check_counter_words.py')]
    sources.append(bind(audit.original.__file__))
    return audit, chosen, sources


def check_chain(out):
    """Future gates must call this in addition to accepting the validator proof."""
    out = Path(out)
    close = json.loads((out / 'acceptance.json').read_text())
    require(close['schema'] == 'complete167-counter-projection-qualification-v1', 'archive schema')
    for record in close['files'] + close['input_bindings'] + close['sources']:
        verify(record)
    full = json.loads((out / 'verification.json').read_text())
    adapter_path = out / 'counter-check-input/verification.json'
    adapter = json.loads(adapter_path.read_text())
    counter = json.loads((out / 'counter-words.json').read_text())
    require(adapter['schema'] == 'counter-projection-input-only-v1', 'explicit projection adapter')
    require(adapter['full_audit'] == bind(out / 'verification.json'), 'adapter to complete audit chain')
    require(adapter['bindings']['run'] == full['bindings']['run'] == counter['run'], 'same exact native run')
    require(adapter['bindings']['events'] == full['archive']['counter_projection'] == counter['events'],
            'explicit projection binding')
    require(counter['audit'] == bind(adapter_path), 'unchanged checker used projection adapter')
    require(counter['auditor'] in close['sources'], 'unchanged counter checker bound')
    require(full['archive']['full_stream']['reader_returncode'] == 0 and
            full['archive']['full_stream']['exact_end_records'] == 1, 'complete stream receipt')
    require(full['bindings']['fst'] in close['input_bindings'], 'complete rawFST retained and verified')
    require(close['semantic_equality'] is True, 'full semantic proof must match accepted original')
    original = json.loads(Path(close['original_audit']['path']).read_text())
    semantic = {k: v for k, v in full.items() if k not in ('bindings', 'archive')}
    require(semantic == {k: v for k, v in original.items() if k != 'bindings'}, 'complete semantic equality')
    return close


def qualify(args):
    start = time.monotonic()
    audit, chosen, sources = load_auditor(args.source_dir, args.profile)
    before = bind(args.audit / 'verification.json')
    old = json.loads(Path(before['path']).read_text())
    for record in old['bindings'].values():
        verify(record)
    require(old['bindings']['auditor']['sha256'] == bind(chosen.__file__)['sha256'],
            'same original validator class bytes')
    require(old['bindings'].get('inherited_auditor', old['bindings']['auditor'])['sha256'] ==
            bind(audit.__file__)['sha256'], 'same original inherited validator bytes')
    program = json.loads(Path(old['bindings']['program']['path']).read_text())
    run = json.loads(Path(old['bindings']['run']['path']).read_text())
    args.out.mkdir(parents=True, exist_ok=False)
    guard = lambda: resource_guard(args.budget_root, start, args.timeout)
    guard()
    projection = args.out / 'gp0-counter-projection.tsv.gz'
    with gzip.open(old['bindings']['events']['path'], 'rb') as stream, gzip.open(projection, 'wb') as saved:
        result, digest = validate_complete(stream, saved, audit.selection(),
            chosen.Validator(program, run['role']), audit.edges, 0, guard)
    require(result == {k: v for k, v in old.items() if k != 'bindings'},
            'byte-identical complete semantic proof (excluding only original bindings)')
    for record in old['bindings'].values():
        verify(record)
    verify(before)
    result['bindings'] = {k: v for k, v in old['bindings'].items() if k != 'events'}
    result['archive'] = dict(schema='full-stream-digest-with-counter-projection-v1',
        full_stream=digest, counter_projection=bind(projection), source_stream=old['bindings']['events'],
        qualification='Host replay of accepted complete reader output; no new reader/model/target.',
        limits='Projection contains only three counters, not the full167 trace. Raw FST and full selection retained.')
    full_path = args.out / 'verification.json'
    write_json(full_path, result)
    adapter = args.out / 'counter-check-input'
    adapter.mkdir()
    write_json(adapter / 'verification.json', dict(schema='counter-projection-input-only-v1',
        full_audit=bind(full_path), bindings=dict(events=bind(projection), run=old['bindings']['run'])))
    command = [sys.executable, str(args.source_dir / 'check_counter_words.py'),
               '--audit', str(adapter), '--out', str(args.out / 'counter-words.json')]
    with (args.out / 'counter-checker.log').open('w') as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=30)
    guard()
    files = [bind(p) for p in sorted(args.out.rglob('*')) if p.is_file()]
    inputs = list(old['bindings'].values()) + [before]
    write_json(args.out / 'acceptance.json', dict(
        schema='complete167-counter-projection-qualification-v1', semantic_equality=True,
        original_audit=before, files=files, input_bindings=inputs,
        sources=sources + [bind(__file__)], elapsed_s=time.monotonic()-start,
        limits='Archive qualification only; no1792 re-audit, new model, target, FPGA or performance claim.'))
    check_chain(args.out)
    guard()
    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', required=True, type=Path)
    parser.add_argument('--source-dir', required=True, type=Path)
    parser.add_argument('--profile', required=True, type=int, choices=(64, 1280))
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--budget-root', required=True, type=Path)
    parser.add_argument('--timeout', type=int, required=True, choices=(600, 3600))
    args = parser.parse_args()
    require(args.budget_root.resolve() in args.out.resolve().parents, 'owned output under budget root')
    require(args.timeout == (600 if args.profile == 64 else 3600), 'historical profile deadline fixed before replay')
    def interrupted(signum, frame):
        raise RuntimeError('bounded host replay interrupted: ' + str(signum))
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM):
        signal.signal(signum, interrupted)
    signal.alarm(args.timeout)
    try:
        print(json.dumps(qualify(args), sort_keys=True))
    except BaseException:
        accepted = args.out / 'acceptance.json'
        if accepted.exists():
            accepted.rename(args.out / 'FAILED-acceptance.json')
        raise
    finally:
        signal.alarm(0)


if __name__ == '__main__':
    main()
