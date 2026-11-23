"""Additional exact-image old2dd ownership/source gates; no board operations."""
import json
from pathlib import Path
import retained29_protocol as base

SOURCE_NAMES = ('csr_pair_context.py', 'csr_pair_promotion.py', 'csr_pair_collector.py',
                'csr_pair_within.py', 'csr_pair_analysis.py', 'csr_pair_acquire.py')
TOP = dict(small='a44c03bb7bc520a3b5727c2bb619a055a7ed5acd',
           large='88ab04dfcc508176cc977096ca0c132299a8a460')
BP = '1e7aa2fdc94a56373a26f95b145aff361d4d0aaa'
LINES = dict(small=256, large=1280)
PROJECTS = ('top_ip_proj', 'black_parrot_bd_proj', 'tmp_edit_project')
# New reviewed SOURCE checkpoints must register actual closed evidence. Empty now.
APPROVED_OWNERSHIP = {}
APPROVED_BUILD_BRIDGES = {}
require = base.require


def read(record):
    base.verify_binding(record)
    return json.loads(Path(record['path']).read_text())


def image_for(hardware):
    matches = [image for image, n in LINES.items()
               if hardware['retained'] == dict(i_lines=n, d_lines=n, set_log2=8)]
    require(len(matches) == 1, 'exact matched256/1280 geometry only')
    return matches[0]


def application_ownership(record, image, bit):
    proof = read(record)
    require(APPROVED_OWNERSHIP.get(bit) == record['sha256'],
            'actual exact-image old2dd CMA ownership approval pending')
    require(proof['schema'] == 'csr-pair-old2dd-physical-ownership-v1'
            and proof['state'] == 'PASS root-reviewed actual old2dd CMA extent MMIO lifetime',
            'physical ownership qualification incomplete')
    require(proof['TOP'] == TOP[image] and proof['BP'] == BP and proof['bit_sha256'] == bit,
            'ownership tied to exact source and bit')
    require(proof['runner_sha256'] == base.RUNNER_SHA and proof['helper_sha256'] == base.HELPER_SHA
            and proof['kernel_nbf_sha256'] == base.NBF_SHA, 'exact2dd/de54/kernel29 only')
    require(proof['allocation_bytes'] == 48234496 and proof['owned_bytes'] >= 48234496
            and proof['guest_base'] == 0x80000000 and proof['guest_end_exclusive'] == 0x82e00000,
            'actual owned46MiB extent, not only requested/printed size')
    start, end = proof['physical_base'], proof['physical_end_exclusive']
    require(type(start) is int and type(end) is int and 0 < start < end <= 2**32
            and end - start == proof['owned_bytes'] and start + 48234496 <= end,
            'returned physical range/no addition overflow')
    require(proof['DRAM_base_readback'] == start and proof['uncached_allocation'] is True
            and proof['all_NBF_write_tails_within_owned_extent'] is True
            and proof['FDT_entire_buffer_within_owned_extent'] is True
            and proof['Linux_total_KiB'] == 47104 and proof['DMA32_last_byte'] == 0x82dfffff,
            'actual remap/Linux/loader bound and memory attributes')
    require(proof['exclusive_CMA_lifetime_qualified'] is True
            and proof['postterminal_cleanup_lifetime_qualified'] is True
            and proof['recovery_verified'] is True and proof['application_gp0'] is False,
            'exclusive allocation and cleanup ownership; no per-app GP0 claim')
    for key in ('runner_identity', 'libcma_API_and_driver_identity', 'allocator_extent_evidence',
                'MMIO_and_remap_evidence', 'boot_and_loader_evidence', 'lifetime_and_recovery_evidence'):
        base.verify_binding(proof[key])
    return proof


