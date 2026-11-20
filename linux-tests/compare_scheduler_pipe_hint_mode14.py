#!/usr/bin/env python3
"""Compare the reviewed mode-14 late-trigger control across complete boots."""
import argparse
import hashlib
from itertools import zip_longest
import json
from pathlib import Path
import random
import re
import statistics

from analyze_scheduler_pipe_hint import analyze
from analyze_scheduler_tagged_replay import percentile

REVIEW = Path(__file__).resolve().parents[1] / 'research/mode14-early-only-20261120'
BASELINE_SHA = 'ef50be197b458b512f82ed8a9deccc0bdfcfadba760ccd119d67e46837501cf4'
CONTROL_SHA = 'd14dc8b00908bb7c7a310d4c517f31752a9db4f5836b5d60b5d916d596a7847b'
MANIFEST_SHA = 'f5040dc8b5dfd919c7cb446d0e4aa05e5c4704a2b5c705b62f90e9acc3d9067b'
VERIFICATION_SHA = 'def505b65273ff940c4782d7885bf09c49fcf1be84107354a397cadf7d0ed75f'
RECORD_LINE = 1075385
OLD_RECORD = b'03_0000000080a13fe8_1073e0f77de3471d\n'
NEW_RECORD = b'03_0000000080a13fe8_1073e0f77de34721\n'
BOOT = re.compile(r'^\[\s*0\.0+\]\s+Linux version 6\.6(?:\.|\s)', re.MULTILINE)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path):
    return dict(path=str(path.resolve()), sha256=sha(path), bytes=path.stat().st_size)


def _verify_nbf_pair(baseline, control):
    """Hash every byte and reject any difference except the reviewed record."""
    old_hash, new_hash = hashlib.sha256(), hashlib.sha256()
    changed = []
    with baseline.open('rb') as old, control.open('rb') as new:
        for number, (a, b) in enumerate(zip_longest(old, new), 1):
            if a is None or b is None:
                raise ValueError('reviewed NBF record counts differ')
            old_hash.update(a)
            new_hash.update(b)
            if a != b:
                if number != RECORD_LINE or a != OLD_RECORD or b != NEW_RECORD:
                    raise ValueError('NBF difference is outside the sole reviewed instruction record')
                changed.append(number)
    if changed != [RECORD_LINE]:
        raise ValueError('NBF pair lacks the sole reviewed instruction change')
    if old_hash.hexdigest() != BASELINE_SHA or new_hash.hexdigest() != CONTROL_SHA:
        raise ValueError('actual NBF SHA256 differs from fixed reviewed image')
    return dict(baseline=dict(path=str(baseline.resolve()), sha256=old_hash.hexdigest()),
                control=dict(path=str(control.resolve()), sha256=new_hash.hexdigest()),
                changed_record_line=RECORD_LINE,
                original_record=OLD_RECORD.decode().strip(), control_record=NEW_RECORD.decode().strip())


def verify_reviewed_images():
    """Only the immutable reviewed pair is eligible; there is no override API."""
    manifest_path, verification_path = REVIEW / 'manifest.json', REVIEW / 'verification.json'
    if sha(manifest_path) != MANIFEST_SHA or sha(verification_path) != VERIFICATION_SHA:
        raise ValueError('reviewed mode14 manifest/proof identity mismatch')
    manifest = json.loads(manifest_path.read_text())
    verification = json.loads(verification_path.read_text())
    if (manifest['state'] != 'offline-causal-control-verified'
            or verification['state'] != 'PASS'
            or verification['manifest']['sha256'] != MANIFEST_SHA
            or manifest['source_nbf']['sha256'] != BASELINE_SHA
            or manifest['candidate_nbf']['sha256'] != CONTROL_SHA
            or manifest['changed_modes'] != [14]
            or not manifest['reverse_nbf_byte_exact']):
        raise ValueError('reviewed mode14 proof does not establish the exact control')
    modes_path = Path(manifest['all_modes']['path'])
    if sha(modes_path) != manifest['all_modes']['sha256']:
        raise ValueError('reviewed all-mode proof hash mismatch')
    modes = json.loads(modes_path.read_text())
    expected = [dict(mode=i, original_trigger=i in (2, 3, 5) or i >= 14,
                     control_trigger=i in (2, 3, 5) or i >= 15) for i in range(256)]
    if modes != expected:
        raise ValueError('reviewed proof changes a mode other than 14')
    images = _verify_nbf_pair(Path(manifest['source_nbf']['path']),
                              Path(manifest['candidate_nbf']['path']))
    images.update(manifest=artifact(manifest_path), verification=artifact(verification_path),
                  all_modes=artifact(modes_path))
    return images


