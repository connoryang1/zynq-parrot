This prepares ROOT-only formal freeze of the stopped R8 WORK and evidence families after the complete independent archive verification. The gate creates new external receipts and never edits old source, caps, files or budgets. Preparation does not execute the gate, archive, model, reader, compiler, vendor tool or reservation release.

`freeze.py` requires exact capture `f2d11985...079b`, ROOT independent verification `6a1dbfe2...c7b0`, and terminal `b67c89c0...c84`. ROOT has already checked every actual tar member/source and all three DCP original/copy pairs; this gate does not repeat decompression. It verifies exact4521/1148/190 memberlists with no invented internalmanifest, preserves the prior verifier-precondition failure, then hashes the entire WORK and evidence families twice. All regular files and exact symlink definitions are recorded, and all actual archive/DCP hashes must still match. Current vendor absence and original terminal ownership remain mandatory.

The output paths are `/home/coyang/fpga-artifacts/context-resume/reservation-closures-20261122/r8-work.json`, `r8-evidence.json`, and `r8-freeze-complete.json`. The complete marker is written LAST and binds both exact receipt hashes and a common `freeze_pair_id`; consumers MUST require all three, matching IDs and hashes. Partial receipt pairs release nothing. Old caps remain2.5GiB WORK and384MiB evidence. Each receipt records logical and allocated footprints, charges their maximum conservatively, and releases only cap-minus-charged unused future allocation. Actual occupied data remains on disk. Future writes require new admission.

The work receipt roots the stopped `/run/user/1001/zp-linux-borrow1792-trace0-cad-20261122-01`. Evidence is the original union of `/home/coyang/fpga-logs-linux-retained-borrow1792-trace0` and `/home/coyang/zynq-parrot-linux-host-observer/research/borrow-fpga-cad-preparation-20261122`. Receipts are external to both families to avoid self-referential inventories. The fixed receipt-only allowance is8MiB with600s maximum; before and throughout sealing, the old native/CAD/source reservations remain fully charged through the unchanged original guard plus this receipt allowance. This is not an actual new-CAD admission.

ROOT-only command after source/hash review:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 freeze.py --admission-sha256 <admission.json-SHA256> --execute
```

The evidence receipt deliberately measures the FINAL closed directory rather than trusting the capture manifest's pre-final-write footprint. Old monitor/source/budget failures remain preserved. No fit, routed checkpoint, bitstream, maximum capacity or application claim follows from these operational receipts.
