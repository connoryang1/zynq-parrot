This directory records the repaired standalone UCE prefetch gate used as a baseline for target-data preview work. The gate exercises the current 16-byte detached hint protocol and its interaction with ordinary demand traffic; it does not validate a Linux scheduler hint or an independent pre-acceptance lane.

# UCE prefetch harness baseline

- Branch: `experiment/target-data-preview-lane`; BlackParrot gitlink: `474dbb8ac850f7e4558e3ebd9983f681c979bf98`.
- Clean invocation: `python3 testing/rtl/run_uce_prefetch.py --out /tmp/zp-uce-prefetch-corrected-20261024-accepted --verilator /home/coyang/zynq-parrot/install/bin/verilator`.
- Result: functional test PASS, malformed-address reply rejected by the exact UCE assertion, `verification.json` reports `passed: true`. Full FST, executable, and build log remain in the named local output directory; their hashes are in `verification.json`.
- The old driver expected a 64-byte, four-beat hint refill and L1 writes. Current UCE sends an aligned 16-byte, one-beat hint and writes the D-cache side buffer. The corrected driver checks its distinct opcode and payload.
- The old ten-hint sequence placed all requests in one four-set cache index. UCE permits only eight live victim-way reservations per set; the ninth was safely dropped, leaving apparent room for an eleventh table request. Spacing by `0x1040` rotates cache sets while retaining distinct addresses, and the gate now proves all ten table slots live before checking full-table backpressure.
- The runner initially failed before compilation because this worktree has no `install/bin/verilator`. After an explicit canonical tool path was supplied, the functional and negative gates passed but provenance writing failed on that tool's external dependency path; it now records absolute paths for dependencies outside the worktree. A final fresh run wrote complete verification metadata.

These were harness and provenance mismatches, not evidence of a UCE RTL regression. This baseline must remain separate from any later queue or arbiter RTL claim.
