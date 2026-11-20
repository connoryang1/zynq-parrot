#!/usr/bin/env python3
"""Read-only audit of accepted guest RAM versus requested PYNQ allocation.

Writes JSON/text evidence only. Never executes a target or produces an image.
"""
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ART = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120')
SDK = Path('/home/coyang/zynq-parrot/import/black-parrot-sdk')
REV = 'b4c82aded497b61b995c86199c6f618aadafb195'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def binding(path):
    b = path.read_bytes()
    return dict(path=str(path), bytes=len(b), sha256=sha(b))


def source(path, ranges, revision=None):
    if revision:
        b = subprocess.check_output(['git', '-C', str(REPO), 'show', f'{revision}:{path}'])
        out = dict(repository=str(REPO), revision=revision, path=path,
                   git_blob=subprocess.check_output(['git', '-C', str(REPO), 'rev-parse',
                                                     f'{revision}:{path}'], text=True).strip())
    else:
        b = Path(path).read_bytes()
        out = dict(path=str(path))
    lines = b.decode().splitlines()
    out.update(bytes=len(b), sha256=sha(b), excerpts=[dict(first_line=a, last_line=z,
        text='\n'.join(f'{i} {lines[i-1]}' for i in range(a, z+1))) for a, z in ranges])
    return out


def fdt_info(b):
    h = struct.unpack_from('>10I', b)
    assert h[0] == 0xd00dfeed and len(b) == h[1]
    reservations = []
    pos = h[4]
    while True:
        addr, size = struct.unpack_from('>QQ', b, pos)
        pos += 16
        if not (addr or size):
            break
        reservations.append(dict(address=hex(addr), bytes=size))
    strings = b[h[3]:h[3]+h[8]]
    pos, stack, props = h[2], [], {}
    while True:
        token, = struct.unpack_from('>I', b, pos)
        pos += 4
        if token == 1:
            end = b.index(0, pos)
            stack.append(b[pos:end].decode())
            pos = (end+4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, nameoff = struct.unpack_from('>II', b, pos)
            pos += 8
            name = strings[nameoff:strings.index(0, nameoff)].decode()
            props['/'.join(stack) + '/' + name] = b[pos:pos+length]
            pos = (pos+length+3) & ~3
        elif token == 4:
            pass
        elif token == 9:
            break
        else:
            raise ValueError(f'unknown FDT token {token}')
    base, length = struct.unpack('>QQ', props['/memory@80000000/reg'])
    return dict(sha256=sha(b), bytes=len(b), memory_base=hex(base), memory_bytes=length,
                memory_end_exclusive=hex(base+length), memreserve=reservations,
                reserved_memory_properties=[k for k in props if k.startswith('/reserved-memory')],
                bootargs=props['/chosen/bootargs'].rstrip(b'\0').decode())


def nbf_binding(path, dtb):
    # Compare actual NBF write bytes against the complete retained firmware DTB.
    address = 0x80016000
    observed = bytearray(len(dtb))
    valid = bytearray(len(dtb))
    digest = hashlib.sha256()
    maximum = 0
    count = 0
    with path.open('rb') as f:
        for line in f:
            digest.update(line)
            op, addr, data = (int(s, 16) for s in line.strip().split(b'_'))
            if op not in (0, 1, 2, 3):
                continue
            size = 1 << op
            if 0x80000000 <= addr < 0x84000000:
                maximum = max(maximum, addr+size)
                count += 1
            for i in range(max(addr, address), min(addr+size, address+len(dtb))):
                observed[i-address] = (data >> (8*(i-addr))) & 255
                valid[i-address] = 1
    assert observed == dtb, f'DTB mismatch in {path}'
    omitted = [i for i, written in enumerate(valid) if not written]
    assert all(dtb[i] == 0 for i in omitted)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest.hexdigest(),
                dtb_matches_retained_firmware_with_zero_filled_sparse_holes=True,
                dtb_unwritten_zero_byte_offsets=omitted,
                sparse_hole_limit='NBF omits these zero bytes; comparison is image reconstruction, not a claim about runtime allocator initialization. Boot log independently proves actual Linux range.',
                dram_write_records=count,
                highest_dram_write_end_exclusive=hex(maximum),
                all_dram_image_writes_within_requested_46MiB=maximum <= 0x82e00000)


