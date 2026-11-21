#!/usr/bin/env python3
"""Close exact source/functional component proof; no models or vendor tools run."""
from pathlib import Path
import json
from run import HERE,SRC,bind,require,guard
old=(SRC/'reference-bp225.sv').read_text();candidate=(SRC/'bp_retained_line_store.sv').read_text()
production=Path('/home/coyang/zynq-parrot-retained-dense/import/black-parrot/bp_common/src/v/bp_retained_line_store.sv')
require(production.read_text()==old and bind(production)['sha256']=='bd4cd65c92bdaf8af80c9c6f4643383c8bfa7fd335ca131319d44c2e45ee2e24','frozen production must be untouched BP225')
require((SRC/'bp_retained_line_store_reference.sv').read_text()==old.replace('module bp_retained_line_store\n','module bp_retained_line_store_reference\n'),'reference only module rename')
start='    if ((lane != 0) && (lines_lp >= sets_p)) begin : distributed_epochs\n';end='    if (lines_lp >= sets_p) begin : distributed_rr\n'
a,b=old.index(start),old.index(end,old.index(start));c,d=candidate.index(start),candidate.index(end,candidate.index(start))
expected_prefix=old[:a].replace('    (* ram_style = "distributed" *) logic [epoch_width_p-1:0] epochs_r [sets_p];\n','').replace('&& (&epochs_r[inv_set])','&& (&inv_epoch)').replace('    wire [epoch_width_p-1:0] line_epoch = epochs_r[epoch_read_set];','    wire [epoch_width_p-1:0] line_epoch, inv_epoch;')
require(candidate[:c]==expected_prefix and candidate[d:]==old[b:],'all non-epoch RTL must be byte-identical')
fallback=old[a:b].split('    end else begin : flop_epochs\n',1)[1]
require(candidate[c:d].endswith(fallback),'I/small/disabled fallback sequential statements unchanged')
root=HERE/'corrected-miter-02';session=json.loads((root/'session.json').read_text())
require(session['state']=='PASS-component-cycle512b-all-epoch-cells-coherence-plus-negative','corrected full component session not PASS')
for row in session['sources']:require(bind(row['path'])==row,'corrected frozen source drift')
require((root/'source/bp_retained_epoch_ram.sv').read_bytes()==(SRC/'bp_retained_epoch_ram.sv').read_bytes() and (root/'source/bp_retained_line_store.sv').read_text()==candidate,'actual compiled candidate bytes differ')
wrapper=(root/'source/retained_metadata_wrapper.sv').read_text()
require("mismatch_o[l] = epoch_mismatch;" in wrapper and "mismatch_o[l] |= ({lookup_ready_o[l]" in wrapper,'all-cell comparison must survive active protocol OR')
normal=[r for r in session['runs'] if not r['expected_rejection']];negative=[r for r in session['runs'] if r['expected_rejection']]
require(len(normal)==6 and len(negative)==1,'exact six normal plus one negative runs')
for r in session['runs']:
 require(bind(r['fst']['path'])==r['fst'] and bind(r['log']['path'])==r['log'],'closed FST/log drift')
 require(r['returncode']==(1 if r['expected_rejection'] else 0),'actual expected component status')
for r in session['executables'].values():require(bind(r['path'])==r,'actual tested component model drift')
witness_path=HERE/'negative-allcell-witness/manifest.json';witness=json.loads(witness_path.read_text())
require(witness['state']=='PASS-expected-negative-explicit-D-epoch-allcell-witness','explicit negative all-cell witness required')
for r in witness['original_object_inventory']:require(bind(r['path'])==r,'witness changed original RTL/runtime object')
require('epochI=0 epochD=1 protocol=0 candidate_set0=255 reference_set0=0 candidate_stateD=0 reference_stateD=0' in Path(witness['log']['path']).read_text(),'all-cell-only negative cause')
for row in session['commands']:
 require(row['returncode']==0 and row['seconds']<300,'bounded clean component builds')
output=dict(state='PASS-canonical-epoch-functional-handoff-no-inference-claim',production=bind(production),candidate_module=bind(SRC/'bp_retained_epoch_ram.sv'),candidate_backend=bind(SRC/'bp_retained_line_store.sv'),extracted_epoch_reference=bind(SRC/'epoch_reference.sv'),source_diff=bind(SRC/'candidate.diff'),
 source_proof=dict(non_epoch_RTL_byte_identical=True,I_small_disabled_fallback_sequential_byte_identical=True,reference_only_module_rename=True),
 corrected_session=bind(root/'session.json'),models=session['executables'],normal_runs=[dict(case=r['case'],mode=r['mode'],log=r['log'],fst=r['fst']) for r in normal],negative=negative,negative_witness=bind(witness_path),
 superseded_first_attempt=dict(session=bind(HERE/'session.json'),corner=bind(HERE/'single-set-disabled-I/manifest.json'),reason='First wrapper overwrote all-cell mismatch with active protocol assignment. Existing cycle/512b/RAM-port tests passed, but all-cell claim superseded. Original artifacts retained unchanged; corrected OR gates use fresh models/FSTs.'),
 artifact_bytes=guard(),cap_bytes=64*1024**2,reserve_bytes=3*1024**3,scope='Component functional proof only. No production edits, whole-core/FPGA/synthesis execution, LUTRAM inference or saving/fit claim. Paired inference requires root admission; standalone result may not explain full-backend context.')
(HERE/'handoff.json').write_text(json.dumps(output,indent=2)+'\n');print(bind(HERE/'handoff.json'));print('artifactbytes',guard())
