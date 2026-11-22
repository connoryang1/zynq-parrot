#!/usr/bin/env python3
"""ROOT-only offline software readback; no board/network/compiler/model/reader."""
import argparse,hashlib,importlib.util,json,os,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
PLAN=Path('/home/coyang/fpga-artifacts/context-resume/csr1536-physical-capacity-readiness-20261122/preparation01/plan.DRAFT.json')

def need(v,m):
    if not v:raise ValueError(m)

def bind(path):
    p=Path(path).resolve();h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024**2),b''):h.update(chunk)
    return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())

def verify(r):need(bind(r['path'])=={k:r[k]for k in ('path','bytes','sha256')},'immutable input drift '+r['path'])

def load(r,name):
    verify(r);spec=importlib.util.spec_from_file_location(name,r['path']);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--authority',type=Path,required=True);ap.add_argument('--authority-sha',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--candidate-lines',type=int,default=1536);args=ap.parse_args()
    need(os.getpid()==os.getpgrp(),'ROOT qualified owned process-group wrapper required')
    need(bind(args.authority)['sha256']==args.authority_sha,'exact fresh ROOT software-only authority')
    a=json.loads(args.authority.read_text());need(a['schema']=='csr-physical-capacity-software-readback-authority-v1' and a['ROOT_approved'] is True and a['resources_verified_by_ROOT'] is True and a['action']=='offline-software-readback-only','DRAFT cannot execute; physical authority is separate')
    need(a['plan']==bind(PLAN) and a['worker']==bind(Path(__file__)) and a['output']==str(args.out) and a['candidate_lines']==args.candidate_lines,'exact software authority/source/output')
    need(args.candidate_lines==1536 and not args.out.exists(),'this packet is candidate1536; fresh metadata output only')
    p=json.loads(PLAN.read_text());need(p['launchable'] is False and p['candidate']['i_lines']==p['candidate']['d_lines']==args.candidate_lines,'not a physical admission')
    for r in p['source_inputs']:verify(r)
    start=time.monotonic()
    def guard():need(time.monotonic()-start<120,'fixed offline readback deadline')
    single=p['software']['single'];joint=p['software']['joint']
    verify(single['manifest']);verify(joint['manifest']);verify(joint['session']);verify(joint['durable_closure'])
    s=json.loads(Path(single['manifest']['path']).read_text());j=json.loads(Path(joint['manifest']['path']).read_text());session=json.loads(Path(joint['session']['path']).read_text())
    need(s['max_lines']==j['max_lines']==1792 and s['max_sets']==j['max_sets']==256,'same complete bounded max1792 fixtures')
    need(session['state']=='PASS one NEW joint guest software/static proof only; no model/audit/board' and session['source_endcheck']=='PASS','actual completed joint compile/static receipt')
    need(all(x['owned']['returncode']==0 and not x['owned']['owned_group_remaining'] for x in session['commands']),'joint compile commands/cleanup')
    verify(s['elf']);verify(j['elf']);verify(j['nbf'])
    need(s['elf']['sha256']==single['ELF_sha256'] and j['elf']['sha256']==joint['ELF_sha256'] and j['nbf']['sha256']==joint['NBF_sha256'],'actual unchanged physical/software payload identities')
    tools=load(p['static_tools'],'bound_joint_static_tools');gen=load(p['generator'],'bound_capacity_generator')
    image,payload=tools.verify_payloads(Path(j['elf']['path']),j['symbols'],gen,guard)
    # The immutable producer JSON serializes these two list-of-tuples fields.
    # Preserve every value/order; accept no arbitrary scalar/type conversion.
    for name in ('hint_sites','checked_compare_failures'):
        pairs=payload['static_CFG'][name]
        need(type(pairs) is list and all(type(pair) is tuple and len(pair)==2 and all(type(v) is int for v in pair) for pair in pairs),'exact source-returned pair type '+name)
        payload['static_CFG'][name]=[list(pair) for pair in pairs]
    need(payload==j['payload_proof'],'all1792 linked joint payload/CFG proof exact; historical256 fields are not a new runtime claim')
    del image
    jc=tools.verify_coverage(Path(j['elf']['path']),Path(j['nbf']['path']),j['payload_proof']['config'],0xc641000000000000)
    need(jc==j['NBF_coverage'],'joint all-file-backed-zero/NBF/46MiB coverage')
    cases={}
    for role in ('d-enabled','d-off','i-enabled','i-off'):
        guard();case=s['cases'][role];verify(case['nbf']);config=case['coverage']['declared_input']
        coverage=tools.verify_coverage(Path(s['elf']['path']),Path(case['nbf']['path']),int(config['address'],16),int(config['value'],16))
        need(coverage==case['coverage'],'same single-role all-byte-zero/46MiB coverage '+role)
        cases[role]=dict(elf=s['elf'],nbf=case['nbf'],coverage=coverage,expected_counts=p['roles'][role]['expected_six_counter_words'])
    cases['joint']=dict(elf=j['elf'],nbf=j['nbf'],coverage=jc,static_CFG=j['payload_proof']['static_CFG'],expected_counts=p['roles']['joint']['expected_six_counter_words'],dynamic_runtime_proof=None)
    need(all(x['coverage']['load_bound']['allocation_bytes']==48234496 and int(x['coverage']['load_bound']['maximum_write_end_exclusive'],16)<=0x82e00000 for x in cases.values()),'actual NBF write-tail within owned46MiB; does not qualify runtime allocation')
    for r in p['source_inputs']:verify(r)
    verify(single['manifest']);verify(joint['manifest']);verify(joint['session']);guard()
    args.out.mkdir();report=dict(schema='csr1536-physical-capacity-software-readback-v1',state='PASS offline byte/static readback only; no physical/native execution authority',candidate_lines=args.candidate_lines,sets=256,max_lines=1792,programs=cases,source_plan=bind(PLAN),authority=bind(args.authority),elapsed_seconds=time.monotonic()-start,requires_fitted_image_and_actual46MiB_runner=True,native_all1536_full167_proof=None,joint_dynamic_target_liveness_proof=None)
    (args.out/'software-readback.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(bind(args.out/'software-readback.json')))

if __name__=='__main__':main()
