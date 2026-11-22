#!/usr/bin/env python3
"""Independently inspect sealed I-only semantic proof; never run a model/FST reader."""
import argparse,collections,gzip,hashlib,importlib.util,json,struct
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=Path('/home/coyang/fpga-artifacts/context-resume/retained1792-stream-canonical-20261121')
GOOD=BASE/'accepted-i-enabled-audit01';NATIVE=BASE/'i-enabled-native01'
PRODUCER='/home/coyang/zynq-parrot-linux-host-observer/research/retained1792-audit-continuation-20261121/continuation.py'
PRODUCER_SHA='96e91eac0aed1085078f4a23c5360cc87ee0d31b241cca792d2e7d04b033cb00'
MODEL_SHA='b9f7f127121d750591513372a5d2e342046098a58984384e0f5b57b35b00b3e7'

def require(ok,message):
    if not ok:raise ValueError(message)
def bind(path):
    p=Path(path).resolve();b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def verify_local_copy(row,local):
    require(row['path']==PRODUCER and row['sha256']==PRODUCER_SHA,'fixed producer path/source anchor')
    require(bind(PRODUCER)==row,'original producer bytes')
    actual=bind(local)
    require(all(actual[k]==row[k] for k in ('bytes','sha256')),'local import must match producer bytes, not its pathname')
    return Path(local)
def code_words(index):
    instructions=[(index<<20)|(10<<7)|0x13]
    for k in range(1,8):
        immediate=((index+1)*(2*k+1)+37*k)&2047
        instructions.extend(((6<<20)|(10<<15)|(1<<12)|(10<<7)|0x13,(immediate<<20)|(10<<15)|(4<<12)|(10<<7)|0x13))
    instructions.append(0x8067)
    return [instructions[n]|(instructions[n+1]<<32) for n in range(0,16,2)]
def oracle(program):
    require(program['max_lines']==program['code_functions']==1792 and program['max_sets']==256 and program['code_stride']==192,'fixed linked generation geometry')
    result={}
    for slot in range(1792):
        index=(slot&~255)+((slot*0xaaaaaaaaaaaaaaab)&255)
        result[str(program['code_base']+192*index)]=dict(slot=slot,index=index,words=code_words(index))
    require(len(result)==1792 and set(collections.Counter((int(a)>>6)&255 for a in result).values())=={7},'1792 unique addresses, seven per retained set')
    return result

def inspect_semantics(full,expected):
    require(full['state']=='PASS actual distinct configured-line publications/hits/full-SRAM payload and checked execution','complete positive state')
    require(full['lane']=='i' and full['lines']==1792 and full['sets']==256,'strict I-only geometry')
    require(full['targets']==expected,'all target addresses/slots/full512-bit independent oracle')
    targets=set(expected)
    require(all(set(full[k])==targets for k in ('publications','hits','retained_bursts','retired_instruction_pcs')),'every distinct target published/hit/restored/retired')
    require(full['ordinary_bursts']=={} and full['d_protected_load_retirements']==0,'I-only no target ordinary refill or D protected load')
    begin,verify,end=(full['markers'][k] for k in ('populate_begin','verify_begin','verified'))
    require(begin<verify<end,'ordered retired phase markers')
    require(max(p['time'] for p in full['publications'].values())<min(h['lookup'] for h in full['hits'].values()),'all target publications before first demand lookup')
    for address,target in expected.items():
        addr=int(address);pub=full['publications'][address];hit=full['hits'][address];burst=full['retained_bursts'][address]
        require(begin<=pub['accepted']<pub['time']<verify<=hit['lookup']<hit['time']<burst['time']<end,'per-target completed publication/hit/restore ordering')
        require(burst['retained'] is True and burst['address']==burst['request']==addr and 0<=burst['way']<8,'I demand starts at target word0 and retained owner')
        words=burst['words'];require(len(words)==8,'eight complete words')
        require([w['address'] for w in words]==[addr+8*i for i in range(8)],'eight ascending SRAM word addresses')
        require([w['data'] for w in words]==target['words'],'all actual serialized full512-bit SRAM data')
        require([w['bank'] for w in words]==[(i+burst['way'])%8 for i in range(8)],'actual all-eight-bank rotation for accepted way')
        require(words[0]['time']==burst['time'] and all(words[i]['time']<words[i+1]['time'] for i in range(7)) and words[-1]['time']<end,'all actual writes ordered and complete')
        require(full['retired_instruction_pcs'][address]==list(range(addr,addr+64,4)),'all16 target instruction PCs retired once in order')
    return dict(targets=1792,payload_bytes=1792*64,actual_sram_words=1792*8,ordered_instruction_retirements=1792*16)

