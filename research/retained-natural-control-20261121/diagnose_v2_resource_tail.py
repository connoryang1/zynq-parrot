#!/usr/bin/env python3
"""Read-only resource diagnosis; never executes a target or accepts partial work."""
import collections
import gzip
import json
from pathlib import Path
import subprocess
import threading
import time
from prepare import bind, HERE, ROOT


def blocks(path):
    """Section framing from the installed, bound fstapi.c reader (big-endian)."""
    size = path.stat().st_size
    rows = []
    pos = 0
    with path.open('rb') as f:
        while pos + 9 <= size:
            f.seek(pos)
            b = f.read(25)
            kind, length = b[0], int.from_bytes(b[1:9], 'big')
            row = dict(offset=pos, kind=kind, section_bytes=length + 1)
            if kind in (1, 5, 8):
                begin, end = int.from_bytes(b[9:17], 'big'), int.from_bytes(b[17:25], 'big')
                row.update(begin_tick=begin, end_tick=end)
                if end > begin:
                    row.update(clock_periods=(end-begin)/50000,
                               bytes_per_clock_period=(length+1)*50000/(end-begin))
            rows.append(row)
            if not length or kind == 255 or pos + 1 + length > size:
                break
            pos += 1 + length
    return rows


def main():
    out = HERE / 'failed-resource-v2-01'
    out.mkdir(exist_ok=False)
    cohort = json.loads((HERE/'cohort-v2-01/cohort.json').read_text())
    assert cohort['state'] == 'STOPPED-failure-preserved-no-retry'
    assert len(cohort['runs']) == 1 and cohort['runs'][0]['returncode'] == -25
    trace = cohort['runs'][0]['trace']
    assert bind(trace['path']) == trace
    spec = json.loads((HERE/'retention-selection.json').read_text())['fields']
    paths = {k:spec[k]['path'] for k in ('be_clock','be_reset','global_cycle','instret','pc')}
    be = paths['pc'].split('.calculator.')[0]
    for n in ('exception', '_interrupt', 'npc_w_v', 'npc'):
        paths[n] = be+'.commit_pkt.'+n
    selection = out/'selection.tsv'
    selection.write_text(''.join(k+'\t'+p+'\n' for k,p in paths.items()))
    reader = ROOT/'research/retained-system-geometry-20261121/reader/fst_events'
    command = [str(reader), trace['path'], str(selection)]
    mapping, values, changes = {}, {}, {}
    stamp = None
    seen_reset = False
    whole_started = False
    exception_events = []
    retired_counts = collections.Counter()
    last = None
    end = False
    error = None
    periods = collections.Counter()
    last_edge_tick = None

    def val(k):
        raw = values.get(k, 'x')
        return None if any(c in raw.lower() for c in 'xz') else int(raw, 2)

    def group():
        nonlocal seen_reset, whole_started, last, last_edge_tick
        new = dict(values)
        new.update(changes)
        if values.get('be_clock') == '0' and new.get('be_clock') == '1':
            if last_edge_tick is not None:
                periods[stamp-last_edge_tick] += 1
            last_edge_tick = stamp
            if val('be_reset'):
                seen_reset = True
            elif seen_reset:
                pc, cycle = val('pc'), val('global_cycle')
                if val('instret'):
                    if pc == 0x80000236:
                        whole_started = True
                    if pc in (0x80000000,0x80000236,0x8000044a,0x8000063a,0x8000079a):
                        retired_counts[hex(pc)] += 1
                    last = dict(cycle=cycle, pc=hex(pc))
                if whole_started and (val('exception') or val('_interrupt')):
                    exception_events.append(dict(cycle=cycle, pc=hex(pc),
                                                 exception=val('exception'), interrupt=val('_interrupt'),
                                                 npc_write=val('npc_w_v'), npc=hex(val('npc'))))
        values.update(changes)
        changes.clear()

    start = time.monotonic()
    with gzip.open(out/'selected-events.tsv.gz', 'wt') as saved, (out/'reader.stderr').open('w') as err:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=err, text=True)
        timer = threading.Timer(120, proc.kill)
        timer.daemon = True
        timer.start()
        try:
            for line in proc.stdout:
                saved.write(line)
                p = line.rstrip('\n').split('\t')
                if p[0] == '#SIGNAL':
                    mapping.setdefault(int(p[3]), []).append(p[1])
                elif p[0] == '#END':
                    group()
                    end = True
                elif p[0].isdigit():
                    tick = int(p[0])
                    if stamp is not None and tick != stamp:
                        group()
                    stamp = tick
                    for k in mapping[int(p[1])]:
                        changes[k] = p[2]
            if changes:
                group()
        except BaseException as e:
            error = repr(e)
            proc.kill()
        finally:
            rc = proc.wait()
            timer.cancel()
    rows = blocks(Path(trace['path']))
    data = [r for r in rows if 'bytes_per_clock_period' in r]
    result = dict(state='PARTIAL-UNFINALIZED-resource-diagnostic-only',
                  scope='No completion, checksum acceptance, full-access audit, capacity or performance result. Reader EOF covers only recoverable bytes.',
                  trace=trace, cohort=bind(HERE/'cohort-v2-01/cohort.json'), source=bind(__file__),
                  reader=bind(reader), selection=bind(selection), command=command, bound_seconds=120,
                  reader_returncode=rc, reader_end_marker=end, error=error,
                  elapsed_seconds=time.monotonic()-start, last_retired=last,
                  selected_label_counts=dict(retired_counts),
                  exceptions_or_interrupts_after_visible_whole_begin=exception_events,
                  observed_be_period_ticks=dict(periods),
                  fst_framing_source=bind('/home/coyang/zynq-parrot/install/share/verilator/include/gtkwave/fstapi.c'),
                  complete_vc_sections=len(data),
                  peak_section_bytes_per_cycle=max(r['bytes_per_clock_period'] for r in data),
                  last_complete_section=data[-1], sections=rows,
                  trace_unchanged_after=bind(trace['path']) == trace,
                  selected_events=bind(out/'selected-events.tsv.gz'))
    (out/'diagnostic.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('state','reader_returncode','reader_end_marker','error',
          'elapsed_seconds','last_retired','selected_label_counts','exceptions_or_interrupts_after_visible_whole_begin',
          'observed_be_period_ticks','complete_vc_sections','peak_section_bytes_per_cycle','last_complete_section')},indent=2))


if __name__ == '__main__':
    main()