def main():
    firmware = ART/'kernel27/baseline-firmware-memory-80000000-80200000.bin'
    raw = firmware.read_bytes()
    offset = raw.index(b'\xd0\x0d\xfe\xed')
    assert offset == 0x16000
    length, = struct.unpack_from('>I', raw, offset+4)
    dtb = raw[offset:offset+length]
    info = fdt_info(dtb)
    assert info['memory_bytes'] == 64*1024*1024
    assert not info['memreserve'] and not info['reserved_memory_properties']
    assert 'mem=' not in info['bootargs']
    log = ART/'session14/0-scan32-futex-early.log'
    text = log.read_text()
    size = int(re.search(r'allocating owned DRAM buffer with size (\d+)', text)[1])
    physical = int(re.search(r'allocate_dram\(\).*physical ptr=(0x[0-9a-f]+)', text)[1], 16)
    assert size == 46*1024*1024
    lines = text.splitlines()
    terms = ('allocating owned DRAM', 'allocate_dram() called', 'reserved mem:', 'DMA32',
             'node   0:', 'Kernel command line:', 'Memory:', 'Built 1 zonelists')
    evidence = [dict(line=i, text=s) for i, s in enumerate(lines, 1) if any(t in s for t in terms)]
    linux = SDK/'linux/work/buildroot/build/linux-6.6'
    sources = {
        'top': source('cosim/black-parrot-example/v/top_zynq.sv', [(248, 253), (664, 677)], REV),
        'host': source('cosim/black-parrot-example/ps.cpp', [(26, 29), (179, 203)], REV),
        'allocator': source('cosim/include/zynq/bsg_zynq_pl.h', [(86, 108)], REV),
        'host_make': source('cosim/black-parrot-example/zynq/Makefile', [(6, 14)], REV),
        'riscv_mem': source(linux/'arch/riscv/mm/init.c', [(173, 203)]),
        'memblock': source(linux/'mm/memblock.c', [(1702, 1740)]),
        'historical_46MiB_runner': source('/home/coyang/zynq-parrot/logs/linux-memory46-boot-control-20261006/README.md', [(10, 17)]),
    }
    (HERE/'source-proof.json').write_text(json.dumps(sources, indent=2)+'\n')
    status_path = log.with_suffix(log.suffix+'.status.json')
    status = json.loads(status_path.read_text())
    report = dict(scope='Read-only source/log/actual-NBF audit; no target execution or image generation',
        conclusion='Guest advertised RAM exceeds the requested owned allocation by 18 MiB; crash causation unproven',
        runner_sha256=status['control_program_sha256'],
        session14_status=binding(status_path), bitstream_sha256=status['bitstream_sha256'],
        accepted_top_revision=REV,
        source_binding_limit='Source remap follows recorded accepted top revision. No new elaboration, netlist validation or physical traffic observation was performed.',
        log=binding(log), log_evidence=evidence, firmware=binding(firmware), dtb=info,
        accepted_nbf=nbf_binding(ART/'linux-prefix32-futex-usersyscall-shell.nbf', dtb),
        session14_nbf=nbf_binding(ART/'embedded-workloads/linux-prefix32-embedded-baseline-shell.nbf', dtb),
        requested_allocation_bytes=size, guest_advertised_bytes=info['memory_bytes'],
        unowned_advertised_bytes=info['memory_bytes']-size,
        guest_owned_range=['0x80000000', hex(0x80000000+size)],
        guest_excess_range=[hex(0x80000000+size), '0x84000000'],
        session14_host_requested_range=[hex(physical), hex(physical+size)],
        session14_host_excess_range=[hex(physical+size), hex(physical+info['memory_bytes'])],
        interval_convention='half-open [begin,end)',
        guards='No active 46MiB bound/mask in accepted top remap. The commented 256MiB warning is neither an enforcing guard nor the requested allocation bound.',
        ownership_limit='pynq.allocate shape=(requested_bytes,), dtype=u1; no retained evidence grants ownership of extra 18MiB. BO/CMA rounding or free totals are insufficient.',
        reservations='Retained zero-reconstructed input DTB has no memreserve/reserved-memory (NBF skips16zero memreserve bytes; see sparse-hole limit). Actual OpenSBI boot reports only two low regions totaling320KiB; Linux node/zone initialization extends to0x83ffffff. Aggregate reserved=25996K does not establish a reservation of the upper18MiB.',
        provenance_limit='Historical README names exact2dd9 as46MiB. Recorded top Makefile default is64MiB; exact binary build invocation/local executable not recovered. Runtime requests are direct evidence independent of build provenance.',
        candidate_control='NEW matched NBF pair with bootarg mem=46M, same immutable2dd9 runner. Source early_mem clamps memory_limit; setup_bootmem enforces it. Prospective until actual new boots verify limit and usable node end; changes baseline for all arms.',
        causation_limit='No faulting physical address or HP0 traffic demonstrates an out-of-buffer access causing SIG11/PID-null/post-exit failures. Passing session14 does not establish safety of the old64MiB contract.')
    (HERE/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({p.name: binding(p) for p in (HERE/'audit.json', HERE/'source-proof.json')}, indent=2))


if __name__ == '__main__':
    main()
