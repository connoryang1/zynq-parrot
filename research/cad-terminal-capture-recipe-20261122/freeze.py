#!/usr/bin/env python3
"""ROOT-only formal future freeze after independently reviewed full preservation."""
import argparse,json,time
from pathlib import Path
import capture as c

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--admission',type=Path,required=True);ap.add_argument('--admission-sha256',required=True);ap.add_argument('--independent',type=Path,required=True);ap.add_argument('--independent-sha256',required=True);args=ap.parse_args()
 c.DEADLINE=time.monotonic()+180
 ab=c.bind(args.admission);c.need(ab['sha256']==args.admission_sha256,'exact ROOT capture admission');a=json.loads(args.admission.read_text());c.terminal(a)
 ir=c.bind(args.independent);c.need(ir['sha256']==args.independent_sha256,'exact separate ROOT verification')
 q=json.loads(args.independent.read_text());c.need(q['schema']=='cad-terminal-independent-verification-v1' and q['ROOT_verified'] is True,'separate ROOT independent full verification required')
 out=Path(a['output']);mp=out/'manifest.json';ip=out/'inventory.json';m=json.loads(mp.read_text());inv=json.loads(ip.read_text())
 c.need(q['capture']==c.bind(mp) and q['inventory']==c.bind(ip) and q['admission']==ab,'same exact completed capture')
 c.need(str(m['state']).startswith('PASS') and m['all_originals_unchanged'] is True,'completed preserved capture')
 c.need(q['all_new_archive_members_verified'] is True and q['all_opaque_references_verified'] is True and q['all_original_paths_covered'] is True,'ROOT complete coverage, not sample/hash projection')
 c.need(m['no_reservation_release'] is True,'capture did not already release')
 c.refs(a);c.stable(a,inv);c.guard(a,True);c.absent(a)
 dest=out/'freeze';c.need(not dest.exists(),'fresh one-shot formal freeze')
 # Preserve all output identities before adding receipts; original source roots
 # are outside OUT and are rechecked independently above.
 output_rows=[c.row(p,'CAPTURE',out,a) for p in [out]+sorted(out.rglob('*'))]
 pair=a['job']+'-terminal-full-preservation'
 dest.mkdir();marker=dest/'complete.json'
 base=dict(schema='cad-terminal-family-freeze-v1',ROOT_verified=True,freeze_pair_id=pair,admission=ab,capture=c.bind(mp),independent=ir,original_limits_unchanged=True,all_actual_files_still_charged=True,future_growth_reserved_bytes=0,requires_complete_marker=dict(path=str(marker),freeze_pair_id=pair),future_writes_require_new_admission=True)
 work=[r for r in inv['members'] if r['member']=='WORK' or r['member'].startswith('WORK/')]
 evidence=[r for r in inv['members'] if r['member'].split('/')[0] in ('ART','LOGS')]
 c.need(work and evidence,'complete WORK and aggregate evidence namespaces')
 c.write(dest/'work.json',dict(base,family='WORK',root=a['roots']['WORK'],original_cap_bytes=a['original_limits']['work_cap_bytes'],members=work,no_deletion=True))
 c.write(dest/'evidence.json',dict(base,family='aggregate-EVIDENCE-and-capture',roots=[a['roots']['ART'],a['roots']['LOGS'],a['output']],original_evidence_cap_bytes=a['original_limits']['evidence_cap_bytes'],prospective_capture_cap_bytes=a['output_family_cap_bytes'],members=evidence,capture_output_members=output_rows,opaque_references=a['opaque_references'],no_deletion=True))
 c.refs(a);c.stable(a,inv);c.absent(a);c.guard(a,True)
 c.write(marker,dict(schema='cad-terminal-freeze-complete-v1',state='PASS ROOT-reviewed complete terminal preservation and paired future freeze; no fit interpretation',freeze_pair_id=pair,job=a['job'],TOP=a['TOP'],BP=a['BP'],work=c.bind(dest/'work.json'),evidence=c.bind(dest/'evidence.json'),independent=ir,admission=ab,no_cleanup=True,no_native_or_other_reservation_release=True))
 print(json.dumps(c.bind(marker),indent=2))
if __name__=='__main__':main()
