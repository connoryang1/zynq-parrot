#!/usr/bin/env python3
"""Read-only replay of closed clone proofs; no model, reader, compiler or vendor invocation."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sig(row):
    return {k: row[k] for k in ('bytes', 'sha256')}


def digest(f, size=None):
    h, n = hashlib.sha256(), 0
    while size is None or n < size:
        block = f.read(1048576 if size is None else min(1048576, size - n))
        if not block:
            break
        h.update(block)
        n += len(block)
    require(size is None or n == size, 'complete bounded read')
    return dict(bytes=n, sha256=h.hexdigest())


def bound(row):
    with Path(row['path']).open('rb') as f:
        require(digest(f) == sig(row), 'unchanged closed file ' + row['path'])


def ar_members(path):
    """Read GNU archive records without executing ar or evaluating object code."""
    rows, names = {}, b''
    with Path(path).open('rb') as f:
        require(f.read(8) == b'!<arch>\n', 'ordinary GNU archive')
        while True:
            header = f.read(60)
            if not header:
                break
            require(len(header) == 60 and header[58:] == b'`\n', 'complete archive header')
            name, size = header[:16].decode().strip(), int(header[48:58])
            if name == '//':
                names = f.read(size)
                require(len(names) == size, 'full long-name table')
            elif name == '/':
                require(len(f.read(size)) == size, 'full archive symbol index')
            else:
                if name.startswith('/'):
                    start = int(name[1:]); end = names.index(b'/\n', start)
                    name = names[start:end].decode()
                else:
                    name = name.rstrip('/')
                require(name not in rows, 'unique archive member')
                rows[name] = digest(f, size)['sha256']
            if size % 2:
                require(f.read(1) == b'\n', 'archive padding')
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--external', action='store_true', help='also hash sealed external files/objects and compare complete RAM canonical bodies')
    args = ap.parse_args()
    m = json.loads((HERE / 'manifest.json').read_text())
    data = {}
    for role, row in m['inputs'].items():
        p = HERE / row['file']; raw = p.read_bytes()
        require(dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()) == sig(row), 'exact snapshot ' + role)
        data[role] = raw
    def obj(role):
        return json.loads(data[role])
    archive = obj('archive'); flow = obj('proof/flow.json')
    build = obj('proof/build/evidence/build.json'); qual = obj('proof/qualification01/qualification.json')
    final = obj('final-supervision'); old = obj('proof/qualify-supervision.json')
    require(m['inputs']['archive']['sha256'] == m['archive_sha256'] == '91cf86e4d25e81c68e910e23f3e00057104611e4585b8cf5d6e9d39b11d30b1d', 'ROOT compact archive')
    require(m['inputs']['final-supervision']['sha256'] == '9444e4555a4f0b9224aef18a5a38b4f46e175ac1bf8d23bedbb9b8dace1ac963' and final['state'] == 'PASS separate qualify', 'actual final supervision')
    require(old['state'] == 'RUNNING ROOT-approved qualify' and 'ownership' not in old, 'earlier RUNNING snapshot remains distinct')
    require(final['ownership']['returncode'] == 0 and final['ownership']['failure'] is None and not final['ownership']['owned_group_remaining'], 'actual owner completed')
    require(m['inputs']['proof/flow.json']['sha256'] == '2757435fe9f5d9f3e20067fea60640456c27e13e50b5dc5dc21660b4ee876274' and flow['state'].startswith('PASS-one-matched256'), 'closed flow')
    require(m['inputs']['proof/qualification01/qualification.json']['sha256'] == '31dd37473171f7f849238f3065cbc86a0fe14dae5145e471582817b88bbe51bf' and qual['state'].startswith('PASS-matched256'), 'closed qualification')
    require(build['original_model']['sha256'] == build['baseline_relink']['sha256'] == '695e53dccdf418dac6e40ec1c652752e82fb7187c834dbd689ac80233445a80c', 'untouched relink byte-identical')
    require(build['binary']['sha256'] == archive['model']['sha256'] == '6a4214d9b03574d0d0f75ab210e7c91dc447897eba5bee465965370a3dc433e0', 'qualified observation binary')
    changed = [k for k in build['initial_copy'] if sig(build['initial_copy'][k]) != sig(build['final_copy'][k])]
    require(sorted(changed) == sorted(build['changed_files']), 'actual changed-file set')
    syms = 'Vbsg_nonsynth_zynq_testbench__Syms'
    require(sorted(changed) == sorted(['Vbsg_nonsynth_zynq_testbench', 'Vbsg_nonsynth_zynq_testbench__ALL.a', syms + '.cpp', syms + '.d', syms + '.o']), 'only filter source/dependency/object/archive/link outputs change')
    require(set(build['original_members']) == set(build['final_members']) and len(build['final_members']) == 129, 'same evaluation archive members')
    require([k for k in build['original_members'] if build['original_members'][k] != build['final_members'][k]] == [syms + '.o'], 'only one archive member changes')
    seven = ['bsg_nonsynth_dpi_clock_gen.o', 'main.o', 'ps.o', 'verilated.o', 'verilated_dpi.o', 'verilated_fst_c.o', 'verilated_threads.o']
    require(all(sig(build['initial_copy'][k]) == sig(build['final_copy'][k]) for k in seven), 'seven host/evaluation objects immutable')
    filtered = gzip.decompress(data['filtered-Syms']); extra = data['proof/build/evidence/inserted-filter.txt']
    require(filtered.count(extra) == 1, 'one exact filter insertion')
    original = filtered.replace(extra, b'', 1)
    require(dict(bytes=len(original), sha256=hashlib.sha256(original).hexdigest()) == sig(build['initial_copy'][syms + '.cpp']), 'Syms source differs ONLY by exact filter insertion')
    require(dict(bytes=len(filtered), sha256=hashlib.sha256(filtered).hexdigest()) == sig(build['final_copy'][syms + '.cpp']), 'filtered Syms source')
    proposal = obj('proof/records/proposal.json')
    require(proposal['original_TOP'] == '1008854d30e5d923c86c3232fc22af039467d552' and proposal['original_BP'] == 'bb575a764c200f07c6f3259a179bdc861dd7593f', 'matched256 frozen source')
    require(len(proposal['writer_leaves']) == 415 and extra.count(b'dumpvars(1,') == 415, 'exact415 leaf filter')
    expected_extra = '        // Observation-only whole-callback selection; evaluation is unchanged.\n'
    expected_extra += ''.join('        __Vm_dumperp->dumpvars(1, ' + json.dumps(r['path']) + ');\n' for r in proposal['writer_leaves'])
    needle = b'        __Vm_modelp->trace(__Vm_dumperp, 0, 0);\n'
    require(extra == expected_extra.encode() and original.count(needle) == 1 and original.replace(needle, needle + extra) == filtered, 'exact filter occurs after registration and before open')
    require(filtered.index(needle) < filtered.index(extra) < filtered.index(b'__Vm_dumperp->open('), 'filter ordering')
    admitted = obj('proof/records/admission.json')['inputs']
    for role, row in m['inputs'].items():
        if role.startswith('helper/'):
            require(row['path'] in admitted and sig(row) == sig(admitted[row['path']]), 'exact admitted qualification helper source')
    require(sig(m['inputs']['reader-source']) == sig(obj('reader-build')['sources'][0]) and obj('reader-build')['executable']['sha256'] == proposal['reader']['sha256'] == 'a9227fe2368ab376b7700a08e044b81c18261432dadeb89e8baeafab021f7541', 'reader source/build identity retained')
    domain_counts = dict(core252=252, observer_and_geometry=45, SP_strict162=162, capacity167=167, actual_geometry17=17)
    require({k: len(v) for k, v in proposal['domains'].items()} == domain_counts and set(qual['domains']) == set(domain_counts), 'five complete schemas including17params')
    require(qual['guest']['returncode'] == -6 and qual['guest']['counter_values'] == ['1', '1', '1', '1', '8', '8'], 'actual one cold08 return/counters')
    log = data['proof/qualification01/runtime/run.log'].decode()
    require(log.index('[BSG-PASS]') < log.index('CORE PASS') < log.index('Returning from ps_main with RC: 0') < log.index('BSG PASS') < log.index('final block executed before fini() was called'), 'precise post-completion GPIO finalizer')
    strict = obj('proof/qualification01/strict/verification.json')
    require(strict['accepted'] is True and len(strict['cold_function_retirement']) == 16, 'closed strict full512 proof')
    for lane in ('i', 'd'):
        row = strict['lanes'][lane]; require(len(row['hits']) == len(row['publications']) == len(row['bursts']) == 1, 'one publication/hit/refill')
        insert, burst = row['publications'][0]['insert'], row['bursts'][0]
        require(not burst['aborted'] and not burst['errors'] and len(burst['beats']) == 8, 'real nonaborted eight-word restore')
        for i, beat in enumerate(burst['beats']):
            require(beat['word'] == i and beat['bank'] == (burst['way'] + i) % 8 and beat['address'] == insert['address'] + 8 * i, 'all eight actual bank writes')
            require(beat['data'] == (insert['data'] >> (64 * i)) & ((1 << 64) - 1), 'full512 payload equality')
    ip = strict['lanes']['i']['publications'][0]['insert']
    require([(r['pc'], r['instruction']) for r in strict['cold_function_retirement']] == [(ip['address'] + 4 * i, (ip['data'] >> (32 * i)) & 0xffffffff) for i in range(16)], 'all16 ordered retired instructions')
    require(obj('proof/qualification01/observer/verification.json')['firsttouch_counts'] == dict(i=[1, 1, 8], d=[1, 1, 8]), 'independent counter corroboration')
    geometry = obj('proof/qualification01/geometry/verification.json')['facts']
    require(len(geometry['values']) == 17 and geometry['clean_eof'] and geometry['values']['retained_store.storage.i_lines_p'] == geometry['values']['retained_store.storage.d_lines_p'] == 256, 'all17 actual geometry parameters')
    failed, accepted = obj('failed-inventory'), obj('accepted-inventory')
    require(m['inputs']['failed-inventory']['sha256'] == 'b6bb2a5545453d6b6245c2fa45f8f5c331f58b7d43011f0021436dda6e03e565' and failed['partial_listing']['bytes'] == 12 * 1024**2, 'original12MiB metadata failure')
    require(failed['numeric_subcommand_returncode'] == 'Not persisted by inline driver; do not infer exact code' and not failed['owned_reader_processes_remaining'], 'no invented failed-inventory RC')
    require(m['inputs']['accepted-inventory']['sha256'] == 'fc7d7e4cf7b3f7b36d3a1322d0811d6d52c7527934539aa9c07891c5cdd266fa' and accepted['required_count'] == 415 and accepted['owned']['returncode'] == 0 and not accepted['owned']['owned_group_remaining'], 'accepted actual415-path inventory')
    require(m['family_cap'] - m['family_bytes_at_scoped_close'] == m['remaining_reserved_at_scoped_close'] == 19599210 and m['prospective_allslot_bytes_within_same_cap'] == 16 * 1024**2, 'whole64MiB unchanged; allslot16MiB remains prospective within it')
    summaries = {}
    for name, pair in qual['domains'].items():
        ref, clone = pair['reference'], pair['clone']
        keys = ('sha256', 'events', 'changes_by_index', 'first_tick', 'final_tick', 'timescale', 'clean_EOF')
        require(pair['literal_bytes_equal'] and all(ref[k] == clone[k] for k in keys) and ref['clean_EOF'], 'complete domain recorded equivalence')
        require(ref['canonical_file']['sha256'] != clone['canonical_file']['sha256'], 'gzip container difference preserved')
        result = dict(events=ref['events'], payload_sha256=ref['sha256'], compressed_containers_equal=False)
        if args.external:
            for row in (ref['canonical_file'], clone['canonical_file']):
                bound(row)
            h, lines, tail = hashlib.sha256(), 0, b''
            with gzip.open(ref['canonical_file']['path'], 'rb') as x, gzip.open(clone['canonical_file']['path'], 'rb') as y:
                while True:
                    one, two = x.read(1048576), y.read(1048576)
                    require(one == two, 'EVERY decompressed canonical byte equal')
                    if not one:
                        break
                    h.update(one); lines += one.count(b'\n'); tail = (tail + one)[-4:]
            require(h.hexdigest() == ref['sha256'] and tail == b'END\n' and lines == ref['events'] + domain_counts[name] + 2, 'full canonical payload digest/count/END')
            result['independent_literal_payload_comparison'] = True
        summaries[name] = result
    if args.external:
        for row in archive['proof_files']:
            bound(row)
        bound(archive['qualified_rawFST']); bound(archive['gzip']); bound(failed['partial_listing']); bound(accepted['hierarchy'])
        with gzip.open(archive['gzip']['path'], 'rb') as f:
            require(digest(f) == sig(build['binary']), 'durable full scoped binary')
        objdir = Path(build['binary']['path']).parent
        original_obj = Path(build['original_model']['path']).parent
        for name in seven:
            bound(build['final_copy'][name])
        require(ar_members(original_obj / 'Vbsg_nonsynth_zynq_testbench__ALL.a') == build['original_members'], 'all129 actual baseline archive members')
        require(ar_members(objdir / 'Vbsg_nonsynth_zynq_testbench__ALL.a') == build['final_members'], 'all129 actual scoped archive members')
        bound(build['original_model']); bound(build['binary'])
    print(json.dumps(dict(state='PASS independent closed matched256 observation-clone replay',
                          external_closed_bytes_checked=args.external, five_domains=summaries,
                          unchanged_host_objects=7, unchanged_archive_members=128, changed_archive_members=1,
                          final_supervision_preserved=True, earlier_RUNNING_snapshot_preserved=True,
                          canonical_gzip_bodies_archived=False, scope=m['limits']), indent=2))


if __name__ == '__main__':
    main()
