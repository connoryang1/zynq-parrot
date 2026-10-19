This directory records the exact physical acceptance ladder for the pending first-target context-switch interlock. It uses a fresh overlay for every run and retains hash-pinned raw guest transcripts so host cleanup cannot mask a guest failure.

# Pending interlock physical acceptance

Acceptance requires the formerly failing exact ten-stream image to reach its workload marker and `CORE PASS` twice, followed by the exact two-stream control reaching the same markers with its measured cycle count.

All three runs passed their workload marker, guest `CORE PASS`, and host `BSG PASS` after a fresh overlay. The two k10 repetitions measured 72,038 and 72,042 cycles. The exact archived k2 control measured 20,547 cycles, matching the corrected traced simulation exactly and adding 1,289 cycles (6.69%) over its 19,258-cycle pre-interlock simulation baseline.

The routed source is top `9990e673b0b3ec4194eb62494f3d1bdd6b06a201` / BlackParrot `30479f1a2c5e5c88aed71f1e79c6efe26ffcec85`. Final WNS/WHS are `+0.150/+0.035 ns`; the package and bitstream SHA-256 values are `b6b04c3b...9aba` and `347d3281...2e3a`. `results.tsv` is derived fail-closed from the raw transcripts and `identities.txt` retains the full hashes.

The managed shell intermittently denied new SSH sockets after staging. Each accepted run therefore used the reviewed overlay helper with a temporary, narrowly hash-pinned post-load hook so overlay loading and the already-reviewed serialized runner stayed in one admitted board session. The helper was restored byte-for-byte afterward to SHA-256 `0d3736302864de21500639bb0fb5f49224df955746825aed6e61d469ad69594a`; no project result depends on the temporary hook remaining installed.
