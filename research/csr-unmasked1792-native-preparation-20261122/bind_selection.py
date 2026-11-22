#!/usr/bin/env python3
"""Source/software binding only; does not launch any build or target."""
import argparse,json
from pathlib import Path
import materialize as source,budget
def main():
 p=argparse.ArgumentParser();p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True);a=p.parse_args();authority=budget.configure(a.admission,a.admission_sha256);budget.require('fullcore-preflight' in authority['actions'],'ROOT preflight role')
 source.verify();out=budget.BASE/'selection.ROOT.json';budget.require(not out.exists(),'fresh1792 selection');s=json.loads((budget.HERE/'selection.DRAFT.json').read_text());s.update(state='ROOT SELECTED conditional1792 source/software; full execution independently gated',source_preparation=budget.bind(budget.BASE/'source-preparation.json'))
 out.write_text(json.dumps(s,indent=2)+'\n');print(json.dumps(budget.bind(out),indent=2))
if __name__=='__main__':main()
