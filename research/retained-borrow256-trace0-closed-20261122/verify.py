#!/usr/bin/env python3
"""Replay compact proof and optional archive roundtrips; never interpret FST events."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import tarfile

HERE = Path(__file__).resolve().parent


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(stream):
    h, size = hashlib.sha256(), 0
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        h.update(block)
        size += len(block)
    return dict(bytes=size, sha256=h.hexdigest())


def signature(row):
    return {k: row[k] for k in ('bytes', 'sha256')}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archives', type=Path, help='closed01 directory; verifies every compressed/raw byte')
    args = ap.parse_args()
    manifest = json.loads((HERE / 'manifest.json').read_text())
    data = {}
    for role, row in manifest['inputs'].items():
        path = HERE / row['file']
        raw = gzip.decompress(path.read_bytes()) if row['encoding'] == 'gzip' else path.read_bytes()
        require(dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()) == signature(row), role + ' exact snapshot')
        data[role] = raw
    q, a, bridge = [json.loads(data[k]) for k in ('session', 'archive', 'comparison02')]
    require(manifest['inputs']['session']['sha256'] == 'ccd530d02b959ac6d5da98d7ad08310d4c65c77942724e9e6136473e86542f4b', 'ROOT composite')
    require(manifest['inputs']['archive']['sha256'] == manifest['archive_manifest_sha256'] == '9918f125af54570e183d249d22eef995f8da1d826d4992fcf24e568721669c59', 'ROOT archive')
    require(manifest['inputs']['comparison02']['sha256'] == manifest['comparison_sha256'] == '97a2bea7bb2712f08e81d60b7effe5a8bb73509893051d916387d1e9ebed7785', 'ROOT bridge')
    require(q['state'].startswith('PASS borrow-only trace0') and a['state'].startswith('PASS complete lossless borrowing256'), 'closed PASS receipts')
    require(q['source_tree_baseline'] == '1008854d30e5d923c86c3232fc22af039467d552' and q['source_bp'] == 'bb575a764c200f07c6f3259a179bdc861dd7593f', 'exact source')
    require(q['model']['sha256'] == a['model']['sha256'] == '695e53dccdf418dac6e40ec1c652752e82fb7187c834dbd689ac80233445a80c', 'exact executed model')
    require([r['label'] for r in q['commands']] == ['make-preflight', 'clean', 'build', 'loader', 'integrity-run', 'integrity-checker', 'advisory-run', 'advisory-checker', 'strict', 'counter', 'parameters'], 'all eleven phases')
    require([r['ownership']['returncode'] for r in q['commands']] == [0, 0, 0, 0, -6, 0, -6, 0, 0, 0, 0], 'actual native finalizers retained')
    require(all(r['ownership']['failure'] is None and not r['ownership']['owned_group_remaining'] for r in q['commands']), 'owned process groups closed')
    for role in ('integrity', 'advisory'):
        native = json.loads(data[role + '-native'])
        require(native['state'].startswith('PASS') and native['actual_returncode'] == -6, 'native checker acceptance')
        log = data[role + '-log'].decode()
        require(log.index('[BSG-PASS]') < log.index('CORE PASS') < log.index('Returning from ps_main with RC: 0') < log.index('BSG PASS') < log.index('final block executed before fini() was called'), 'native finalizer follows all completion markers')
    strict, counter = [json.loads(data[k]) for k in ('strict', 'counter')]
    require(strict['accepted'] is True and counter['firsttouch_counts'] == dict(i=[1, 1, 8], d=[1, 1, 8]), 'closed strict/counter proof')
    for lane in ('i', 'd'):
        p = strict['lanes'][lane]
        require(len(p['publications']) == len(p['hits']) == len(p['bursts']) == 1, 'one firsttouch per lane')
        insert, hit, burst = p['publications'][0]['insert'], p['hits'][0], p['bursts'][0]
        require(insert['address'] == hit['lookup']['address'] == burst['request_address'] & ~63, 'address ownership')
        require(not burst['aborted'] and not burst['errors'] and burst['hit'] == hit and len(burst['beats']) == 8, 'actual nonaborted retained restore')
        for word, beat in enumerate(burst['beats']):
            require(beat['word'] == word and beat['address'] == insert['address'] + 8 * word, 'all eight physical words')
            require(beat['bank'] == (burst['way'] + word) % 8, 'all eight SRAM banks')
            require(beat['data'] == (insert['data'] >> (64 * word)) & ((1 << 64) - 1), 'all512 publication/real SRAM bits')
    ip = strict['lanes']['i']['publications'][0]['insert']
    retired = strict['cold_function_retirement']
    require(len(retired) == 16 and [r['pc'] for r in retired] == [ip['address'] + 4 * i for i in range(16)], 'ordered16 retired PCs')
    require([r['instruction'] for r in retired] == [(ip['data'] >> (32 * i)) & 0xffffffff for i in range(16)], 'all16 actual retired instructions match full payload')
    expected = {'retained_store.storage.epoch_width_p': 8, 'retained_store.storage.sets_p': 256,
                'retained_store.storage.i_lines_p': 256, 'retained_store.storage.d_lines_p': 256,
                'l2_block_width_p': 512, 'dcache_block_width_p': 512, 'icache_block_width_p': 512,
                'core_minimal.cache_miss_trace_p': 0, 'l2_sets_p': 64, 'dcache_sets_p': 64,
                'icache_sets_p': 64, 'l2_assoc_p': 2, 'l2_banks_p': 2, 'num_threads_p': 2,
                'num_contexts_p': 4, 'dcache_assoc_p': 8, 'icache_assoc_p': 8}
    params = json.loads(data['parameters'])
    require(params['facts']['values'] == expected and params['facts']['clean_eof'], 'all17 actual parameters')
    require(json.loads(data['generated-geometry'])['facts']['l2'] == dict(slices=1, banks=2, sets_per_bank=64, ways=2, line_bytes=64, data_bytes_per_bank=8192, total_bytes=16384), 'generated STATIC16KiB L2')
    require({k: len(v) for k, v in a['groups'].items()} == dict(sources=766, metadata=49, singles=7) and len(a['archives']) == 9, 'complete archive groups')
    require(a['all_required_data_retained'] and all(r['roundtrip'] for r in a['archives']), 'producer full roundtrips')
    require(manifest['family_allocation'] == a['durable_allocation_bytes'] == 64 * 1024**2 and manifest['family_allocation'] - manifest['family_bytes_at_ROOT_close'] == manifest['remaining_reserved_at_ROOT_close'] == 24791320, 'remaining allocation retained, not released')
    sources = json.loads(data['actual-sources'])['sources']
    archived = {r['path']: signature(r) for r in a['groups']['sources']}
    require(len(sources) == 396 and all(archived[p] == signature(r) for p, r in sources.items()), 'all396 consumed sources archived')
    require(any('Trace' in p for p in archived) and any('Syms' in p for p in archived), 'trace registration/writer and symbols retained')
    meta = {r['path']: signature(r) for r in a['groups']['metadata']}
    require(all(meta[r['log']['path']] == signature(r['log']) for r in q['commands']), 'all phase logs archived')
    require(a['groups']['singles'][0] == {k: q['model'][k] for k in ('path', 'bytes', 'sha256')}, 'full model single retained')
    require(a['released_reservations_before'] == a['released_reservations_after'] and a['closed_scratch_before'] == a['closed_scratch_after'], 'occupied closed inputs unchanged')
    # Compare actual manifest entries; normalize only the two exact source/runtime roots.
    normalized = {}
    for size in ('large', 'small'):
        model = bridge['models'][size]
        session = json.loads(data['large-session'] if size == 'large' else data['session'])
        rows = json.loads(data['large-actual-sources'] if size == 'large' else data['actual-sources'])['sources']
        source = '/home/coyang/zynq-parrot-linux-borrow' + ('256' if size == 'small' else '') + '-profile'
        runtime = str(Path(model['model']['path']).parents[1])
        normalized[size] = {p.replace(source, '<SOURCE>').replace(runtime, '<RUNTIME>'): signature(r) for p, r in rows.items()}
        require(session['model'] == model['model'] and len(normalized[size]) == 396, 'bridge model/source set')
        argv = next(r['argv'] for r in session['commands'] if r['label'] == 'build')
        require([v.replace(source, '<SOURCE>') for v in argv] == bridge['identical_make_build_argv_after_path_normalization'], 'same exact normalized Make argv')
    require(set(normalized['small']) == set(normalized['large']), 'same396 normalized source paths')
    differences = [p for p in normalized['small'] if normalized['small'][p] != normalized['large'][p]]
    require(differences == ['<RUNTIME>/bsg_bootrom.sv'] and bridge['raw_byte_identical_source_count'] == 395, 'only exact bootrom raw difference')
    common = {}
    for size in ('large', 'small'):
        raw = data[size + '-bootrom-sv']; first, rest = raw.split(b'\n', 1)
        exception = bridge['only_generated_comment_exception'][size]
        require(first.decode() == exception['exact_header'], 'exact first generated-path comment only')
        require(dict(bytes=len(rest), sha256=hashlib.sha256(rest).hexdigest()) == exception['common_remainder'], 'entire following SV unchanged')
        require(signature(manifest['inputs'][size + '-bootrom-sv']) == signature(exception['raw']), 'raw ROM source identity')
        common[size] = rest
    require(common['small'] == common['large'] and data['small-bootrom-rom'] == data['large-bootrom-rom'], 'actual ROM/SV body byte equality')
    merged = dict(normalized['small']); merged['<RUNTIME>/bsg_bootrom.sv'] = bridge['only_generated_comment_exception']['small']['common_remainder']
    require(merged == bridge['normalized396_sources'], 'exact recorded bridge signature map')
    require(data['large-design'].replace(b'BP_RETAINED_I_LINES ?= 1792', b'BP_RETAINED_I_LINES ?= 256').replace(b'BP_RETAINED_D_LINES ?= 1792', b'BP_RETAINED_D_LINES ?= 256') == data['small-design'], 'only two source defaults change')
    large_params = json.loads(data['large-parameters'])['facts']['values']
    require({k: v for k, v in large_params.items() if not k.endswith(('.i_lines_p', '.d_lines_p'))} == {k: v for k, v in expected.items() if not k.endswith(('.i_lines_p', '.d_lines_p'))}, 'same noncapacity17 parameters')
    require(json.loads(data['raw-comparison-failure01'])['raw_identical_sources'] == 395, 'initial strict raw refusal preserved')
    verified = []
    if args.archives:
        for row in a['archives']:
            path = args.archives / Path(row['archive']['path']).name
            with path.open('rb') as f:
                require(digest(f) == signature(row['archive']), 'exact compressed archive')
            if 'members' in row:
                with tarfile.open(path, 'r|gz') as tar:
                    count = 0
                    for member in tar:
                        require(count < len(row['members']), 'no extra archive member')
                        expected_member = row['members'][count]
                        require(member.isfile() and member.name == expected_member['member'], 'exact ordered safe member')
                        with tar.extractfile(member) as f:
                            require(digest(f) == signature(expected_member['original']), 'full raw member roundtrip')
                        count += 1
                    require(count == len(row['members']), 'no missing archive member')
            else:
                with gzip.open(path, 'rb') as f:
                    require(digest(f) == signature(row['original']), 'full raw single roundtrip')
            verified.append(path.name)
    print(json.dumps(dict(state='PASS independent compact proof/source bridge replay',
                          archive_roundtrips=len(verified), raw_sources_equal=395, exact_ROM_header_exception=1,
                          full512_lanes=2, real_L1_beats_per_lane=8, ordered_I_instructions=16,
                          retained_remaining_bytes_at_ROOT_close=24791320,
                          scope=manifest['limits']), indent=2))


if __name__ == '__main__':
    main()
