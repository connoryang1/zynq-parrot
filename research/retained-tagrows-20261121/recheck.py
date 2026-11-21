#!/usr/bin/env python3
"""Read-only source, component, closed full-core and archive verification."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def require(ok,message):
    if not ok:raise ValueError(message)


def data_check(data,record):
    require(len(data)==record['bytes'] and hashlib.sha256(data).hexdigest()==record['sha256'],'artifact bytes/hash changed')


def check(record):data_check(Path(record['path']).read_bytes(),record)


def main():
    git=lambda path,*args:subprocess.check_output(['git','-C',str(path),*args],text=True).strip()
    require(git(ROOT/'import/black-parrot','rev-parse','HEAD')=='54c065652c4e6079bef4a25ecefd3dd3b859fd36','backend checkpoint changed')
    require(not git(ROOT/'import/black-parrot','status','--porcelain'),'backend source dirty')
    require(git(ROOT,'rev-parse','refs/heads/experiment/linux-retained-native1280-r2')=='15288321bfb1443c5ce39318014f60cd979890f9','baseline r2 moved')
    component=json.loads((HERE/'component-verification.json').read_text())
    host=(HERE/'host-tests.log').read_text()
    require('\nRan 6 tests in ' in host and '\nOK\n' in host,'host checker gate incomplete')
    for name,binding in component['files'].items():data_check((ROOT/name).read_bytes(),binding)
    summary=json.loads((HERE/'component02/summary.json').read_text())
    require(summary['state']=='PASS-tagrow-and-fallback-component-cases' and len(summary['results'])==8,'component matrix incomplete')
    for row in summary['results']:
        for key in ('manifest','service'):check(row[key])
        manifest=json.loads(Path(row['manifest']['path']).read_text())
        require(manifest['state']=='PASS-retained-tagrows' and len(manifest['clock_results'])==2,'component not closed')
        for mode in manifest['clock_results']:check(mode['fst'])
    full=json.loads((HERE/'closure01/verification.json').read_text())
    require(full['state'].startswith('PASS clean tagrow1280'),'whole-core correctness incomplete')
    for record in full['artifacts']:
        check(record['archive'])
        encoded=Path(record['archive']['path']).read_bytes()
        data_check(gzip.decompress(encoded) if record['gzip'] else encoded,record['source'])
    check(full['integrity_trace']);check(full['advisory_trace']);check(full['model'])
    require(full['actual_GP0_counts']=={'i':[1,1,8],'d':[1,1,8]},'observer proof differs')
    require(full['geometry']['tag_rows']==1 and full['geometry']['tag_row_bits']==145
        and full['geometry']['tag_depth']==512 and full['geometry']['payload_slots']==2560
        and full['geometry']['epoch_width']==8,'actual elaborated storage differs')
    for lane in full['advisory_evidence'].values():
        require(lane==dict(publications=1,accepted_hits=1,complete_bursts=1,actual_words=[8],discarded=0),'full-line evidence differs')
    commands=json.loads((HERE/'closure01/audit-commands.json').read_text())
    require([c['label'] for c in commands]==['integrity-geometry','strict-advisory','counter-audit','archive']
        and all(c['returncode']==0 for c in commands),'closed trace audit incomplete')
    for command in commands:
        check(command['log'])
        data_check((HERE/'closure01'/Path(command['log']['path']).name).read_bytes(),command['log'])
    print('PASS 8 component models/16 runs, 6 host fixtures, clean actual fullcore + strict I/D restoration + GP0; no FPGA/performance claim')


if __name__=='__main__':main()
