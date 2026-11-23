"""Literal clean768 producer gate; never accepts prior1536/composite state."""
import hashlib,json
from pathlib import Path
BASE=Path('/run/user/1001/zp-csr-unmasked768-fullcore-20261123-01')
FULL=BASE/'full01'
TOP='1b24c915ed628f6d47a382b3aa89fb662884e1a1'
BP='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa'
STATE='PASS CSR unmasked768 trace0 clean fullcore integrity/cold08 strict512b-eight-real-writes-Iretire-counter-17geometry-source-audits'

def require(v,m):
    if not v:raise ValueError(m)

def bind(path):
    p=Path(path).resolve();h=hashlib.sha256()
    with p.open('rb')as stream:
        for chunk in iter(lambda:stream.read(1024**2),b''):h.update(chunk)
    return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())

def verify(row):require(bind(row['path'])=={k:row[k]for k in ('path','bytes','sha256')},'bound new768 input drift '+row['path'])

def read_fullcore(fullcore_sha):
    require(type(fullcore_sha)is str and len(fullcore_sha)==64 and bind(FULL/'session.json')['sha256']==fullcore_sha,'exact ROOT-provided new768 complete session SHA')
    c=json.loads((FULL/'session.json').read_text())
    require(c['state']==STATE and c['source_endcheck']=='PASS' and c['source_tree_baseline']==TOP and c['source_bp']==BP,'new actual clean768 PASS only, no historical/composite transfer')
    labels=['make-preflight','clean','build','loader','integrity-run','integrity-checker','advisory-run','advisory-checker','strict','counter','parameters']
    require([r['label']for r in c['commands']]==labels,'all eleven actual phases')
    for r in c['commands']:
        require(r['ownership']['failure']is None and r['ownership']['owned_group_remaining']is False,'each actual owned phase reaped')
        if r['label']not in ('integrity-run','advisory-run'):require(r['returncode']==r['ownership']['returncode']==0,'every build/checker actual0')
        verify(r['log'])
    for row in c['inputs']:verify(row)
    for row in [c['model'],c['model_stamp'],c['actual_source_list'],c['selection'],c['software_proof'],*c['closed_audits'].values()]:verify(row)
    require(Path(c['model']['path'])==FULL/'verilator/obj_dir/Vbsg_nonsynth_zynq_testbench' and c['model']['bytes']>0 and len(c['model']['sha256'])==64,'actual new768 model, no placeholder')
    stat=Path(c['model']['path']).stat();require((stat.st_ino,stat.st_mtime_ns,stat.st_ctime_ns)==tuple(c['model'][k]for k in ('inode','mtime_ns','ctime_ns')),'original actual model inode/mtime/ctime unchanged')
    selection=json.loads(Path(c['selection']['path']).read_text())
    require(selection['TOP']==TOP and selection['BP']==BP and selection['lines']==768 and selection['workers']==8 and selection['cache']=='off' and selection['PCH']=='off' and selection['TRACE']==1,'actual source/noPCH/8worker selection provenance')
    require(c['geometry']==dict(i_lines=768,d_lines=768,sets=256,epoch=8,line_bytes=64,observe=1,cache_miss_trace=0,delay=0,resident=2,logical=4,l2_bytes=16384,aclk_mhz=20),'exact new768 source geometry')
    strict=json.loads(Path(c['closed_audits']['strict']['path']).read_text());counter=json.loads(Path(c['closed_audits']['counter']['path']).read_text());geo=json.loads(Path(c['closed_audits']['parameters']['path']).read_text())
    require(strict['accepted']is True and counter['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8]),'actual new strict512/eight winning writes/Iretire and independent counters')
    values=geo['facts']['values'];require(len(values)==17 and values['retained_store.storage.i_lines_p']==values['retained_store.storage.d_lines_p']==768 and values['retained_store.storage.sets_p']==256 and geo['facts']['clean_eof']is True,'actual new768 seventeen facts and completeEOF')
    run=json.loads((FULL/'advisory/verification.json').read_text());require(len(run['files'])==6,'complete six-field runtime artifact receipt')
    for row in run['files']:
        verify(row);s=Path(row['path']).stat();require((s.st_ino,s.st_mtime_ns,s.st_ctime_ns)==tuple(row[k]for k in ('inode','mtime_ns','ctime_ns')),'actual closed-run full binding')
    require(run['actual_returncode']==json.loads((FULL/'advisory/process.json').read_text())['returncode'],'same checker-qualified native return, no blanket exception acceptance')
    return c