def physical_context(qualification, hardware, artifacts):
    image = image_for(hardware)
    bit = artifacts['bit']['sha256']
    application_ownership(qualification['application_ownership'], image, bit)
    build = build_bridge(dict(build_control_bridge=qualification['build_control_bridge']))
    require(build['images'][image]['bit_sha256'] == bit, 'same actual matched-build bit')
    profile = read(qualification['source_bridge'])
    require(profile['BP'] == BP and profile['TOP'] == TOP[image]
            and profile['bit_sha256'] == bit, 'same CSR source/physical image context')
    clocks = read(qualification['clock_topology'])
    require(clocks['bit_sha256'] == bit and clocks['core_hz'] == clocks['axi_hz'] == 20000000
            and clocks['timer_hz'] == 8000000, 'actual20MHz/8MHz clocks required')
    require(hardware['l1i_bytes'] == hardware['l1d_bytes'] == 32768
            and hardware['l2_bytes'] == 16384, 'ordinary cache geometry unchanged')
    return qualification


def build_bridge(capacity_bridge):
    record = capacity_bridge['build_control_bridge']
    proof = read(record)
    require(APPROVED_BUILD_BRIDGES.get(record['sha256']) == TOP,
            'explicit nonHDL OPT carrier bridge not registered')
    require(proof['schema'] == 'csr-pair-capacity-plus-opt-carrier-v1'
            and proof['state'] == 'PASS root-reviewed exact nonHDL carrier and actual matched build',
            'actual build-control source bridge missing')
    require(proof['TOPs'] == TOP and proof['BP'] == BP and proof['HDL_changes'] == [],
            'same exact BP/HDL; no new storage/policy change')
    require(proof['changed_files'] == ['cosim/black-parrot-example/Makefile.design',
            'cosim/mk/Makefile.vivado', 'cosim/tcl/vivado-utils.tcl']
            and proof['capacity_default_changes'] == dict(i_lines=[256,1280], d_lines=[256,1280]),
            'two capacity defaults plus only reviewed OPT carrier')
    require(proof['source_diff']['sha256'] == '37b95fb9293539a80900617f6bbb32cb860f449d80b496c772f3cb7ae314d1b5', 'exact raw source-control diff')
    base.verify_binding(proof['source_diff'])
    for key in ('consumed_HDL_equality', 'all_gitlink_identity', 'carrier_only_derivation'):
        base.verify_binding(proof[key])
    expected_options = None
    for image in ('small', 'large'):
        actual = proof['images'][image]
        require(actual['TOP'] == TOP[image] and actual['BP'] == BP, 'exact per-image build source')
        expected = dict(BP_RETAINED_BUFFER=1, BP_RETAINED_I_LINES=LINES[image],
            BP_RETAINED_D_LINES=LINES[image], BP_RETAINED_SETS=256,
            BP_RETAINED_OBSERVE=1, BP_AXI_RESPONSE_DELAY=0, BP_CACHE_MISS_TRACE=0)
        rows = actual['contexts']
        require(len(rows) == 3 and {r['project'] for r in rows} == set(PROJECTS),
                'all three real source/IP/finalBD contexts')
        for row in rows:
            require(row['defines'] == expected and all(type(v) is int for v in row['defines'].values()),
                    'all seven actual defines; capacity only variable')
            base.verify_binding(row['receipt'])
        options = actual['child_options']
        require(set(options) == {'synth', 'opt', 'place', 'phys_opt', 'route', 'threads'}
                and options['opt'] == 'ExploreArea' and options['threads'] == 8,
                'actual complete matched implementation options, not environment assertion')
        for key in ('synth', 'place', 'phys_opt', 'route'):
            require(type(options[key]) is list and bool(options[key]), 'actual full child argv '+key)
        require(expected_options is None or options == expected_options, 'both actual child option sets match')
        expected_options = options
        require(actual['core_hz'] == actual['axi_hz'] == 20000000 and actual['timer_hz'] == 8000000,
                'matched actual clock constraints')
        for key in ('config', 'revision_record', 'XPR', 'child_commands', 'clock_coverage', 'fit_package'):
            base.verify_binding(actual[key])
    return proof
