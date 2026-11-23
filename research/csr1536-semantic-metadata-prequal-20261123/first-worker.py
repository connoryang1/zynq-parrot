import sys,json,hashlib,os,importlib.util
from pathlib import Path
sys.dont_write_bytecode=True
R=Path(__file__).parent
P=Path('/home/coyang/zynq-parrot-retained-metadata/research/csr1536-capacity-semantic-adapter-20261122')
def bind(p):b=Path(p).read_bytes();return dict(path=str(Path(p)),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def exact(r):assert bind(r['path'])==r;return json.loads(Path(r['path']).read_text())
assert os.getpid()==os.getpgrp()
a=exact(json.loads((R/'authority-binding.json').read_text()));assert a['ROOT_approved'] and a['action']=='metadata-constructors-only'
for r in a['inputs']:assert bind(r['path'])==r
sys.path.insert(0,str(P));import csr1536_profile as s
ctx=s.load_context();program=exact(ctx.anchors['programs']['single']['manifest']);rows=[]
for row in json.loads((R/'references.json').read_text()):
 exact(row['acceptance']);proof=exact(row['proof']);counts=exact(row['counters'])
 n=256 if row['group']=='control256' else 1536
 v=s.Validator(program,row['role'],s.geometry(n),ctx)
 expected={k:t for k,t in proof['targets'].items() if t['slot']<n};actual={str(k):t for k,t in v.targets.items()}
 assert len(actual)==len(expected)==n and actual==expected
 if n==256:assert s.expected_counters(v.profile,row['role'])==counts['values']
 rows.append(dict(group=row['group'],role=row['role'],lines=n,targets_exact=True,comparison='completed proof target-map metadata; not new trace execution',proof=row['proof']))
 del v,proof
# Joint has no prior dynamic proof. Compare both constructed target payload sets
# against the actual unchanged ELF bytes, independent of returned count labels.
j=exact(ctx.anchors['programs']['joint']['manifest']);v=s.JointValidator(j,s.geometry(1536),ctx)
tools_row=a['static_tools'];assert bind(tools_row['path'])==tools_row
sp=importlib.util.spec_from_file_location('bound_elf_static_readback',tools_row['path']);tools=importlib.util.module_from_spec(sp);sp.loader.exec_module(tools)
assert bind(j['elf']['path'])=={k:j['elf'][k] for k in ('path','bytes','sha256')};image=tools.image_from_elf(Path(j['elf']['path']))
joint=[]
for lane,l in v.lanes.items():
 width=4 if lane=='i' else 8
 for address,t in l.targets.items():
  expected=b''.join(w.to_bytes(width,'little') for w in t['words']);assert len(expected)==64
  assert bytes(image[address+k] for k in range(64))==expected
 joint.append(dict(lane=lane,lines=len(l.targets),linked_payload_bytes=64*len(l.targets),all_bytes_equal=True))
for r in a['inputs']:assert bind(r['path'])==r
out=dict(state='PASS metadata constructor compatibility and joint linked-ELF payload checks; no new events/native/FPGA',single_comparisons=rows,joint_linked_payloads=joint,current_expected_joint=s.expected_counters(s.geometry(1536),'joint'),geometry_profile='explicit1536/256',model_executed=False,FST_read=False,board_actions=False,limits='Prior dynamic proofs are constructor metadata references only. No new1536 dynamic/complete-stream/counter/EOF/physical acceptance.',authority=bind(R/'authority.json'))
(R/'result.json').write_text(json.dumps(out,indent=2)+'\n');print(out['state'])
