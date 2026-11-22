"""Classify the completed read-only clock diagnostic and preserve every byte."""
from pathlib import Path
import collections
import csv
import datetime
import hashlib
import json
import os
import shutil
import subprocess

OUT = Path(__file__).resolve().parent
WORK = Path('/run/user/1001/zp-csr256-post-synth-clock-diagnostic02-20261122-01')
SOURCE = Path('/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/csr-post-synth-area-controls02-diagnostic-20261122')
TAG = 'black_parrot_bd_1_i/top_0/inst/top/inst/top_fpga_inst/bb/tag_clk_reg/data_r_reg[0]'
CORE = 'clk_out1_vps_bd_1_clk_wiz_0_0'
TIMER = 'clk_out2_vps_bd_1_clk_wiz_0_0'
CAP = 32 * 1024**2


def bind(p):
    return dict(path=str(p), bytes=p.stat().st_size,
                sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def save(p, value):
    assert not p.exists(), p
    p.write_text(json.dumps(value, indent=2) + '\n')


def endpoint_set(path):
    return sorted(line.strip() for line in path.read_text().splitlines()
                  if line.startswith('black_parrot_bd_1_i/'))


def inventory():
    rows = []
    for label, root in [('WORK', WORK), ('SOURCE', SOURCE)]:
        for p in sorted([root, *root.rglob('*')]):
            s = p.lstat()
            row = dict(root=label, relative=str(p.relative_to(root)), mode=s.st_mode,
                       device=s.st_dev, inode=s.st_ino, mtime_ns=s.st_mtime_ns,
                       ctime_ns=s.st_ctime_ns)
            if p.is_symlink():
                row.update(kind='link', bytes=s.st_size, target=os.readlink(p))
            elif p.is_file():
                row.update(kind='file', **bind(p))
            else:
                assert p.is_dir()
                row['kind'] = 'directory'
            rows.append(row)
    return rows


def main():
    assert sorted(p.name for p in OUT.iterdir()) == ['classify_close.py']
    session = json.loads((WORK / 'session.json').read_text())
    assert session['state'].startswith('PASS closed two read-only')
    assert session['source_and_DCP_endcheck'] == 'PASS'
    assert not session['ownership_final']['owned_group_remaining']
    assert session['global_vendor_at_end'] == []
    assert not Path('/proc/1358549').exists()
    assert subprocess.run(['pgrep', '-af', '(^|/)(vivado|xvlog|xelab|xsim)( |$)'],
                          capture_output=True).returncode == 1
    assert shutil.disk_usage(OUT).free > 1879048192 + 134217728 + 61327708 + CAP
    entry, baseline = WORK / 'entry', WORK / 'baseline'
    rows = list(csv.DictReader((entry / 'clock-sinks.tsv').open(), delimiter='\t'))
    other = list(csv.DictReader((baseline / 'clock-sinks.tsv').open(), delimiter='\t'))
    assert len(rows) == len(other) == 34766
    for name in ['clocks.tsv', 'ports.tsv', 'constraints.xdc', 'blackboxes.txt', 'sink-signatures.tsv']:
        assert (entry / name).read_bytes() == (baseline / name).read_bytes(), name
    assert not (entry / 'blackboxes.txt').read_bytes()
    tag = [r for r in rows if r['class'] == 'UNEXPLAINED']
    assert len(tag) == 42
    for r in tag:
        assert r['region'] == 'SHELL' and r['cell_ref'] in ['FDRE', 'FDSE']
        assert r['direct_drivers'] == TAG + '/Q'
        assert r['fanin_startpoints'] == TAG + '/C'
    tagpins = sorted(r['pin'] for r in tag)
    oldtag = [r for r in other if r['class'] == 'UNEXPLAINED']
    assert sorted(r['pin'] for r in oldtag) == tagpins
    for r in oldtag:
        assert r['direct_drivers'] == TAG + '_0_BUFG_inst/O'
        assert r['fanin_startpoints'] == TAG + '/C'
    noclock = endpoint_set(entry / 'check-no-clock.rpt')
    unconstrained = endpoint_set(entry / 'check-unconstrained.rpt')
    assert noclock == tagpins == endpoint_set(baseline / 'check-no-clock.rpt')
    assert len(unconstrained) == 76
    assert unconstrained == endpoint_set(baseline / 'check-unconstrained.rpt')
    tagcells = {p.rsplit('/', 1)[0] for p in tagpins}
    assert all(p.rsplit('/', 1)[0] in tagcells for p in unconstrained)
    for arm in [entry, baseline]:
        assert 'root clock pin: ' + TAG + '/Q (HIGH)' in (arm / 'check-no-clock.rpt').read_text()
        assert 'checking constant_clock (0)' in (arm / 'check-constant-clock.rpt').read_text()
    static = [r for r in rows if r['class'].startswith('STATIC_')]
    assert len(static) == 41
    assert static == [r for r in other if r['class'].startswith('STATIC_')]
    assert collections.Counter(r['cell_ref'] for r in static) == dict(PS7=19, DSP48E1=11, MMCME2_ADV=3, RAMB36E1=8)
    assert all(r['logic_value'] == 'zero' and r['direct_drivers'].endswith('/GND/G') for r in static)
    core = [r for r in rows if r['region'] == 'CORE' and r['class'] == 'CLOCKED']
    assert len(core) == 16390 and all(r['clock_domains'] == CORE for r in core)
    dual = [r for r in rows if ',' in r['clock_domains']]
    assert len(dual) == 128
    assert all(r['region'] == 'PROCESSOR' and '/clints/mtime_gray/' in r['pin']
               and r['clock_domains'] == CORE + ',' + TIMER for r in dual)
    special = [r for r in rows if r['class'] == 'CLOCKED'
               and r['clock_domains'] not in [CORE, CORE + ',' + TIMER]]
    assert len(special) == 2 and all(r['cell_ref'] == 'MMCME2_ADV' for r in special)
    policy = dict(schema='root-observed-csr256-clock-policy-v1',
                  scope='Bounded area controls only; preserve existing clock coverage, not timing signoff or a new waiver',
                  full_entry_sink_table=bind(entry / 'clock-sinks.tsv'),
                  full_baseline_sink_table=bind(baseline / 'clock-sinks.tsv'),
                  exact_clock_table=bind(entry / 'clocks.tsv'), exact_ports=bind(entry / 'ports.tsv'),
                  exact_constraints=bind(entry / 'constraints.xdc'),
                  tag_source_Q=TAG + '/Q', tag_fanin_timing_startpoint_C=TAG + '/C',
                  tag_direct_driver_observed_variants=[TAG + '/Q', TAG + '_0_BUFG_inst/O'],
                  exact_tag_no_clock_pins=tagpins,
                  exact_tag_unconstrained_pins=unconstrained,
                  exact_static_zero_rows=static,
                  exact_clint_dual_domain_rows=dual, exact_MMCM_clock_rows=special,
                  core_domain=CORE, processor_other_domain=CORE,
                  no_new_unexplained_clock_sinks=True,
                  tag_differences_require_ROOT_review=True,
                  static_or_dual_domain_additions_require_ROOT_review=True,
                  input_XDC_byte_identity_required=True,
                  postopt_XDC_differences_require_ROOT_review=True,
                  no_create_clock_or_new_false_paths=True,
                  static_note='Direct GND and unchanged pin identities observed, not inferred zero. DSP register configuration not collected; no new DSP clock exemption authorized.',
                  baseline_limits='42 existing programming-clock pins and76 endpoints remain reported. All76 endpoints belong to those42 tag cells. Final qualification must retain this explicit attribution; no claim of zero unconstrained endpoints.')
    before = inventory()
    assert sum(r.get('bytes', 0) for r in before) + 1024**2 < CAP
    for label, root in [('WORK', WORK), ('SOURCE', SOURCE)]:
        shutil.copytree(root, OUT / label, symlinks=True)
    for r in before:
        p = OUT / r['root'] / r['relative']
        assert p.lstat().st_mode == r['mode']
        if r['kind'] == 'file':
            assert bind(p)['sha256'] == r['sha256'] and p.stat().st_size == r['bytes']
        elif r['kind'] == 'link':
            assert os.readlink(p) == r['target']
    assert inventory() == before
    save(OUT / 'inventory.json', before)
    save(OUT / 'ROOT-clock-policy.json', policy)
    save(OUT / 'complete.json', dict(schema='root-ro-clock-diagnostic02-closure-v1',
         utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), state=session['state'],
         elapsed_seconds=session['elapsed_seconds'], inventory=bind(OUT / 'inventory.json'),
         policy=bind(OUT / 'ROOT-clock-policy.json'), analysis_source=bind(Path(__file__).resolve()),
         all_original_bytes_preserved=True, stable_original_identities=True,
         every_member_hash_mode_link_verified=True, owned_groups_remaining=False,
         worker_pid1358549_absent=True, global_vendor_processes=[],
         old_future_RUN_HOME_bytes=0, old_caps_unchanged=True, actual_originals_retained=True,
         closure_inside_original_HOME_cap_bytes=CAP, no_optimization_or_physical_operations=True))
    assert sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()) < CAP
    print(json.dumps(bind(OUT / 'complete.json')))
    print(json.dumps(bind(OUT / 'ROOT-clock-policy.json')))


if __name__ == '__main__':
    main()
