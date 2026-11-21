#!/usr/bin/env python3
"""Bind the closed absent-probe inputs locally; no SSH or board action."""
import base64
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'linux-tests'))
import emit_resume_transfer
import retained29_protocol as p


def write(path,obj):path.write_text(json.dumps(obj,indent=2)+'\n')


def main():
    output=HERE/'closed-preparation-002'
    external=Path('/home/coyang/fpga-artifacts/context-resume/retained29-session-preparation-20261121/closed-preparation-002')
    p.require(not output.exists() and not external.exists(),'new output paths required')
    package=Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/fpga-fit/20261120T211416Z-7edf64d1/black_parrot_bd_1.zynq.pynqz2.tar.xz.b64')
    p.require(p.binding(package)['sha256']==p.ABSENT_PACKAGE_SHA,'accepted absent package changed')
    verified=subprocess.run([str(p.SCRIPTS/'verify_pynq_package.sh'),str(package),p.ABSENT_BIT_SHA],
                            text=True,capture_output=True,check=True,timeout=90)
    output.mkdir();external.mkdir(parents=True)
    (output/'package-verification.log').write_text(verified.stdout)
    # The already hash-bound package is trusted input. Read only its single
    # regular bit member; no tar paths are extracted into the source worktree.
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(package.read_bytes())),mode='r:xz') as archive:
        members=[m for m in archive.getmembers() if m.isfile() and m.name.endswith('.bit')]
        p.require(len(members)==1,'single bit member required')
        bit=external/'accepted-f744.bit';bit.write_bytes(archive.extractfile(members[0]).read())
    p.require(p.binding(bit)['sha256']==p.ABSENT_BIT_SHA,'extracted bit identity')
    probe=ROOT/'research/retained-control-abi-20261121/retained_store_probe.elf'
    transfer=output/'probe.transfer';transfer.write_text('\n'.join(emit_resume_transfer.commands(probe))+'\n')
    paths=dict(nbf='/home/coyang/fpga-artifacts/context-resume/retained-control-kernel29-20261121/package/linux-retained-control29-accepted-rootfs-mem46-shell.nbf',
        elf=probe,transfer=transfer,package=package,bit=bit,
        fit=ROOT/'research/retention-fit-20261120/manifest.json',
        kernel_verification=ROOT/'research/retained-control-kernel29-20261121/verification.json')
    admission=dict(schema='bp-retained29-functional-session-v1',state='bound-functional-only',role='probe-absent',
        host='xilinx@192.168.4.35',guest_argv=p.argv_for('probe-absent'),one_guest_boot=True,performance_inference=False,
        runner_sha256=p.RUNNER_SHA,board_helper_sha256=p.HELPER_SHA,runtime_ms=3600000,sources=p.source_hashes(),
        artifacts={key:p.binding(path) for key,path in paths.items()},
        hardware=dict(cfg='e_bp_unicore_zynqparrot_prefetch_cfg',l1i_bytes=32768,l1d_bytes=32768,l2_bytes=4096,retained=None))
    p.validate_admission(admission)
    write(output/'probe-absent.admission.json',admission)
    present=copy.deepcopy(admission)
    present.update(state='DRAFT-unlaunchable-pending-actual-routed-fit-package-and-bit',role='probe-present',guest_argv=p.argv_for('probe-present'))
    for key in ('package','bit','fit'):present['artifacts'][key]=None
    present['hardware']=dict(cfg='e_bp_unicore_zynqparrot_prefetch16k_cfg',l1i_bytes=32768,l1d_bytes=32768,
        l2_bytes=16384,retained=None)
    present['missing_bindings']=['passed actual routed fit','actual package and extracted bit','actual retained I/D slot counts and set_log2']
    write(output/'probe-present.DRAFT.json',present)
    benchmark=copy.deepcopy(present)
    benchmark.update(role='benchmark-functional',guest_argv=p.argv_for('benchmark-functional'),capability_gate=None)
    benchmark['artifacts']['elf']=p.binding(ROOT/'research/retained29-natural-workload-20261121/preparation-002-cleanup/compiled/scheduler_retained29_benchmark_dynamic')
    benchmark['artifacts']['transfer']=p.binding(ROOT/'research/retained29-natural-workload-20261121/preparation-002-cleanup/retained29.transfer')
    benchmark['missing_bindings'].append('complete recovered matching probe-present session.json and its console')
    write(output/'benchmark-functional.DRAFT.json',benchmark)
    tests=subprocess.run([sys.executable,'-m','unittest','-v','test_retained29_session.py'],cwd=ROOT/'linux-tests',
                         text=True,capture_output=True)
    (output/'host-tests.log').write_text(tests.stdout+tests.stderr)
    p.require(tests.returncode==0,'host tests failed')
    source_paths=[ROOT/name for name in p.SOURCE_FILES]+[ROOT/'linux-tests/test_retained29_session.py',Path(__file__).resolve(),HERE/'README.md']
    sources=[]
    for path in source_paths:
        relative=path.relative_to(ROOT);target=output/'source'/relative
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
        sources.append(p.binding(path))
    write(output/'manifest.json',dict(state='PASS offline preparation only; no board call or physical result',
        scope='15 host tests plus real local accepted-package/extracted-bit/NBF/ELF/transfer/source binding; present drafts rejected',
        sources=sources,files=[p.binding(path) for path in sorted(output.iterdir()) if path.is_file()],
        extracted_bit=p.binding(bit),unit_fixture_limit='Host lifecycle tests mock board steps and package/hash fixtures; they are not independent artifact or physical proof.'))
    print(output/'manifest.json')


if __name__=='__main__':main()
