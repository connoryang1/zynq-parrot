#!/usr/bin/env python3
"""ROOT source-only selection binding; requires reviewed authority, never build."""
import argparse,json
from pathlib import Path
import budget,materialize as source
HERE=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True);a=p.parse_args()
 authority=budget.configure(a.admission,a.admission_sha256);budget.require('fullcore-preflight' in authority['actions'],'ROOT source/preflight approval');budget.check()
 source.verify();out=budget.BASE/'selection.ROOT.json';budget.require(not out.exists(),'new source selection only')
 q=json.loads((HERE/'selection.DRAFT.json').read_text());q.update(state='ROOT APPROVED CSR unmasked256 functional qualification',source_preparation=budget.bind(budget.BASE/'source-preparation.json'),integration_contract=budget.bind(source.GHOST))
 out.write_text(json.dumps(q,indent=2)+'\n');print(json.dumps(budget.bind(out),indent=2))
if __name__=='__main__':main()
