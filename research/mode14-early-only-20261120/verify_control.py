#!/usr/bin/env python3
"""Recheck all durable causal-control identities and whole-file differences."""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('control_gate', HERE / 'prepare_control.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def verify(value):
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value:
            path = Path(value['path'])
            assert gate.sha(path) == value['sha256'], str(path)
            assert path.stat().st_size == value['bytes'], str(path)
        for child in value.values():
            verify(child)
    elif isinstance(value, list):
        for child in value:
            verify(child)


def differences(original, control):
    old, new = original.read_bytes(), control.read_bytes()
    assert len(old) == len(new)
    return [dict(offset=hex(i), original=hex(a), control=hex(b))
            for i, (a, b) in enumerate(zip(old, new)) if a != b]


def main():
    manifest_path = HERE / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    verify(manifest)
    assert manifest_path.read_bytes() == (gate.OUT / 'manifest.json').read_bytes()
    path = lambda name: Path(manifest[name]['path'])
    binary = differences(path('original_payload'), path('control_payload'))
    elf = differences(path('original_elf'), path('control_elf'))
    nbf = differences(path('source_nbf'), path('candidate_nbf'))
    assert binary == [dict(offset='0x813fe8', original='0x1d', control='0x21')]
    assert elf == [dict(offset='0x814fe8', original='0x1d', control='0x21')]
    assert len(nbf) == 2  # Two ASCII hex digits encode the single changed byte.
    assert path('source_nbf').read_bytes() == path('reverse_nbf').read_bytes()
    assert path('control_payload').read_bytes() == path('converted_control_payload').read_bytes()
    assert path('control_payload').read_bytes() == path('reextracted_payload').read_bytes()
    old = gate.selected_mode_triggers(path('original_payload').read_bytes())
    new = gate.selected_mode_triggers(path('control_payload').read_bytes())
    assert [mode for mode in range(256) if old[mode] != new[mode]] == [14]
    assert old[14] and not new[14] and not old[0] and not new[0]
    recorded = json.loads(path('all_modes').read_text())
    assert recorded == [dict(mode=i, original_trigger=old[i], control_trigger=new[i])
                        for i in range(256)]
    result = dict(state='PASS', scope='offline only; no board or kernel build',
                  manifest=gate.record(manifest_path), verifier=gate.record(Path(__file__)),
                  full_payload_differences=binary, full_elf_differences=elf,
                  full_nbf_ascii_differences=nbf, changed_modes=[14],
                  reverse_nbf_byte_exact=True, conversion_and_extraction_byte_exact=True)
    rendered = json.dumps(result, indent=2) + '\n'
    (HERE / 'verification.json').write_text(rendered)
    (gate.OUT / 'verification.json').write_text(rendered)
    print('PASS: all durable identities; exactly one binary/ELF byte and two NBF ASCII digits differ')


if __name__ == '__main__':
    main()
