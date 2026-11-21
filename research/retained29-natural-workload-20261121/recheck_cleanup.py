#!/usr/bin/env python3
"""Revalidate the cleanup fix in fresh outputs; preserve the first closed proof."""
import json
from pathlib import Path
import prepare

HERE = Path(__file__).resolve().parent
OUT = HERE / 'preparation-002-cleanup'


if __name__ == '__main__':
    OUT.mkdir(exist_ok=False)
    prepare.HERE = OUT  # Output destination only; source/tool/reference roots stay fixed.
    prepare.main()
    (OUT / 'invocation.json').write_text(json.dumps({
        'wrapper': prepare.record(Path(__file__).resolve()),
        'preparation_driver': prepare.record(HERE / 'prepare.py'),
        'output_directory': str(OUT),
        'purpose': 'Current cleanup-fixed source revalidation; first closed ELF/manifest remain historical.',
        'no_target_execution': True}, indent=2) + '\n')
