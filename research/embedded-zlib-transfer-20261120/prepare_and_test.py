#!/usr/bin/env python3
"""Create a review-only runner patch and test temporary copied modules offline."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FILES = ('linux-tests/run_scheduler_pipe_hint.py', 'linux-tests/run_resume_workload_session.py')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after)


def proposed(name, text):
    if name.endswith('run_scheduler_pipe_hint.py'):
        text = replace(text, '    parser.add_argument("--retention-probe", choices=("absent", "present"),',
                       '    parser.add_argument("--embedded-zlib-library", action="store_true",\n'
                       '                        help="copy fixed /opt/bp-resume/libz.so.1; requires exact --zlib-library")\n'
                       '    parser.add_argument("--retention-probe", choices=("absent", "present"),')
        text = replace(text, 'def validate_args(args):\n', 'def validate_args(args):\n'
                       '    if args.embedded_zlib_library and args.zlib_library is None:\n'
                       '        raise ValueError("--embedded-zlib-library requires exact --zlib-library")\n')
        text = replace(text, '    return library_transfer(args.zlib_library)\n',
                       '    if args.embedded_zlib_library:\n'
                       '        return [f"cp {EMBEDDED_DIRECTORY}libz.so.1 {GUEST_ZLIB}"]\n'
                       '    return library_transfer(args.zlib_library)\n')
        text = replace(text, 'status["zlib_transfer_encoding"] = ("embedded-copy-v1" if embedded is not None\n',
                       'status["zlib_transfer_encoding"] = ("embedded-copy-v1" if embedded is not None\n'
                       '                                             or args.embedded_zlib_library\n')
    else:
        text = replace(text, "    parser.add_argument('--host', default='xilinx@192.168.4.35')\n",
                       '    parser.add_argument("--embedded-zlib-library", action="store_true",\n'
                       '                        help="copy fixed embedded library; requires exact --zlib-library")\n'
                       "    parser.add_argument('--host', default='xilinx@192.168.4.35')\n")
        text = replace(text, '    args = parser.parse_args(argv)\n', '    args = parser.parse_args(argv)\n'
                       '    if args.embedded_zlib_library and args.zlib_library is None:\n'
                       '        parser.error("--embedded-zlib-library requires exact --zlib-library")\n')
        text = replace(text, '        parsed.zlib_library = args.zlib_library\n',
                       '        parsed.zlib_library = args.zlib_library\n'
                       '        parsed.embedded_zlib_library = args.embedded_zlib_library\n')
    return text


def main():
    evidence = HERE / 'draft'
    evidence.mkdir()  # Preserve any previous review run.
    before = {name: (ROOT / name).read_bytes() for name in FILES}
    after = {name: proposed(name, data.decode()).encode() for name, data in before.items()}
    patch = ''.join(''.join(difflib.unified_diff(before[name].decode().splitlines(True),
                       after[name].decode().splitlines(True), fromfile='a/' + name,
                       tofile='b/' + name)) for name in FILES)
    (evidence / 'embedded-zlib-library.patch').write_text(patch)
    for group, content in (('original', before), ('proposed', after)):
        for name, data in content.items():
            destination = evidence / group / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
    with tempfile.TemporaryDirectory(prefix='embedded-zlib-review-') as directory:
        sandbox = Path(directory)
        # The existing reservation tests snapshot these scripts but mock every
        # command. None of the copied scripts is executed by this driver.
        names = set(FILES) | {
            'linux-tests/' + name for name in ('run_scheduler_tagged_replay.py',
            'emit_resume_transfer.py', 'test_run_scheduler_pipe_hint.py',
            'test_embedded_resume_transfer.py', 'test_run_resume_workload_session.py',
            'scheduler_pipe_hint_benchmark.c', 'kernel-patches/0026-blackparrot-early-futex-instruction-replay.patch')}
        names |= {'codex-skills/bp-fpga-synthesis/scripts/' + name for name in
                  ('stage_pynq_artifacts.sh', 'power_cycle_pynq.sh', 'wait_pynq_ready.sh',
                   'load_pynq_overlay.sh', 'run_pynq_interactive.sh')}
        for name in names:
            destination = sandbox / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, destination)
        applied = subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i',
                                  str(evidence / 'embedded-zlib-library.patch')],
                                 cwd=sandbox, capture_output=True, text=True, timeout=10)
        (evidence / 'patch-apply.log').write_text(applied.stdout + applied.stderr)
        applied.check_returncode()
        assert all((sandbox / name).read_bytes() == data for name, data in after.items())
        shutil.copy2(HERE / 'test_embedded_zlib_library.py', sandbox / 'linux-tests/test_embedded_zlib_library.py')
        command = [sys.executable, '-m', 'unittest', 'test_run_scheduler_pipe_hint',
                   'test_embedded_resume_transfer', 'test_run_resume_workload_session',
                   'test_embedded_zlib_library']
        run = subprocess.run(command, cwd=sandbox / 'linux-tests', capture_output=True, text=True, timeout=60)
        (evidence / 'host-tests.stdout').write_text(run.stdout)
        (evidence / 'host-tests.stderr').write_text(run.stderr)
        run.check_returncode()
        reverse = subprocess.run(['patch', '--batch', '--fuzz=0', '-R', '-p1', '-i',
                                  str(evidence / 'embedded-zlib-library.patch')],
                                 cwd=sandbox, capture_output=True, text=True, timeout=10)
        (evidence / 'patch-reverse.log').write_text(reverse.stdout + reverse.stderr)
        reverse.check_returncode()
        assert all((sandbox / name).read_bytes() == data for name, data in before.items())
    assert all((ROOT / name).read_bytes() == data for name, data in before.items())
    manifest = dict(state='review-only; active runners unchanged',
                    patch_sha256=sha(patch.encode()), command=command, test_exit_code=run.returncode,
                    original_sha256={name: sha(data) for name, data in before.items()},
                    proposed_sha256={name: sha(data) for name, data in after.items()},
                    test_source_sha256=sha((HERE / 'test_embedded_zlib_library.py').read_bytes()),
                    active_runners_unchanged=True, patch_roundtrip=True, board_actions=False)
    (evidence / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(run.stderr)
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
