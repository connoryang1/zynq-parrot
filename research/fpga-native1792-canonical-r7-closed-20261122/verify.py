#!/usr/bin/env python3
"""Portable closed-data replay. Optional --external-dcps rehashes two original DCPs; no tools."""
import argparse,gzip,hashlib,json,re
from pathlib import Path
HERE=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def require(p,s):
 if not p:raise ValueError(s)
def verify(root,external=False):
 d=json.loads((root/'bindings.json').read_text());raw=(root/d['upstream_manifest_file']).read_bytes();require(sha(raw)==d['upstream_manifest_sha256']=='e6d59ed8fc1a3a634b5b55038bddc65aa3749d7bd437cc7dad58dd691e02b4b6','root closure hash');u=json.loads(raw)
 texts={}
 for x in d['inputs']+d['r5b_inputs']:
  p=root/x['file'];require(p.resolve().parent.is_relative_to(root.resolve()) if hasattr(Path,'is_relative_to') else str(p.resolve()).startswith(str(root.resolve())+'/'),'safe relative path')
  b=p.read_bytes();plain=gzip.decompress(b);require(sha(b)==x['compressed_sha256'] and len(plain)==x['plain_bytes'] and sha(plain)==x['plain_sha256'],'gzip+roundtrip '+x['file']);texts[x['file']]=plain.decode()
 require(len(d['inputs'])==20,'all20 snapshots');require(u['all_vendor_processes_absent'] and u['worker_absent'] and u['monitor_root_exit']==0,'closed cleanup receipt')
 require(u['monitor_terminal']=='FAIL' and not u['identity_violations'] and not u['bound_violations'],'terminal identity/resource policy')
 for x,row in zip(d['inputs'],u['copies']):require(Path(x['file']).name==Path(row['snapshot']['path']).name and x['compressed_sha256']==row['snapshot']['sha256'] and x['plain_sha256']==row['original']['sha256'] and x['plain_bytes']==row['original']['bytes'],'original root manifest roundtrip binding')
 for x in d['source_objects']:
  b=(root/x['file']).read_bytes();require(sha(b)==x['sha256'] and len(b)==x['bytes'],'public source hash')
 require(sha(texts['r7/019-bp_retained_line_store.sv.gz'].encode())=='68d1dd0c7df7e56ffe76317f9bae5a3ca3e09d13cb44d1167c0f737acefcbea6','actual packaged68d source')
 p=json.loads(texts['r7/001-poll-071.json.gz']);a=json.loads(texts['r7/004-admission.json.gz']);cfg=a['configuration']
 expected={'BP_RETAINED_BUFFER':[1],'BP_RETAINED_I_LINES':[1792],'BP_RETAINED_D_LINES':[1792],'BP_RETAINED_SETS':[256],'BP_RETAINED_OBSERVE':[1],'BP_AXI_RESPONSE_DELAY':[0]}
 require(p['child_actual_features']==expected and p['all_vivado']==[] and p['worker'] is None and p['worker_group']==[],'actual child six flags and terminal process inventory')
 require(not p['identity_violations'] and not p['feedback_warnings'],'actual no feedback/identity violation')
 require(cfg['cfg']=='e_bp_unicore_zynqparrot_prefetch16k_cfg' and cfg['aclk_mhz']==20 and cfg['workers']==8 and cfg['sparse_source']==1,'prospective static config/clock/workers')
 require(u['top']==p['source']['top']=='eb7d390134a0025331a2366a979a774263b146d5' and u['bp']==p['source']['bp']=='8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c','exact TOP/BP source chain')
 require(all(x['selected']==[cfg['cfg']] and sha(x['text'].encode())==x['binding']['sha256'] for x in p['selected_configuration']),'all3 actual selected packages')
 require(len(p['selected_configuration'])==3,'three selected package copies')
 require(any(any('CLKOUT1_REQUESTED_OUT_FREQ' in l and '"20"' in l for l in x['lines']) for x in p['clock_configuration']),'actual20MHz clock wizard intent')
 require(any(any('PCW_FPGA0_PERIPHERAL_FREQMHZ' in l and '"50"' in l for l in x['lines']) for x in p['clock_configuration']),'PS upstream50MHz recorded separately')
 require(a['resources']=={'work_cap_bytes':2684354560,'evidence_cap_bytes':402653184,'work_floor_bytes':1073741824,'home_floor_bytes':3221225472,'shm_floor_bytes':536870912,'deadline_seconds':10800},'unchanged prelaunch split-volume budgets')
 def util(s,name):
  m=re.search(r'\|\s*'+re.escape(name)+r'\s*\|\s*(\d+)\s*\|',s);require(m is not None,'report row '+name);return int(m[1])
 def place(s):
  m=re.search(r'of which (\d+) slices are available.*?unplaced instances require (\d+) slices',s);require(m is not None and '[Place 30-487]' in s,'actual detailed placement error');av,req=map(int,m.groups());return dict(available_remaining_slices=av,required_remaining_slices=req,gap=req-av,control_sets=int(re.search(r'Control sets: (\d+)',s)[1]),combined_LUT=int(re.search(r'Luts: (\d+) \(combined\)',s)[1]),total_LUT=int(re.search(r'\(combined\) (\d+) \(total\)',s)[1]),FF=int(re.search(r'Flip flops: (\d+)',s)[1]))
 synth=texts['r7/012-black_parrot_bd_1_wrapper_utilization_synth.rpt.gz'];s7={k:util(synth,n) for k,n in [('LUT','Slice LUTs*'),('logic_LUT','LUT as Logic'),('memory_LUT','LUT as Memory'),('FF','Slice Registers'),('BRAM_tiles','Block RAM Tile')]};require(s7==u['synthesis'],'actual synth report matches root facts')
 p7=place(texts['r7/015-runme.log.gz']);p5=place(texts['r5b/012-runme.log.gz']);require(p7==u['placement'] and p7['gap']==404 and p5['gap']==822,'both actual same-stage packing gaps')
 s5raw=texts['r5b/018-black_parrot_bd_1_wrapper_utilization_synth.rpt.gz'];s5={k:util(s5raw,n)for k,n in [('LUT','Slice LUTs*'),('FF','Slice Registers'),('BRAM_tiles','Block RAM Tile')]};require(s5==dict(LUT=56251,FF=33071,BRAM_tiles=140),'r5b actual synth rows')
 synlog=texts['r7/011-runme.log.gz'];require('lane_fsm[1].distributed_epochs.epoch_ram/mem_reg' in synlog and 'RAM64M x 24' in synlog,'canonical D epoch inference row');require('[Synth 8-326]' not in texts['r7/006-console.log.gz'],'no actual feedback-cut warning in full console');require('Command: route_design' not in texts['r7/006-console.log.gz'],'route not reached')
 topcfg=(root/'source/bp_common_pkg.sv').read_text();basecfg=(root/'source/bp_common_aviary_cfg_pkgdef.svh').read_text()
 for pattern in (r'icache_sets\s*:\s*64',r'icache_assoc\s*:\s*8',r'icache_block_width\s*:\s*512',r'dcache_sets\s*:\s*64',r'dcache_assoc\s*:\s*8',r'dcache_block_width\s*:\s*512',r'l2_assoc\s*:\s*2',r'l2_block_width\s*:\s*512'):require(re.search(pattern,basecfg) is not None,'source geometry '+pattern)
 require("'{l2_banks: 2" in topcfg and "'{l2_sets: 64" in topcfg and 'e_bp_unicore_zynqparrot_prefetch16k_cfg' in topcfg,'static16k source overrides')
 if external:
  for row in d['external_checkpoints_verified']:
   q=Path(row['path']);b=q.read_bytes();require(len(b)==row['bytes'] and sha(b)==row['sha256'],'external DCP '+row['kind'])
 q=d['optimized_query'];qr=(root/q['session_file']).read_bytes();require(sha(qr)==q['session_sha256'],'closed query session');qs=json.loads(qr);require(qs['state'].startswith('PASS') and qs['returncode']==0 and qs['DCP_unchanged'] and qs['input_DCP']==qs['input_DCP_after'],'closed read-only query unchanged DCP')
 require(qs['input_DCP']['sha256']==u['checkpoints'][1]['snapshot']['sha256'] and len(q['outputs'])==22,'optimized input and all22outputs')
 qt={}
 for x,row in zip(q['outputs'],qs['outputs']):
  b=(root/'optimized-query'/x['file']).read_bytes();plain=gzip.decompress(b);require(sha(b)==x['compressed_sha256'] and len(plain)==x['plain_bytes'] and sha(plain)==x['plain_sha256']==row['sha256'] and len(plain)==row['bytes'],'closed query lossless '+x['file']);qt[Path(row['path']).name]=plain.decode()
 opt={k:util(qt['utilization_flat.rpt'],n) for k,n in [('LUT','Slice LUTs*'),('logic_LUT','LUT as Logic'),('memory_LUT','LUT as Memory'),('FF','Slice Registers'),('BRAM_tiles','Block RAM Tile')]};require(opt==dict(LUT=54170,logic_LUT=50253,memory_LUT=3917,FF=31011,BRAM_tiles=140),'actual optimized whole resource rows')
 focused={i:{k:util(qt['focused-%02d.rpt'%i],n) for k,n in [('LUT','Slice LUTs*'),('FF','Slice Registers'),('BRAM_tiles','Block RAM Tile')]} for i in (0,4,5,6)}
 require(util(qt['focused-06.rpt'],'LUT as Logic')==969 and util(qt['focused-06.rpt'],'LUT as Memory')==128,'optimized backend logic/memory subcounts')
 require(focused=={0:dict(LUT=37516,FF=17782,BRAM_tiles=77),4:dict(LUT=2779,FF=2998,BRAM_tiles=0),5:dict(LUT=3011,FF=2839,BRAM_tiles=0),6:dict(LUT=1097,FF=2211,BRAM_tiles=56)},'optimized focused nonadditive groups')
 rows=[x.split('\t') for x in qt['primitive-counts.tsv'].splitlines()[1:]]
 def count(component,group,kind):return sum(int(n) for c,g,k,n in rows if c==component and g==group and k.startswith(kind))
 primitive_groups={}
 for c in ('I_UCE','D_UCE'):
  primitive_groups[c]={g:count(c,g,'FD') for g in sorted(set(x[1] for x in rows if x[0]==c))}
 epoch_counts={k:count('retained_D','epoch_storage_or_access_named',k) for k in ('RAM64M','RAMD64E','FD')}
 require(epoch_counts==dict(RAM64M=24,RAMD64E=96,FD=9),'D epoch mapped parent/leafRAM and access-FF counts (not additive)')
 for c in ('I_UCE','D_UCE'):
  require(primitive_groups[c]['staging_RAM_or_interface_named']==512 and primitive_groups[c]['retained_capture_response_buffer_or_mux_named']==1536,'UCE named line-register groups '+c)
 require('distributed_epochs.epoch_ram' in qt['retained-RAM-ports.tsv'],'actual optimized canonical epoch RAM inventory')
 require(not list(root.rglob('*.dcp')) and sum(p.stat().st_size for p in root.rglob('*') if p.is_file())<=8*1024**2,'compact<=8MiB no DCP')
 return dict(state='PASS closed replay; actual placement FAIL/no route',gzip_roundtrips=20,public_sources=len(d['source_objects']),six_child_flags=expected,geometry=dict(L1I_bytes=32768,L1D_bytes=32768,L2_banks=2,L2_sets_per_bank=64,L2_ways=2,line_bytes=64,L2_bytes=16384),r7_synthesis=s7,r7_placement=p7,r5b_synthesis=s5,r5b_placement=p5,optimized_whole=opt,optimized_focused_nonadditive=focused,optimized_FD_name_groups=primitive_groups,D_epoch_parent_leaf_counts_not_additive=epoch_counts,external_DCPs_rehashed=external,interpretation='Same-stage resource comparison only. Packing gap cannot be converted to hard LUT-saving requirement; no maxcapacity/fit/timing/application claim.')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=HERE);ap.add_argument('--external-dcps',action='store_true');a=ap.parse_args();print(json.dumps(verify(a.root,a.external_dcps),indent=2))
if __name__=='__main__':main()
