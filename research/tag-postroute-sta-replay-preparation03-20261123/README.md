This fresh03 source fixes only the generated-clock Tcl syntax required by Vivado2024.2. It adds -add to the existing explicit-master create_generated_clock command. All actual02 evidence, source, DCP and BIT remain unchanged.

02 passed actual42sink/root/serializer positive polarity using explicit C-pin IS_INVERTED0 and reported final51,305LUT/47,327logic/3,978memory/26,946FF. It stopped at ERROR12-672: Cannot specify -master_clock without -add; no clock was created or STA result accepted. Source-end/group release remains preserved in the bound actual02 session.

Only replay.tcl change versus02 is -add. The same explicit20MHz source/master,50ns conservative envelope, initial exact42/76/5clock gates, positive polarity and after exactly-one-new-clock/original-constraints gates remain. -add is required syntax, not permission to keep unreviewed extra clocks. Same exact final60910DCP/BITd302, all reports and utilization captured, no hold exception/clock relaxation/implementation command.

Fresh RUN...-03 and v3schemas; unchanged300tool/330owner/64MiBRUN/8MiBreports/8MiBHOME/96KiBsource/AS8GiB/allfloors. Draft OTHER unchangedRUN301989888/HOME267995484/SHM335544320. ROOT must fill new FINAL/release/selection/routed-binding and actualpreflight; no runtime admitted by this source.
```
/usr/bin/python3 run_sta.py --execute --admission-sha256 EXACT_FINAL_SHA
```
