#!/usr/bin/env python3
"""Read closed same-model UART retirements; conditional logging estimate only."""
import collections
import gzip
import json
import math
import re
from prepare import bind, HERE
from test_preparation import fixture


def main():
    source = HERE/'dcache-adapter/closed-integrity02/selected-events.tsv.gz'
    mapping, values, changes = {}, {}, {}
    stamp = None
    entries, finishes = [], []

    def value(k):
        raw = values.get(k, 'x')
        return None if any(c in raw.lower() for c in 'xz') else int(raw, 2)

    def group():
        new = dict(values)
        new.update(changes)
        if values.get('clock') == '0' and new.get('clock') == '1' and value('reset') == 0 and value('commit_v'):
            pc, cycle = value('commit_pc'), value('global_cycle')
            if pc == 0x80005848:
                entries.append(cycle)
            if pc == 0x800057bc:
                finishes.append(cycle)
        values.update(changes)
        changes.clear()

    keep = {'clock', 'reset', 'commit_v', 'commit_pc', 'global_cycle'}
    with gzip.open(source, 'rt') as f:
        for line in f:
            p = line.rstrip('\n').split('\t')
            if p[0] == '#SIGNAL' and p[1] in keep:
                mapping.setdefault(int(p[3]), []).append(p[1])
            elif p[0] == '#END':
                group()
            elif p[0].isdigit():
                tick = int(p[0])
                if stamp is not None and stamp != tick:
                    group()
                stamp = tick
                for k in mapping.get(int(p[1]), []):
                    changes[k] = p[2]
        if changes:
            group()
    # Fixture rows have the exact successful-path fields. Every target hex value
    # uses the fixed18-character bp_hprint_uint64, unlike Python's short hex().
    target_text = fixture().split('CORE PASS')[0]
    target_text = re.sub(r'0x[0-9a-f]+', '0x'+'0'*16, target_text)
    gaps = [b-a for a,b in zip(entries, entries[1:])]
    result = dict(scope='Closed same-model other-program UART service observation; conditional resource planning, not a bound on a different program or performance result.',
                  source=bind(__file__), input=bind(source),
                  prior_complete_session=bind(HERE/'../retained-system-geometry-20261121/full-system1280-native0-03-runtime01/session.json'),
                  old_cprint_entry_pc='0x80005848', old_finish_entry_pc='0x800057bc',
                  cprint_entries=len(entries), first_cprint_cycle=entries[0], last_cprint_cycle=entries[-1],
                  finish_entry_cycles=finishes,
                  consecutive_cprint_gap_histogram=dict(sorted(collections.Counter(gaps).items())),
                  maximum_consecutive_cprint_gap_cycles=max(gaps),
                  new_successful_guest_characters=len(target_text),
                  new_tail_cycles_at_old_maximum_character_gap=len(target_text)*max(gaps),
                  limitations=['Old gaps include caller work and are observations, not worst-case service bounds.',
                               'No target execution/recompile. Actual MMIO backpressure, faults and final idle polling can exceed this planning envelope.',
                               'New successful UART begins only after WHOLE and all checks; no printed row or sum was observed in the capped natural run.'])
    (HERE/'reporting-tail-estimate-v2.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('cprint_entries','first_cprint_cycle','last_cprint_cycle','finish_entry_cycles','maximum_consecutive_cprint_gap_cycles','new_successful_guest_characters','new_tail_cycles_at_old_maximum_character_gap')},indent=2))


if __name__ == '__main__':
    main()
