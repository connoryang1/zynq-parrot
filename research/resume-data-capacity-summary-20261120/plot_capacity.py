#!/usr/bin/env python3
"""Plot hash-bound closed JSON evidence; no trace or target execution."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT/'research/resume-data-reuse-20261120'
CAPACITIES = (0, 4, 16, 32, 64, 128)
EXPECTED = {
    'compact-one-kib-900/dcache-audit/summary.json': '4737a0f447dfaacb11e25b10dd48b743b61f9a80f15acb93463d308546303f1d',
    'compact-one-kib-900/dcache-audit/analysis.json': 'ba4918145528cf26ec0ec506e5bafe568a21ecb60888a30f8399d13990325728',
    'compact-one-kib-900/dcache-audit/manifest.json': '9710919c19fceec66b7f33424563a2b0106629a733cd425c2a2c87e21eae34e3',
    'compact-one-kib-900/session.json': '34f6620eb8918a1901d9676c37a5ce374767a37c2580e3515b8de4870843b001',
    'compact-one-kib-900/trace-metadata.json': '67ff3d79bb12817a528917aa8dc5b55cc2c0bee567108451cd9a608aca7dd3db',
    'compact-thirtytwo-kib/dcache-audit/summary.json': '6cf70e8c497d9f8fb50d50e050847728eb7438e72d6541de0c2caff8b57817eb',
    'compact-thirtytwo-kib/dcache-audit/analysis.json': 'a75dda29c3da07277582f9a882f337fe07f01067a2fd4b5a083c43f64d87f973',
    'compact-thirtytwo-kib/dcache-audit/manifest.json': '41949658aa0ccab468a73358ef05d1105102f2aef371ac9baf95a4a24f826b4a',
    'compact-thirtytwo-kib/session.json': 'ed7512587138883bc6044d30eeb3ce412d710a2d9111bf384f6bc992a929ec0e',
    'compact-thirtytwo-kib/trace-metadata.json': 'e88e3fcf940bf77e5ecc5cb945d89106f642e2218f3b6c1902d6b12bc0f5a519',
}
ELF_SHA = 'f35e5da8dcb527cfa04c16edab0616f1f80a7715c9b05278500799c9b66393dd'
MODEL_SHA = '77f76ae7527c2e9ed796fad48a8344e2dbbc10a5d90a69ccfb829e0bc2754ad5'


def binding(path):
    b = path.read_bytes()
    return dict(path=str(path.resolve()), bytes=len(b), sha256=hashlib.sha256(b).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=HERE)
    out = parser.parse_args().output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    inputs, data = {}, {}
    for relative, expected in EXPECTED.items():
        p = BASE/relative
        inputs[relative] = binding(p)
        assert inputs[relative]['sha256'] == expected, 'closed input changed: '+relative
        data[relative] = json.loads(p.read_text())
    rows, cases = [], []
    for name, kib in (('compact-one-kib-900', 1), ('compact-thirtytwo-kib', 32)):
        summary, report, session = (data[name+'/'+suffix] for suffix in
            ('dcache-audit/summary.json', 'dcache-audit/analysis.json', 'session.json'))
        assert session['state'] == 'pass' and report['validation'] == 'passed'
        assert session['program']['elf']['sha256'] == ELF_SHA and session['model']['sha256'] == MODEL_SHA
        assert session['physical_slots'] == 2 and session['logical_contexts'] == 4
        assert summary['geometry'] == dict(sets=64, ways=8, line_bytes=64, normal_l1_d_bytes=32768)
        assert len(report['requests']) == 64 and summary['all64_independent_target_load_counts_match']
        timed = summary['phases']['timed']
        misses = timed.get('ordinary_misses', timed.get('target_ordinary_misses', 0))
        covered = [report['coverage'][str(c)].get('timed_target_misses_covered', 0) for c in CAPACITIES]
        assert covered == ([0]*6 if kib == 1 else [0, 5, 20, 39, 99, 207])
        assert misses == (0 if kib == 1 else 1680)
        stats = summary['full_program_stats']
        cases.append(dict(footprint_kib_per_actor=kib, timed_target_loads=timed['target_loads'],
            timed_target_normal_l1_hits=timed['normal_l1_hits'], timed_target_ordinary_misses=misses,
            full_program_actual_replacement_evictions=stats.get('actual_replacement_evictions', 0),
            covered_counts=covered))
        for capacity, count in zip(CAPACITIES, covered):
            rows.append(dict(case=name, footprint_kib_per_actor=kib, extra_victim_lines=capacity,
                extra_victim_bytes=capacity*64, timed_target_loads=timed['target_loads'],
                timed_target_normal_l1_hits=timed['normal_l1_hits'], timed_target_ordinary_misses=misses,
                covered_timed_target_ordinary_misses=count,
                full_program_actual_replacement_evictions=stats.get('actual_replacement_evictions', 0),
                source_analysis_sha256=inputs[name+'/dcache-audit/analysis.json']['sha256']))
    with (out/'timed-target-victim-coverage.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
        'axes.spines.top': False, 'axes.spines.right': False, 'pdf.fonttype': 42,
        'svg.fonttype': 'none', 'svg.hashsalt': 'resume-data-capacity-20261120'})
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    fig.subplots_adjust(left=.115, right=.97, top=.85, bottom=.35)
    fig.text(.115, .955, 'Conditional coverage of timed target misses', fontsize=13, weight='bold', va='top')
    fig.text(.115, .900, 'Four private corpora · 2 resident slots / 4 logical actors · normal L1D: 32 KiB', fontsize=9, color='#444444')
    ax.plot(CAPACITIES, cases[1]['covered_counts'], color='#D55E00', marker='D', linewidth=1.7,
        markersize=5, label='32 KiB / actor: 1,680 timed target misses', zorder=3)
    ax.plot(CAPACITIES, cases[0]['covered_counts'], color='#0072B2', marker='o', markerfacecolor='white',
        linestyle=':', linewidth=1.6, markersize=5, label='1 KiB / actor: 0 timed target misses', zorder=4)
    for capacity, count in zip(CAPACITIES[1:], cases[1]['covered_counts'][1:]):
        ax.annotate(str(count), (capacity, count), xytext=(0, 8), textcoords='offset points',
            ha='center', fontsize=9, color='#963C00')
    ax.set(xlim=(-4, 135), ylim=(-8, 235), xticks=CAPACITIES, yticks=(0, 50, 100, 150, 200),
        xlabel='Additional hypothetical victim capacity (64 B lines)',
        ylabel='Covered timed target ordinary\nmisses (count)')
    ax.tick_params(axis='x', labelsize=9)
    ax.grid(axis='y', color='#DDDDDD', linewidth=.6)
    ax.set_axisbelow(True)
    ax.legend(loc='upper left', frameon=False, fontsize=9)
    fig.text(.115, .205, 'Exclusive FIFO address ledger; fixed observed execution with no execution feedback.', fontsize=8.5)
    fig.text(.115, .161, '32 timed requests = 8 ring laps × 4 actors; 64 generated hash queries per request.', fontsize=8.5)
    fig.text(.115, .117, 'Counts only: no speedup or FPGA projection; 1 KiB has no timed miss opportunities.', fontsize=8.5)
    fig.text(.115, .073, 'Hypothetical 64 B victims are not equivalent to the FPGA’s four 16 B D-advisory segments.', fontsize=8.5)
    stem = out/'timed-target-victim-coverage'
    fig.savefig(str(stem)+'.svg', metadata=dict(Title='Conditional timed target miss coverage', Date=None))
    fig.savefig(str(stem)+'.pdf', metadata=dict(Title='Conditional timed target miss coverage',
        Creator='plot_capacity.py / matplotlib', CreationDate=None, ModDate=None))
    fig.savefig(str(stem)+'.png', dpi=300, metadata=dict(Title='Conditional timed target miss coverage'))
    plt.close(fig)
    geometry_proof = ROOT/'research/accepted-cache-geometry-20261120/ffc-initial-parameters.json'
    parameters = json.loads(geometry_proof.read_text())['parameters']
    assert next(v['value'] for k, v in parameters.items() if k.endswith('.l2_banks_p')) == 1
    metadata = dict(purpose='Static scientific conditional miss-count figure from closed audit JSONs only',
        inputs=inputs, plotter=binding(Path(__file__)), cases=cases,
        ffc_geometry_parameter_proof=binding(geometry_proof),
        workload_source={name: binding(BASE/'compact-thirtytwo-kib/source'/name) for name in
            ('testing/mt_resume_data_reuse_benchmark.c', 'linux-tests/resume_workload.h')},
        same_elf_sha256=ELF_SHA, same_model_sha256=MODEL_SHA,
        model=dict(blackparrot_revision='ffc9bd7641bc1d9b3df6cf530f3a432db3ebae57',
            l2_banks=1, l1d_bytes=32768, l1d_sets=64, l1d_ways=8, line_bytes=64,
            resident_slots=2, logical_actors=4, private_corpora=4,
            timed_requests=32, timed_laps=8, generated_queries_per_request=64),
        metric='Covered timed TARGET ordinary miss COUNT, never rate or speedup',
        scope='Exclusive FIFO actual-baseline-eviction address ledger, fixed observed execution, no execution feedback or FPGA projection',
        zero_opportunity_policy='1KiB has zero timed target ordinary misses; plot zero covered counts, no0/0 rate',
        advisory_limit='No equivalence to actual accepted FPGA64B store consisting of four16B segments',
        timings='Excluded: computation/probe counts differ, so ring timings cannot isolate capacity',
        environment=dict(python=platform.python_version(), matplotlib=matplotlib.__version__,
            packages={d.metadata['Name']: d.version for d in importlib.metadata.distributions()
                      if str(d.locate_file('')).startswith('/tmp/resource-capacity-plot-deps')}),
        outputs={p.name: binding(p) for p in out.glob('timed-target-victim-coverage.*')})
    (out/'input-hashes-and-metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    (out/'requirements.txt').write_text('\n'.join(name+'=='+version for name, version in
        sorted(metadata['environment']['packages'].items()))+'\n')
    print(json.dumps(metadata['outputs'], indent=2))


if __name__ == '__main__':
    main()
