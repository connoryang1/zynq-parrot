#!/usr/bin/env python3
"""Copy only enumerated immutable receipts/helpers; never execute their code."""
import gzip
import hashlib
import io
import json
import lzma
from pathlib import Path
import shutil
import tarfile

HERE=Path(__file__).resolve().parent
ORIGIN=Path('/home/coyang/fpga-artifacts/context-resume/borrow256-fpga-preparation-20261122/preparation01')
RUN='adapter02/run-20261122T084853Z-1008854d3'
CAP=1024**2
HELPERS=['prepare_source.py','software_owned_v2.py','prepare_packet.py','prepare_admission.py','monitor_local.py','remote_probe.py','identity.py','budget.py','ownership_ledger.py','cancel_local.sh','README.md']
ADAPTER=['reservation.py','prepare_packet.py','prepare_admission.py','monitor_local.py','remote_probe.py','identity.py','budget.py','ownership_ledger.py','cancel_local.sh','README.md']
PROOFS=['provenance.json','unexecuted-adapter01-preserved.json','adapter-handoff.json',
        'actual01/session.json','actual01/plan.json','actual01/source-files.json','actual01/consumed-source-bridge.json','actual01/private-generated-inputs.json','actual01/auxiliary.json',
        'actual01/readiness.log','actual01/make-dryrun.log','native-proof/session.json','native-proof/actual-source-list.json',
        'adapter02/ROOT-preflight01.json','adapter02/ROOT-launch01.json','adapter02/admission01.json','adapter02/ROOT-release01.json','adapter02/handoff.json',RUN+'/monitor-identity.json']


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def binding(path):return dict(path=str(path),**digest(Path(path).read_bytes()))


def main():
    require(not (HERE/'manifest.json').exists(),'fresh immutable packet only')
    originals=[];copies=[];members=[];pending=[]
    for rel in HELPERS+['adapter02/'+name for name in ADAPTER]:
        source=ORIGIN/rel;raw=source.read_bytes();dest=Path('helpers')/rel
        originals.append(binding(source));pending.append((dest,raw));copies.append(dict(local=str(dest),original=binding(source),**digest(raw)))
    admitted=json.loads((ORIGIN/'adapter02/admission01.json').read_text())
    expected={'launch_synthesis.sh','check_build_ready.sh','run_vivado_2024_2.sh','accept_vivado_build.sh','summarize_vivado.sh','select_vivado_report.sh','check_vivado_timing.sh','farm_synthesis.sh'}
    require({Path(r['path']).name for r in admitted['operational_bindings']}==expected,'exact eight admitted operational source helpers')
    for row in admitted['operational_bindings']:
        source=Path(row['path']);raw=source.read_bytes();require(binding(source)==row,'actual admitted operational source unchanged')
        dest=Path('helpers/operational')/source.name;pending.append((dest,raw));copies.append(dict(local=str(dest),original=row,**digest(raw)));originals.append(row)
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w') as tar:
        for rel in PROOFS:
            source=ORIGIN/rel;raw=source.read_bytes();name='proofs/'+rel
            info=tarfile.TarInfo(name);info.size=len(raw);info.mtime=0;info.mode=0o644
            tar.addfile(info,io.BytesIO(raw));members.append(dict(member=name,original=binding(source),**digest(raw)));originals.append(binding(source))
        for source,name in [(Path('/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/retained-borrow256-shared-budget-preparation-20261122/policy.json'),'proofs/shared-policy.json'),
                            (Path('/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/retained-borrow256-shared-budget-preparation-20261122/operational-note.json'),'proofs/archive-deferral-note.json')]:
            raw=source.read_bytes();info=tarfile.TarInfo(name);info.size=len(raw);info.mtime=0;info.mode=0o644
            tar.addfile(info,io.BytesIO(raw));members.append(dict(member=name,original=binding(source),**digest(raw)));originals.append(binding(source))
    raw_tar=archive.getvalue();packed=lzma.compress(raw_tar,preset=6);require(lzma.decompress(packed)==raw_tar,'lossless whole archive roundtrip')
    pending.append((Path('immutable-proofs.tar.xz'),packed))
    for name in ('poll-001.json.gz','poll-005.json.gz'):
        source=ORIGIN/RUN/name;raw=source.read_bytes();decoded=gzip.decompress(raw);json.loads(decoded)
        dest=Path('running-snapshots')/name;pending.append((dest,raw));copies.append(dict(local=str(dest),original=binding(source),**digest(raw),decompressed=digest(decoded)))
        originals.append(binding(source))
    current=sum(p.stat().st_size for p in HERE.rglob('*')if p.is_file())
    require(current+sum(len(raw)for _,raw in pending)+65536<=CAP,'1MiB entire new packet, including manifest/report reserve')
    for rel,raw in pending:
        path=HERE/rel;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb')as stream:stream.write(raw)
        require(path.read_bytes()==raw,'copy byte roundtrip '+str(rel))
    for row in originals:require(binding(row['path'])==row,'immutable original changed during capture')
    result=dict(schema='borrow256-running-CAD-curation-v1',scope='Immutable launch/source readiness and two running-only snapshots; no fit/route/bit/board/application acceptance',
        origin=str(ORIGIN),job='20261122T084853Z-1008854d3',worker=dict(pid=1194135,startticks=95314382),
        cap_bytes=CAP,copy_files=copies,proof_archive=dict(local='immutable-proofs.tar.xz',**digest(packed),uncompressed_tar=digest(raw_tar),members=members),
        original_files=originals,excluded='Full trees/DCPs/live status/ownership ledger/monitor lock/later polls; originals remain external and untouched',
        roles=dict(source_preparation='actual ROOT43766 private clones/readiness/Make-n PASS30.425947754993103s',adapter01='UNEXECUTED CAD adapter, preserved source only',adapter02='actual ROOT preflight/release/launch/monitor'),
        snapshot_limit='poll005 RUNNING at375.14s, feature propagation PASS only; never terminal acceptance')
    with (HERE/'manifest.json').open('x')as stream:json.dump(result,stream,indent=2);stream.write('\n')
    require(sum(p.stat().st_size for p in HERE.rglob('*')if p.is_file())<=CAP,'total packet cap')
    print(json.dumps(dict(manifest=binding(HERE/'manifest.json'),packet_bytes=sum(p.stat().st_size for p in HERE.rglob('*')if p.is_file())),sort_keys=True))


if __name__=='__main__':main()
