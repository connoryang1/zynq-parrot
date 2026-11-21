"""Exact static16KiB SP inputs; no old4KiB model/source overrides."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
PROPOSAL=ROOT/'research/retained-sp-scoped-proposal-20261121/proposal.json'
PROPOSAL_SHA='3e36cedab61a2a406a76861f3897663680bfb958ce91462ce6743d4cc83e5b5f'
NATIVE=PROPOSAL.parent/'native-identities.json'
NATIVE_SHA='fb16f41621fbb59fc7d8a6f2b20c679a93bbd94076f079b5093e8d64b39e9941'
MODEL_SHA='f65c04d85f495e4412d782b32e362dd0ce09914787f8fbe61284964b7b34444e'
PREFIX='Vbsg_nonsynth_zynq_testbench';SYMS=PREFIX+'__Syms'
CAP=150*1024*1024;NATIVE_SECONDS=180;HOST_SECONDS=360
RESERVE=3*1024**3;ARTIFACT_ALLOCATION=512*1024**2
SP=Path('/home/coyang/zynq-parrot-retained-sp')
ORIGINAL=Path('/home/coyang/fpga-artifacts/context-resume/retained-private-sp-ram-20261121/full01')


def require(value,message):
    if not value:raise ValueError(message)


def bind(path):
    p=Path(path).resolve();h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())


def verify(record):require(bind(record['path'])==record,'frozen file changed: '+record['path'])


def save(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')


def identities(records):return {k:(v['bytes'],v['sha256']) for k,v in records.items()}


def tree(path):
    result={}
    for p in sorted(Path(path).rglob('*')):
        require(not p.is_symlink(),'generated tree contains symlink')
        if p.is_file() and p.suffix!='.gch':result[str(p.relative_to(path))]=bind(p)
    return result


def fresh_home(path):
    p=Path(path).absolute();require(not p.exists() and not p.is_symlink(),'output must be fresh')
    p=p.resolve();require(str(p).startswith('/home/coyang/'),'output must be HOME');return p


def reviewed():
    require(bind(PROPOSAL)['sha256']==PROPOSAL_SHA and bind(NATIVE)['sha256']==NATIVE_SHA,'reviewed SP proposal/native identities changed')
    p=json.loads(PROPOSAL.read_text());n=json.loads(NATIVE.read_text())
    require(p['original_model']['sha256']==n['model']['sha256']==MODEL_SHA,'wrong SP model')
    require(p['writer_leaf_count']==400 and len({r['path'] for r in p['leaves']})==400,'wrong400-leaf union')
    require(p['reader_domain_counts']==dict(core252=252,observer_and_geometry=45,SP_strict162=162),'wrong complete reader domains')
    return p,n


def proposal():
    p,n=reviewed();f=json.loads((HERE/'source-freeze.json').read_text())
    require(f['model']['sha256']==MODEL_SHA,'wrong source freeze')
    mapped=n['compile_argv'].copy();mapped[-5]=PREFIX+'__pch.h'
    return dict(p,model=n['model'],filter_leaves=p['leaves'],
        original_generated_root=n['original_generated_root'],original_generated_files=f['original_generated_files'],
        original_build_log=n['build_log'],original_archive=n['archive'],original_Syms=n['Syms'],
        archive_member_sha256=f['archive_member_sha256'],compile_argv=n['compile_argv'],
        original_PCH_creation_argv=n['PCH_creation_argv'],textual_header_compile_argv=mapped,
        link_argv=n['link_argv'],host_objects=n['seven_host_objects'],PCH_textual_header=n['PCH_text_header'],
        reviewed_runtime=f['reviewed_runtime'],estimated_copy_bytes_without_PCH=n['copy_bytes_without_gch'],
        source_freeze=bind(HERE/'source-freeze.json'),compiled_sources=f['compiled_sources'])
