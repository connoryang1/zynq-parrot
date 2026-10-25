#!/usr/bin/env python3
"""Report address-tagged D-cache preview buffer events from fst2vcd input.

The trace samples pre-edge signals at the D-cache clock. It reports accepted
response writes, word consumption, and store/L1 invalidation with the prior
slot owner, so a published response is not mistaken for a retained target.
"""

import argparse
import json
import sys

from cache_overlap_vcd import EvidenceError, rising_edges
from prefetch_overlap_vcd import read_header


DCACHE = 'core_minimal.be.calculator.pipe_mem.dcache.'
SIGNALS = {
    'final_publish': 'blackparrot.dcache_preview_publish',
    'clock': DCACHE + 'clk_i',
    'reset': DCACHE + 'reset_i',
    'write': DCACHE + 'prefetch_buffer_write',
    'write_slot': DCACHE + 'prefetch_buffer_write_slot',
    'write_match': DCACHE + 'prefetch_buffer_write_match',
    'write_addr': DCACHE + 'data_mem_pkt_cast_i.addr',
    'write_yumi': DCACHE + 'data_mem_pkt_yumi_o',
    'hit': DCACHE + 'prefetch_buffer_hit_tv',
    'hit_slot': DCACHE + 'prefetch_buffer_hit_slot_tv',
    'load_addr': DCACHE + 'paddr_tv_r',
    'load_valid': DCACHE + 'v_tv_r',
    'store': DCACHE + 'decode_tv_r.store_op',
    'l1_hit': DCACHE + 'cache_load_hit_tv',
    'valid_slots': DCACHE + 'prefetch_buffer_v_r',
}
for slot in range(5):
    SIGNALS[f'addr{slot}'] = DCACHE + f'prefetch_buffer_addr_r[{slot}]'
    SIGNALS[f'words{slot}'] = DCACHE + f'prefetch_buffer_word_v_r[{slot}]'


def report(stream):
    selected, timescale = read_header(stream, SIGNALS)
    events = []
    for cycle, timestamp, value in rising_edges(stream, selected):
        if value.get('reset') != 0:
            continue
        valid = value.get('valid_slots')
        if valid is None:
            raise EvidenceError('unknown side-buffer validity')
        write = value.get('write') == 1 and value.get('write_yumi') == 1
        hit = value.get('hit') == 1
        addr = value.get('load_addr')
        for slot in range(5):
            if not (valid & (1 << slot)):
                continue
            old_segment = value.get(f'addr{slot}')
            if old_segment is None:
                raise EvidenceError('unknown valid slot address')
            old_addr = old_segment << 4
            if hit and value.get('hit_slot') == slot:
                events.append(dict(cycle=cycle, timestamp=timestamp,
                                   kind='consume', address=addr, slot=slot,
                                   old_address=old_addr,
                                   words_before=value.get(f'words{slot}')))
            if (value.get('load_valid') == 1
                    and (value.get('store') == 1 or value.get('l1_hit') == 1)
                    and addr is not None and addr >> 4 == old_segment):
                events.append(dict(cycle=cycle, timestamp=timestamp,
                                   kind='invalidate', address=addr, slot=slot,
                                   reason='store' if value.get('store') == 1 else 'l1_hit'))
        if write:
            slot = value.get('write_slot')
            write_addr = value.get('write_addr')
            if slot is None or slot >= 5 or write_addr is None:
                raise EvidenceError('unknown accepted preview write')
            old_addr = value.get(f'addr{slot}')
            matched = value.get('write_match') == 1
            events.append(dict(cycle=cycle, timestamp=timestamp,
                               kind='publish' if value.get('final_publish') == 1
                               else 'response_word',
                               address=write_addr, segment_address=write_addr & ~15,
                               slot=slot,
                               matched_existing=value.get('write_match') == 1,
                               displaced_address=(old_addr << 4 if valid & (1 << slot)
                                                  and not matched else None)))
    return dict(timescale=timescale, sampling='pre-edge D-cache clock', events=events)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=('response_word', 'publish', 'consume', 'invalidate'))
    args = parser.parse_args()
    try:
        data = report(sys.stdin)
    except EvidenceError as error:
        parser.error(str(error))
    if args.kind:
        data['events'] = [item for item in data['events'] if item['kind'] == args.kind]
    print(json.dumps(data, indent=2))


if __name__ == '__main__':
    main()
