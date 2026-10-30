This directory records the exact-image Linux instruction-miss traces used to retrain the shared I-cache replay table. It keeps the physical inputs, deterministic model, checks, and generated results together so later firmware builds can be tied to measured addresses rather than an older kernel layout.

# Exact-image replay model

All three inputs were captured on independent fresh FPGA boots with replay disabled and completed without recorder overflow. The training/full trace contains 81 instruction records; the measured handoff windows contain 102 source-to-peer and 55 peer-to-source instruction records. Their compressed source hashes are recorded in `results.json`.

The two measured windows contain 157 instruction-demand records, 153 in privileged code. The fixed shared policy selects 63 physical cache lines, with no more than eight lines in any I-cache set. Under the model's primary timing assumptions it makes 50/157 demand records ready before demand (31.8%) and gives a proportional—not measured—upper bound of 2,104.8 cycles from the separately measured 6,609-cycle cold-instruction penalty.

`model.py` regenerates `results.json`; `test_model.py` checks the input identities, table legality, and principal results. The emitted firmware table is `linux-tests/opensbi-platform/blackparrot/icache_prefix.h`.
