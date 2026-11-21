#!/usr/bin/env python3
"""Isolated header/ABI proof, host correctness checks and optional cross link.

Never executes an RV64 binary, integrated benchmark, simulation or board tool.
All generated files stay under a new numbered preparation directory here.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SDK = Path('/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot')
CC = SDK/'host/bin/riscv64-linux-gcc'
CPIO = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/kernel27/accepted-rootfs.cpio')
CPIO_SHA = 'e2f7dbc4d02d0ae99bb66832fe94b4882e19d7c95acd2cc0521299ff6aa73f50'
LIBC_SHA = 'd3f60c3e773fa76856457df96dc151609db7d1041e031c55477a62ff74cde43b'
MASK = (1 << 64) - 1
BASIS = 14695981039346656037
PRIME = 1099511628211


def artifact(path):
    path = Path(path).resolve()
    return dict(path=str(path), bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def allocated_sections(path):
    data = Path(path).read_bytes()
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    assert h[0][:6] == b'\x7fELF\x02\x01' and h[2] == 243, 'not ELF64 little-endian RISC-V'
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, h[6] + i*h[11]) for i in range(h[12])]
    strings = sections[h[13]]; names = data[strings[4]:strings[4]+strings[5]]
    result = {}
    for row in sections:
        name = names[row[0]:names.find(b'\0', row[0])].decode()
        if row[2] & 2:
            result[name] = dict(type=row[1], flags=row[2], address=row[3], bytes=row[5],
                sha256=None if row[1] == 8 else hashlib.sha256(data[row[4]:row[4]+row[5]]).hexdigest())
    return result


def accepted_libc():
    assert artifact(CPIO)['sha256'] == CPIO_SHA, 'accepted CPIO changed'
    data = CPIO.read_bytes(); offset = 0; found = None
    while offset < len(data):
        header = data[offset:offset+110]; assert header[:6] in (b'070701', b'070702')
        fields = [int(header[6+i*8:14+i*8], 16) for i in range(13)]
        size, namebytes = fields[6], fields[11]
        name = data[offset+110:offset+110+namebytes-1].decode()
        start = (offset+110+namebytes+3) & ~3
        if name == 'lib/libc.so.6':
            assert found is None, 'duplicate libc member'
            found = dict(member=name, bytes=size, sha256=hashlib.sha256(data[start:start+size]).hexdigest())
        offset = (start+size+3) & ~3
        if name == 'TRAILER!!!': break
    assert found and found['sha256'] == LIBC_SHA
    return found


def hash_byte(h, value): return ((h ^ value) * PRIME) & MASK


def independent_matches(text):
    """Separate Python field scanner; no regex or C-generated oracle consumed."""
    expected = [dict(matches=0, checksum=BASIS) for _ in range(3)]
    offset = 0
    for complete_line in text.splitlines(keepends=True):
        line = complete_line.rstrip(b'\n')
        fields = line.split(b' ')
        keys = (b'id=', b'user=', b'status=', b'bytes=')
        if len(fields) == 4 and all(field.startswith(key) for field, key in zip(fields, keys)):
            values = [field[len(key):] for field, key in zip(fields, keys)]
            assert 1 <= len(values[0]) <= 6 and values[0].isdigit()
            assert 3 <= len(values[1]) <= 8 and all(97 <= c <= 122 for c in values[1])
            assert values[2] in (b'ok', b'warn', b'fail')
            assert 1 <= len(values[3]) <= 5 and values[3].isdigit()
            captures = [(offset, offset+len(line))]; position = offset
            for field, key, value in zip(fields, keys, values):
                captures.append((position+len(key), position+len(key)+len(value)))
                position += len(field)+1
            for p, result in enumerate(expected):
                if p == 1 and values[2] == b'ok' or p == 2 and values[2] != b'fail': continue
                result['matches'] += 1
                for begin, end in captures:
                    for value in (begin, end):
                        for byte in value.to_bytes(8, 'little'): result['checksum'] = hash_byte(result['checksum'], byte)
                    for byte in text[begin:end]: result['checksum'] = hash_byte(result['checksum'], byte)
        offset += len(complete_line)
    return expected


def main():
    for index in range(1, 1000):
        output = HERE/('preparation-%03d' % index)
        try: output.mkdir(); break
        except FileExistsError: continue
    else: raise RuntimeError('no unused preparation directory')
    record = dict(state='preparing', scope='Future isolated regex functional core only; no timing or target execution.',
                  commands=[], source={p.name:artifact(p) for p in HERE.iterdir() if p.suffix in ('.c', '.h', '.py')})

    def run(label, argv, env=None):
        command = dict(label=label, argv=[str(x) for x in argv])
        result = subprocess.run(command['argv'], cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout = output/(label+'.stdout'); stderr = output/(label+'.stderr')
        stdout.write_bytes(result.stdout); stderr.write_bytes(result.stderr)
        command.update(returncode=result.returncode, stdout=artifact(stdout), stderr=artifact(stderr))
        record['commands'].append(command)
        if result.returncode: raise RuntimeError(label+' failed: '+str(result.returncode))
        return result.stdout.decode()

    try:
        sysroot = Path(run('cross-sysroot', [CC, '-print-sysroot']).strip())
        ext = SDK/'host/opt/ext-toolchain/riscv64-buildroot-linux-gnu/sysroot'
        headers = {}
        for name in ('regex.h', 'features.h'):
            path = sysroot/'usr/include'/name
            assert path.read_bytes() == (ext/'usr/include'/name).read_bytes()
            headers[name] = artifact(path)
        features = (sysroot/'usr/include/features.h').read_text()
        assert '#define\t__GLIBC__\t2' in features and '#define\t__GLIBC_MINOR__\t37' in features
        target = SDK/'target/lib/libc.so.6'; assert artifact(target)['sha256'] == LIBC_SHA
        allocated = allocated_sections(sysroot/'lib/libc.so.6')
        assert allocated == allocated_sections(target) and len(allocated) == 28
        member = accepted_libc()
        flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-march=rv64imafdc', '-mabi=lp64d']
        run('cross-abi-probe', [CC]+flags+['-H', '-c', HERE/'abi_probe.c', '-o', output/'abi_probe.o'])
        readelf = shutil.which('readelf'); assert readelf
        symbols = run('accepted-libc-symbols', [readelf, '-Ws', target])
        for symbol in ('regcomp', 'regexec', 'regfree', 'regerror'):
            assert symbol+'@@GLIBC_2.27' in symbols
        record['abi_proof'] = dict(state='actual cross2.37 public headers and accepted runtime allocated image verified',
            sysroot=str(sysroot), compiler=artifact(CC), headers=headers,
            sysroot_libc=artifact(sysroot/'lib/libc.so.6'), accepted_target_libc=artifact(target),
            accepted_cpio=artifact(CPIO), accepted_member=member, matching_allocated_sections=allocated,
            target_abi_probe=artifact(output/'abi_probe.o'),
            abi={'regex_t_bytes':64, 're_nsub_offset':48, 'regoff_t_bytes':4, 'regmatch_t_bytes':8, 'pointer_bytes':8},
            source_limit='SDK riscv-gnu-toolchain/glibc source2.42 is NOT this runtime; excluded. Bootlin archive not visible here; no fresh archive authentication claim.')
        host = shutil.which('cc'); assert host
        run('host-compiler-version', [host, '--version'])
        common = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie']
        sanitizers = ['-fsanitize=address,undefined']
        run('host-sanitizer-build', [host]+common+sanitizers+['-DRW_TESTING', HERE/'regex_workload.c', HERE/'host_checks.c', '-o', output/'host_checks'])
        env = dict(os.environ, LC_ALL='C', ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
        text = run('host-sanitizer-checks', [output/'host_checks'], env)
        assert text.strip() == 'REGEX_CORE_HOST_CHECKS_PASS'
        run('host-production-build', [host]+common+sanitizers+[HERE/'regex_workload.c', HERE/'functional_driver.c', '-o', output/'functional_driver'])
        cases = []
        for number, (size, seed) in enumerate(((0, 0), (1, 7), (4097, 71), (8193, 197), (32769, 991))):
            dump = run('oracle-dump-%d'%number, [output/'functional_driver', '--dump', size, seed], env)
            expected = []
            for line in dump.splitlines():
                if not line.startswith('REGEX_CORE_BLOCK '): continue
                fields = line.split(' ', 4); data = bytes.fromhex(fields[3]) if len(fields) == 4 else bytes.fromhex(fields[3]+' '+fields[4])
                # split with maxsplit3 keeps an empty final field for an empty block.
                expected.append(independent_matches(data))
            actual = run('oracle-requests-%d'%number, [output/'functional_driver', size, seed, 19], env)
            count = 0
            for line in actual.splitlines():
                if not line.startswith('REGEX_CORE_ROW '): continue
                fields = dict(v.split('=', 1) for v in line.split()[1:]); block = int(fields['block'])
                assert block == count % len(expected)
                for p in range(3):
                    assert int(fields['count%d'%p]) == expected[block][p]['matches']
                    assert int(fields['digest%d'%p], 16) == expected[block][p]['checksum']
                count += 1
            assert count == 19 and actual.rstrip().endswith('REGEX_CORE_FUNCTIONAL_PASS')
            cases.append(dict(input_bytes=size, seed=seed, requests=count, blocks=len(expected)))
        record['independent_python_oracle_cases'] = cases
        run('cross-functional-build', [CC]+flags+['-fno-pie', '-no-pie', HERE/'regex_workload.c', HERE/'functional_driver.c', '-o', output/'regex-functional.riscv'])
        dynamic = run('cross-functional-elf', [readelf, '-h', '-d', '-V', '-Ws', output/'regex-functional.riscv'])
        needed = [line.split('[', 1)[1].split(']', 1)[0] for line in dynamic.splitlines() if '(NEEDED)' in line]
        assert needed == ['libc.so.6'] and 'RISC-V' in dynamic
        for line in dynamic.splitlines():
            if 'UND' in line and 'reg' in line:
                assert '@GLIBC_2.27' in line
        record.update(state='PASS-host-functional-sanitizers-and-cross-link-only', cross_elf=artifact(output/'regex-functional.riscv'),
            cross_needed=needed, sanitizer_environment={k:env[k] for k in ('LC_ALL','ASAN_OPTIONS','UBSAN_OPTIONS')},
            sanitizer_limit='LeakSanitizer disabled for restricted host environment. Owned allocations and successful regcomp/regfree balanced by test counters; uninstrumented libc internals are not a leak or memory-bound proof. RV64 ELF not executed.')
    except BaseException as error:
        record.update(state='FAILED-preparation-not-target-evidence', error=repr(error))
        raise
    finally:
        (output/'manifest.json').write_text(json.dumps(record, indent=2)+'\n')
        print(output, record['state'])


if __name__ == '__main__': main()
