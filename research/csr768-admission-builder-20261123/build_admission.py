#!/usr/bin/env python3
"""Bind the sealed768 template into one fresh ROOT-authorized phase; run no tools."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True

PRODUCER = Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr768-native-preparation-20261123')
TEMPLATE = PRODUCER / 'admission.TEMPLATE.json'
TEMPLATE_SHA = 'ec085ffa4f8b544bb63dd8e27ebefc79d55f429aefc8dce5917be1bef3b33278'
TOP = '1b24c915ed628f6d47a382b3aa89fb662884e1a1'
PARENT = '88ab04dfcc508176cc977096ca0c132299a8a460'
BP = '1e7aa2fdc94a56373a26f95b145aff361d4d0aaa'
ACTIONS = dict(source='source-materialization', software='software-preparation',
               preflight='fullcore-preflight', execution='fullcore-execution')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def bind(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def read(path, sha):
    row = bind(path)
    require(row['sha256'] == sha, 'external exact ROOT/input SHA mismatch')
    return row, json.loads(Path(row['path']).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=tuple(ACTIONS), required=True)
    for name in ('profile', 'decision', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('profile', 'decision'):
        parser.add_argument('--'+name+'-sha256', required=True)
    args = parser.parse_args()
    template_row, value = read(TEMPLATE, TEMPLATE_SHA)
    require(value['schema'] == 'csr768-native-admission-v1' and value['ROOT_approved'] is False
            and value['actions'] == [], 'sealed unexecuted768 template only')
    for row in value['inputs']:
        require(bind(row['path']) == row, 'sealed producer/source input drift')
    profile_row, profile = read(args.profile, args.profile_sha256)
    decision_row, decision = read(args.decision, args.decision_sha256)
    require(profile['schema'] == 'csr768-native-resource-profile-v1'
            and profile['ROOT_approved'] is True
            and profile['all_other_charged_reserves_included'] is True
            and profile['TOP'] == TOP and profile['BP'] == BP, 'fresh ROOT768 resource authority')
    require(profile['caps'] == dict(RUN=1073741824, base_HOME=33554432,
            helper_HOME=131072, program_inside_RUN=8388608), 'unchanged native caps')
    require(decision['ROOT_verified'] is True and decision['proceed_768_native_validation'] is True
            and decision['TOP'] == TOP and decision['BP'] == BP and decision['parent'] == PARENT,
            'actual ROOT768 decision must name immediate1280 parent')
    evidence = decision['based_on_1280_placement_and_capture']
    require(type(evidence) is dict and set(evidence) == {'terminal', 'complete_preservation'},
            'actual1280 terminal and complete preservation bindings required')
    for row in evidence.values():
        require(bind(row['path']) == row, 'actual predecessor evidence drift')
    require(profile['basis_records'], 'ROOT global reserve/funding basis required')
    for row in profile['basis_records']:
        require(bind(row['path']) == row, 'actual resource basis drift')
    value.update(ROOT_approved=True, actions=[ACTIONS[args.phase]],
        ROOT_resource_profile=profile_row, ROOT_capacity_selection=decision_row,
        state='ROOT bound one prospective768 phase; no execution or result inferred')
    value['inputs'] += [template_row, bind(__file__)]
    output = args.output.resolve()
    require(output.parent.is_dir() and not output.exists() and not output.is_symlink(),
            'fresh output in existing ROOT-funded authority directory only')
    require(output != PRODUCER and PRODUCER not in output.parents,
            'never write inside sealed producer helper prefix')
    raw = (json.dumps(value, indent=2)+'\n').encode()
    with output.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    print(json.dumps(bind(output), sort_keys=True))


if __name__ == '__main__':
    main()
