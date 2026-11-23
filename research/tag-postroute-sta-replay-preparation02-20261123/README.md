This fresh source-only02 fixes only the mapped-polarity API and captures its raw evidence before proceeding with the same STA replay. Failed01 and all original files stay unchanged. The exact96KiB finalphysicalDCP/BIT, clock model, reports and runtime caps are retained; execution/funding still require a new ROOT authority.

01 actual toolRC1/outer1 stopped before clock addition after exact42/76 precheck. First FDRE cell IS_C_INVERTED was an empty value, not binary0; the harness correctly stopped instead of assuming polarity. DCP/source-endPASS, ownedgroupRELEASED/globalvendor[]. It is not a timing or fit failure.

Correct API: AMD UG9122024.2 PIN page documents Boolean IS_INVERTED on mapped PIN objects, including C. Installed exact2024.2 FDRE.v/FDSE.v lines34 and87–96 set default IS_C_INVERTED=0 and choose posedge C. The new script first executes raw report_property -all for all42cells+C pins plus root and serializer cells+C pins, and preserves every literal property in raw-cell-pin-properties.tsv. Effective edge uses that positive primitive default and EXPLICIT C-pin IS_INVERTED override; empty/ABSENT/unknown pin values STOP. Optional nonempty cell parameter must agree, not be XORed/double-counted. Empty CELL.IS_C_INVERTED is never converted into false.

Primary documentation: https://docs.amd.com/r/2024.2-English/ug912-vivado-properties/PIN (PIN table IS_INVERTED; report_property -all). Exact installed library paths/hashes are plan inputs; no vendor bodies copied. Flat report_utilization is saved immediately on the exact finalDCP, before polarity checks; no hierarchical report or checkpoint copy. Same source-derived conservative50ns clock, source-on-fall hold diagnostics, unchanged existing constraints/exceptions, no synth/place/route/bitgen or hold relaxation. All failing reports preserved; qualified remainsfalse pending ROOTreview.

New prospective source96KiB (old64KiB unchanged), within the explicitly priced1MiB source reservation; other caps unchanged300tool/330owner/64MiBRUN/8MiBreports/8MiBHOME/AS8GiB. ROOT-requested OTHER_HOME sum183060828+1048576+16777216+67108864=267995484B; OTHER_RUN301989888/SHM335544320 unchanged. These are draft prices, not an actual free-space result/release.

ROOT fills fresh02 admission.FINAL.json/release and the same finalphysical routed binding; expected96selection is recorded separately below for exact review, never an initialroute substitution. New RUN...-02 only.
```
/usr/bin/python3 run_sta.py --execute --admission-sha256 EXACT_FINAL_SHA
```

Source-only syntax checked; no tool/runtime launched by the preparer.
