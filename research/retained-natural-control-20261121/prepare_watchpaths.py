#!/usr/bin/env python3
"""Bind telemetry names/widths from the already CLOSED1280 advisory FST."""
import json
from pathlib import Path
import subprocess
from prepare import bind,ROOT,HERE


def main():
 closed=ROOT/'research/retained-system-geometry-20261121/full-system1280-cold08-native0-01/session.json';m=json.loads(closed.read_text());reader=ROOT/'research/retained-system-geometry-20261121/reader/fst_events'
 if bind(m['trace']['path'])!=m['trace']:raise ValueError('changed closed trace')
 r=subprocess.run([str(reader),m['trace']['path'],'--list'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=60)
 if r.returncode or not r.stdout.rstrip().endswith('#END'):raise ValueError('closed hierarchy list failed')
 variables={f[3]:(int(f[1]),int(f[2])) for line in r.stdout.splitlines() if line.startswith('#VAR') for f in [line.split('\t')]}
 core='TOP.bsg_nonsynth_zynq_testbench.dut.top_fpga_inst.blackparrot.processor.u.unicore.unicore_lite';store=core+'.retained_store.storage';be=core+'.core_minimal.be';want={}
 for n in ['clk_i','reset_i','clear_i','invalidate_v_i','lookup_v_i','lookup_ready_o','resp_v_o','resp_ready_i','resp_hit_o','insert_v_i','insert_ready_o','insert_replace_i','insert_cancel_i','insert_done_o','insert_published_o','busy_o','epoch_wrap_o']:
  want['store_'+n]=store+'.'+n
 for stem in ['invalidate_addr_i','lookup_addr_i','insert_addr_i']:
  for lane in range(2):want[f'store_{stem}_{lane}']=store+'.'+stem+f'[{lane}]'
 for n in ['retained_control_cmd_v','retained_control_cmd','retained_control_r','retained_maintenance','dcache_retained_mutation_v','dcache_retained_mutation_paddr','retained_uce_idle','retained_status']:want[n]=core+'.'+n
 want.update({'be_clock':be+'.clk_i','be_reset':be+'.reset_i','global_cycle':be+'.calculator.pipe_sys.csr.global_cycle_r','retire_slot':be+'.retire_thread_id_lo','context0':be+'.physical_thread_context_id_r[0]','context1':be+'.physical_thread_context_id_r[1]','instret':be+'.calculator.commit_pkt_cast_o.instret','pc':be+'.calculator.commit_pkt_cast_o.pc'})
 if any(p not in variables for p in want.values()):raise ValueError('missing actual telemetry port')
 rows={k:dict(path=p,width=variables[p][0]) for k,p in want.items()};selection=HERE/'retention-selection.tsv';selection.write_text(''.join(k+'\t'+v['path']+'\n' for k,v in rows.items()))
 record=dict(state='PREPARED-watchpaths-exist-in-closed-model-no-new-execution',source_session=bind(closed),trace=m['trace'],reader=bind(reader),preparer=bind(__file__),selection=bind(selection),fields=rows,
 semantics='Sample each packed lane BEFORE its own clk_i rising edge; count accepted lookups/responses/inserts/terminals/publications, same-set mutation invalidations, clear-active cycles and wrap pulses inside actual retired-PC/CSR-defined WHOLE and timed-ring windows. Track owners across boundaries. Hits require resp_v AND ready AND hit. Control command/status main-clock sampling is distinct from D negedge lane. This is only a prepared schema; no natural-run analyzer validation or accepted coverage yet. Merge with full ordinary D-cache/tag/reference ledger; side-store events alone cannot reconstruct capacity.')
 (HERE/'retention-selection.json').write_text(json.dumps(record,indent=2)+'\n');print('Prepared',len(rows),'actual telemetry paths; no target/model execution')

if __name__=='__main__':main()