def elf_spans(path):
    raw=Path(path).read_bytes();require(raw[:6]==b'\x7fELF\x02\x01','ELF64LE')
    offset=struct.unpack_from('<Q',raw,32)[0];size,count=struct.unpack_from('<HH',raw,54);spans=[]
    for n in range(count):
        kind,flags,off,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',raw,offset+n*size)
        if kind==1:
            require(va==pa and 0x80000000<=pa and pa+memsz<=0x80000000+46*1024**2,'actual linked physical bounds')
            spans.append((pa,raw[off:off+filesz]))
    require(spans,'loadable ELF');return spans

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',required=True,type=Path);args=ap.parse_args()
    require(not args.out.exists(),'fresh review output required')
    closure=GOOD/'root-closure.json';native_closure=NATIVE/'root-closure.json'
    require(bind(closure)['sha256']=='303d7427bea5fc67aa845e165cb6498e0550caa70309fef42e4dafe100d5ecbc','externally supplied I audit closure anchor')
    require(bind(native_closure)['sha256']=='8b1f6fe032e0da514889177877b8cee27024ff65f433accac4fcca1e4af64f43','externally supplied I native closure anchor')
    closed=json.loads(closure.read_text());native_closed=json.loads(native_closure.read_text());mapping={}
    for doc in (closed,native_closed):
        for row in doc['records']:
            if not row['path'].endswith('/trace.fst'):
                require(bind(row['path'])=={k:row[k] for k in ('path','bytes','sha256')},'durable-copy identity')
            mapping[row['original']]=row
    # The earlier stopped packet carries the unchanged original preparation and runtime snapshot.
    stopped_path=BASE/'stopped-audit01/root-stop.json'
    require(bind(stopped_path)['sha256']=='cf8cdaa0b987406a1ffaf94a3386fc33b5c562e8dc75add5d7d5af6431b87bcb','explicit earlier failure remains sealed')
    for row in json.loads(stopped_path.read_text())['records']:mapping.setdefault(row['original'],row)
    def resolve(row):
        if row['path'] in mapping:
            copied=mapping[row['path']];require(all(row[k]==copied[k] for k in ('bytes','sha256')),'original/copy exact identity')
            if not row['path'].endswith('/trace.fst'):require(bind(copied['path'])=={k:copied[k] for k in ('path','bytes','sha256')},'resolved durable bytes')
            return Path(copied['path'])
        require(bind(row['path'])==row,'bound source or metadata bytes');return Path(row['path'])
    audit=GOOD/'i-enabled-audit';accepted=json.loads((audit/'acceptance.json').read_text())
    require(bind(audit/'acceptance.json')['sha256']==closed['acceptance_sha256']=='90ebfd03eaf351445d4069b7ee3eba2b6a7c21c79927c75204ccae4bd5d394ac','fixed I acceptance')
    require(accepted['schema']=='retained1792-stream-continuation-acceptance-v1' and accepted['role']=='i-enabled' and accepted['attempt']==1 and accepted['inherited_native'] is False,'fresh I role, not inherited D retry')
    require(closed['audit_exit']==0 and native_closed['native_outer_exit']==0,'actual root native/audit wrapper exits')
    for row in accepted['sources']+accepted['files']:resolve(row)
    bridge=json.loads(resolve(accepted['preparation']).read_text())
    for row in bridge['sources']:resolve(row)
    producer=[r for r in bridge['sources'] if r['path']==PRODUCER];require(len(producer)==1,'one fixed producer contract')
    local=verify_local_copy(producer[0],HERE/'producer/continuation.py')
    spec=importlib.util.spec_from_file_location('sealed_i_continuation',local);c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
    for row in c.PINS:resolve(row)
    preparation=json.loads(resolve(bridge['original_preparation']).read_text())
    require(bridge['geometry']==preparation['geometry']==c.GEOMETRY and preparation['schedule']==['d-enabled','d-off','i-enabled'],'unchanged original fixed cohort geometry/order')
    require(accepted['sources']==preparation['runtime_sources'],'exact original audit implementation')
    for key in ('model_approval','canonical_fullcore','observation_qualification','compiled_sources','model_stamp','host_admission'):resolve(preparation[key])
    approval=json.loads(resolve(preparation['model_approval']).read_text())
    require(all(approval['checks'].values()) and all(approval[k]==preparation[k] for k in ('model','canonical_fullcore','observation_qualification','compiled_sources','model_stamp','geometry')),'qualified source/model/trace bridge')
    critical=c.original.source_bindings(resolve(preparation['compiled_sources']))
    native=json.loads((NATIVE/'verification.json').read_text());ad=json.loads((NATIVE/'admission.json').read_text())
    require(bind(NATIVE/'verification.json')['sha256']==accepted['native_sha256']==closed['native_sha256']==native_closed['native_sha256']=='f2b0c4ed628950892a1887a846f9636de57b996e16c2be6d27d9c5f07d01f10f','fresh exact native I proof')
    require(native['role']==ad['role']=='i-enabled' and native['counters']==[1792,0,1792,0,14336,0] and native['primary_use_gate_rejected'] is False,'native actual I-only counters')
    require(native['admission']==dict(path=next(r['original'] for r in native_closed['records'] if r['path'].endswith('/admission.json')),**{k:bind(NATIVE/'admission.json')[k] for k in ('bytes','sha256')}),'native admission bytes')
    require(ad['preparation']==accepted['preparation'] and ad['program']==preparation['program'] and ad['model']==preparation['model'] and ad['compiled_sources']==preparation['compiled_sources'],'native same source/model/software boundary')
    require(json.loads(resolve(ad['runtime_sources']).read_text())==preparation['runtime_sources'],'actual runtime snapshot exact')
    require(ad['coverage']['missing_bytes']==ad['coverage']['wrong_bytes']==0 and ad['coverage']['load_bound']['allocation_bytes']==46*1024**2,'actual complete zero-preserving bounded NBF coverage receipt')
    for row in native['files']:
        if not row['path'].endswith('/trace.fst'):resolve(row)
    require(json.loads((NATIVE/'process.json').read_text())['returncode']==native['actual_returncode']==-6,'actual known post-PASS simulator shutdown return')
    checker_path=next(r for r in accepted['sources'] if r['path'].endswith('/testing/check_run.py'))
    spec=importlib.util.spec_from_file_location('sealed_i_checker',resolve(checker_path));checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    text=(NATIVE/'run.log').read_text();checker.check_transcript(text,-6)
    marker='[BSG-PASS] retained capacity checked all full64B payloads completed'
    require(text.count(marker)==1 and text.index(marker)<checker.CORE_PASS.search(text).start(),'complete payload before CORE/HOST PASS')
    life=json.loads((NATIVE/'run.owned.json').read_text());require(life['failure'] is None and not life['owned_group_remaining'] and life['returncode']==-6 and life['argv']==ad['command'],'actual owned native command and reaping')
    full=json.loads((audit/'verification.json').read_text())
    for key,row in full['bindings'].items():
        if key not in ('model','fst'):resolve(row)
    require(full['bindings']['model']==preparation['model'] and full['bindings']['model']['sha256']==MODEL_SHA,'same qualified b9f7 model')
    model_path=Path(full['bindings']['model']['path']);model_rehashed=False
    if model_path.is_file():require(bind(model_path)==full['bindings']['model'],'accessible actual model binary');model_rehashed=True
    program=json.loads(resolve(full['bindings']['program']).read_text());expected=oracle(program)
    producer_expected=json.loads(json.dumps(c.original.Validator(program,'i-enabled').targets))
    require(expected==producer_expected,'independent analytic oracle equals pinned producer static oracle')
    summary=inspect_semantics(full,expected)
    elf=resolve(ad['elf']);require(ad['elf']['sha256']==program['elf']['sha256'],'same physical/simulation ELF bytes')
    require(ad['nbf']['sha256']==program['cases']['i-enabled']['nbf']['sha256'],'same declared I input NBF')
    spans=elf_spans(elf)
    for address,target in expected.items():
        addr=int(address);found=[data[addr-base:addr-base+64] for base,data in spans if base<=addr and addr+64<=base+len(data)]
        require(len(found)==1 and found[0]==struct.pack('<8Q',*target['words']),'all1792 linked64B/16instruction functions')
    stream=full['archive']['full_stream']
    require(stream==dict(sha256='4ee094ad1af4923fa8938a1e39611749385e3ffac9ca1a2efe10888ae24e8ab1',bytes=328291224,lines=15104105,events=15103936,counter_events=17923,exact_end_records=1,reader_returncode=0),'complete unchanged full167 receipt')
    handles={};last={};events=0;ended=False
    with gzip.open(resolve(full['archive']['counter_projection']),'rt') as f:
        for line in f:
            fields=line.rstrip('\n').split('\t')
            if fields[0]=='#SIGNAL':
                require(not ended and fields[1] in ('obs.hits','obs.published','obs.beats') and fields[1] not in handles and fields[2]=='32','three explicit counter projection signals');handles[fields[1]]=int(fields[3])
            elif fields[0]=='#END':require(not ended and line=='#END\n','one exact projection EOF');ended=True
            elif not fields[0].startswith('#'):
                require(not ended and len(handles)==3 and int(fields[1]) in handles.values() and len(fields[2])==32 and set(fields[2])<=set('01'),'only complete counter events');last[int(fields[1])]=int(fields[2],2);events+=1
    values=[]
    for name in ('obs.hits','obs.published','obs.beats'):
        word=last[handles[name]];values.extend((word&65535,word>>16))
    require(ended and events==17923 and values==native['counters'],'independent FST projection equals actual GP0 reads')
    counter=json.loads((audit/'counter-words.json').read_text());adapter=json.loads((audit/'counter-check-input/verification.json').read_text())
    require(counter['values']==values and counter['audit']==next(r for r in accepted['files'] if r['path'].endswith('/counter-check-input/verification.json')) and adapter['full_audit']==next(r for r in accepted['files'] if r['path'].endswith('/i-enabled-audit/verification.json')),'counter projection/full audit adapter cannot impersonate full167 proof')
    for name in ('reader.owned.json','counter-checker.owned.json'):
        life=json.loads((audit/name).read_text());require(life['returncode']==0 and life['failure'] is None and life['owned_group_remaining'] is False,'actual0 and owned groups reaped')
    prior=[]
    for relative,sha in [('accepted-d-enabled-audit02/d-enabled-audit-attempt2/acceptance.json','82b333fb26766421d127cdd2bee6c657368444a82d247de8440d9edfed5e01bc'),('accepted-d-off-audit01/d-off-audit/acceptance.json','b3836100e588c699b4ecc7be92983637aadd4b90c332480e11b7bd53a7ef6309')]:
        require(bind(BASE/relative)['sha256']==sha,'sealed fixed earlier cohort acceptance');prior.append(sha)
    require(prior==closed['prior_audit_sha256'],'fixed D/on/off evidence precedes I')
    report=dict(state='PASS independent I-only1792 full-payload serialized-proof review',root_closure=bind(closure),native_closure=bind(native_closure),acceptance=bind(audit/'acceptance.json'),prior_acceptance_sha256=prior,summary=summary,publications=1792,hits=1792,retained_bursts=1792,ordinary_bursts=0,counter_words=values,full_stream=stream,markers=full['markers'],critical_sources=critical,model=full['bindings']['model'],actual_model_rehashed=model_rehashed,raw_fst=full['bindings']['fst'],raw_fst_replayed=False,producer_original=producer[0],
        limits='Simulation I-only112KiB proof, separately complements D112KiB. No simultaneous joint224KiB workload, routed/physical capacity or application gain. Independent serialized all-target SRAM words/banks/PC order, linked ELF and counter projection; actual handshake/opcode/publication-hit512 checks inherited from exact reviewed full167 Validator receipt. Fullbackend mapped Xsim remains separate/open. Synthetic phase endpoints exclude mode setup/reset/drain/report and are not complete-COST timing.')
    with args.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(dict(state=report['state'],report=bind(args.out)),sort_keys=True))
if __name__=='__main__':main()