def _load(paths):
    results, inodes, digests = [], set(), set()
    for path in paths:
        stat = path.stat()
        inode = (stat.st_dev, stat.st_ino)
        if inode in inodes:
            raise ValueError('independent boots require distinct transcript inodes')
        inodes.add(inode)
        text = path.read_text(errors='replace').replace('\r', '').replace('\x00', '')
        if len(BOOT.findall(text)) != 1:
            raise ValueError('each transcript must contain exactly one fresh Linux 6.6 boot')
        result = analyze(path, bootstrap_samples=1)
        digest = result['transcript_sha256']
        if digest in digests:
            raise ValueError('independent boots require distinct transcript content')
        digests.add(digest)
        runner = json.loads(Path(result['status']).read_text())
        if runner.get('runner_exit') != 0:
            raise ValueError('complete boot requires runner_exit zero')
        if ('whole_cell' not in result or 'resources' not in result
                or result['config'].get('resource_stats') != 1):
            raise ValueError('mode14 comparison requires WHOLE and resource rows')
        if 'retention_status' in result:
            raise ValueError('reviewed old-kernel comparison cannot use retention CSR telemetry')
        results.append(result)
    return results


def _strata(results):
    strata = []
    for result in results:
        whole, steady = result['whole_cell']['pairs'], result['pairs']
        if len(whole) != len(steady):
            raise ValueError('whole and steady pair counts differ')
        rows = []
        for a, b in zip(whole, steady):
            if (a['repeat'], a['enabled_order']) != (b['repeat'], b['enabled_order']):
                raise ValueError('whole and steady pairs have different order')
            rows.append(dict(whole_cycles=a['saved_cycles_per_cell'], whole_percent=a['saved_percent'],
                             steady_cycles=b['saved_cycles_per_roundtrip'], steady_percent=b['saved_percent']))
        strata.append(rows)
    return strata


def _median(strata):
    return {key: statistics.median(row[key] for boot in strata for row in boot)
            for key in strata[0][0]}


def _draw(rng, strata):
    # Use the same sampled boots and pairs for whole and steady measurements.
    sampled = []
    for index in rng.choices(range(len(strata)), k=len(strata)):
        boot = strata[index]
        sampled.append(rng.choices(boot, k=len(boot)))
    return _median(sampled)


def _boot(result):
    # analyze(..., bootstrap_samples=1) supplies points and validation here.
    # Its one-draw local intervals are not meaningful uncertainty estimates.
    points = lambda metrics: {key: value for key, value in metrics.items() if '95pct' not in key}
    whole = dict(pairs=result['whole_cell']['pairs'], metrics=points(result['whole_cell']['metrics']),
                 scope=result['whole_cell']['scope'])
    return dict(transcript=result['transcript'], transcript_sha256=result['transcript_sha256'],
                status=result['status'], status_sha256=result['status_sha256'], identity=result['identity'],
                whole_cell=whole, steady_pairs=result['pairs'],
                steady_metrics=points(result['metrics']), resources=result['resources'],
                enabled_order_by_repeat=[pair['enabled_order'] for pair in result['pairs']],
                trigger_accounting=result.get('trigger_accounting'))


