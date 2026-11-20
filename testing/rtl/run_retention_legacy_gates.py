#!/usr/bin/env python3
"""Run unchanged accepted replay/UCE gates against the isolated retention RTL."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--bp', type=Path, default=Path('/home/coyang/bp-linux-retention-policy'))
    args = parser.parse_args()
    rtl = Path(__file__).resolve().parent
    for name in ('run_icache_replay_buffer.py', 'run_uce_icache_side.py', 'run_uce_icache_replay.py'):
        original = rtl / name
        out = (args.out / original.stem).resolve()
        out.mkdir(parents=True, exist_ok=True)
        # Preserve accepted wrappers/stimulus; adapt only the isolated source
        # root and single-translation-unit C++ build to avoid disposable PCHs.
        body = original.read_text().replace('bp = root / "import/black-parrot"',
                                            'bp = Path(' + repr(str(args.bp.resolve())) + ')')
        body = body.replace('"-Wno-fatal"]', '"-Wno-fatal", "-MAKEFLAGS", "VM_PARALLEL_BUILDS=0"]')
        (out / 'adapter.json').write_text(json.dumps({
            'original': str(original),
            'original_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
            'executed_source_sha256': hashlib.sha256(body.encode()).hexdigest(),
            'bp': str(args.bp.resolve())}, indent=2)+'\n')
        sys.argv = [str(original), '--out', str(out)]
        exec(compile(body, str(original), 'exec'), {'__file__':str(original), '__name__':'__main__'})


if __name__ == '__main__':
    main()
