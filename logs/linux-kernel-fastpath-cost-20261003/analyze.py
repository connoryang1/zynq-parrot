#!/usr/bin/env python3
import json,re
from pathlib import Path
rows={}
for line in (Path(__file__).parent/'result.log').read_text().splitlines():
 m=re.match(r'RESULT path=(\S+) metric=(\S+).*median_x2=(\d+)',line)
 if m: rows.setdefault(m.group(1),{})[m.group(2)]=int(m.group(3))/2
base=rows['empty']
for name,row in rows.items():
 row['net_cycles']=row['cycles']-base['cycles']
 row['net_instructions']=row['instructions']-base['instructions']
 if name!='empty':
  row['ratio_vs_ready_resident_11_12']=row['net_cycles']/11.12
  row['ratio_vs_ready_nonresident_15_13']=row['net_cycles']/15.13
out={'samples':512,'warmups':64,'measurement_envelope':base,'paths':rows}
(Path(__file__).parent/'analysis.json').write_text(json.dumps(out,indent=2)+'\n')