def compare(baseline_paths, control_paths, bootstrap_samples=20000):
    """Contrast paired off-on benefits; only the reviewed NBF may differ."""
    if len(baseline_paths) < 2 or len(control_paths) < 2:
        raise ValueError('each image requires at least two independent complete boots')
    if bootstrap_samples <= 0:
        raise ValueError('bootstrap sample count must be positive')
    paths = [Path(path).resolve() for path in (*baseline_paths, *control_paths)]
    if len(set(paths)) != len(paths):
        raise ValueError('independent boots require distinct transcript paths')
    results = _load(paths)  # Completeness is checked before any effect is calculated.
    count = len(baseline_paths)
    baseline, control = results[:count], results[count:]
    config = baseline[0]['config']
    if (config['policy'] != 'futex-early' or config['sync'] != 'futex'
            or config.get('terminal_handshake') != 1):
        raise ValueError('reviewed comparison requires futex-early, futex, terminal_handshake=1')
    common = {key: value for key, value in baseline[0]['identity'].items() if key != 'nbf_sha256'}
    for label, boots, expected in (('baseline', baseline, BASELINE_SHA), ('control', control, CONTROL_SHA)):
        for index, result in enumerate(boots):
            if result['config'] != config:
                raise ValueError(f'{label} boot {index} configuration mismatch')
            if result.get('library') != baseline[0].get('library'):
                raise ValueError(f'{label} boot {index} library configuration mismatch')
            identity = {key: value for key, value in result['identity'].items() if key != 'nbf_sha256'}
            if identity != common:
                raise ValueError(f'{label} boot {index} identity mismatch')
            if result['identity']['nbf_sha256'] != expected:
                raise ValueError(f'{label} boot {index} is not the fixed reviewed NBF')
    images = verify_reviewed_images()
    base_strata, control_strata = _strata(baseline), _strata(control)
    base_point, control_point = _median(base_strata), _median(control_strata)
    draws = {key: [] for key in base_point}
    rng = random.Random(0x4d313443)
    for _ in range(bootstrap_samples):
        a, b = _draw(rng, base_strata), _draw(rng, control_strata)
        for key in draws:
            draws[key].append(b[key] - a[key])

    def contrast(prefix, unit):
        cycles, percent = prefix + '_cycles', prefix + '_percent'
        return {f'saved_cycles_per_{unit}': control_point[cycles] - base_point[cycles],
                f'hierarchical_95pct_ci_saved_cycles_per_{unit}':
                    [percentile(draws[cycles], 0.025), percentile(draws[cycles], 0.975)],
                'saved_percentage_points': control_point[percent] - base_point[percent],
                'hierarchical_95pct_ci_saved_percentage_points':
                    [percentile(draws[percent], 0.025), percentile(draws[percent], 0.975)]}

    return dict(
        purpose='Compare paired off-minus-on benefits after removing only the reviewed mode14 scheduler-selection trigger.',
        config=config, common_identity=common, reviewed_images=images, bootstrap_samples=bootstrap_samples,
        effect_direction='Positive control-minus-baseline benefit favors removal of the late trigger; negative values favor the historical combined policy.',
        primary_whole_cell_control_minus_baseline=contrast('whole', 'cell'),
        secondary_steady_control_minus_baseline=contrast('steady', 'roundtrip'),
        baseline=dict(nbf_sha256=BASELINE_SHA, mechanism='early entry plus incoming-task selection',
                      boots=[_boot(result) for result in baseline]),
        control=dict(nbf_sha256=CONTROL_SHA, mechanism='early entry; reviewed late selection site excluded',
                     boots=[_boot(result) for result in control]),
        interpretation_limits=[
            'Whole-cell cycles are primary and include setup, warmup, checked work, teardown and resource observers; they are not cycles per steady transaction.',
            'The contrast is a difference in paired off-on benefits across images, not a direct comparison of enabled medians from different boots.',
            'Boots and their paired blocks are resampled hierarchically; few independent boots still give limited between-boot evidence.',
            'Per-boot point estimates and pairs are retained; only the image contrasts carry the reported hierarchical uncertainty.',
            'Each input has one boot marker and unique path, inode and content. Recovery/reservation provenance and acquisition chronology remain externally documented; input-list order is not chronological proof.',
            'Per-repeat enabled order and all resource rows are retained for drift review. OS resource counts are not hardware cache-miss counts.',
            'The exact kernel control supports attribution to removal of this selection trigger only; it does not establish general application throughput or a prefetch-versus-capacity distinction.',
        ])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', nargs='+', required=True, type=Path)
    parser.add_argument('--control', nargs='+', required=True, type=Path)
    parser.add_argument('--bootstrap-samples', type=int, default=20000)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if args.output and args.output.exists():
        raise SystemExit(f'refusing to overwrite output: {args.output}')
    try:
        result = compare(args.baseline, args.control, args.bootstrap_samples)
    except (ValueError, OSError, KeyError) as error:
        raise SystemExit(str(error)) from error
    rendered = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(rendered)
        print(f'wrote {args.output}')
    else:
        print(rendered, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
