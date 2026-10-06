This analysis compares two cache-resume architectures using the accepted physical cold-resume and replay measurements. It estimates the concurrency required for background replay and the cache capacity consumed by retaining state for two resident contexts. It is an accounting model, not an implemented replay engine or cache partition.

# Background replay versus resident cache retention

## Result

| Lines retained or replayed per context in each I/D cache | Combined I+D bytes | Serial combined replay | Linux resume slack | Replay rate needed | Two-context retained ways per cache | Ways left shared |
|---:|---:|---:|---:|---:|---:|---:|
| 128 | 16 KiB | 11,278 cycles | 11,350 cycles | 0.99x serial / 26.0 MB/s | 4 of 8 | 4 |
| 160 | 20 KiB | 14,057 cycles | 11,351 cycles | 1.24x serial / 32.5 MB/s | 5 of 8 | 3 |
| 192 | 24 KiB | 16,956 cycles | 11,431 cycles | 1.48x serial / 38.7 MB/s | 6 of 8 | 2 |

The middle 160-line point needs only 1.24x the measured serial software replay rate to finish combined instruction and data replay inside the existing Linux resume interval. A ten-request engine should have enough request-level concurrency in principle; cache installation bandwidth, interference with scheduler traffic, and useful-before-demand timing remain unmeasured.

Retention has the opposite tradeoff. The 32-KiB, 64-set, eight-way caches need 2, 2.5, or 3 ways per resident context for 128, 160, or 192 lines. Two resident contexts can therefore retain the measured range while leaving four, three, or two ways shared. Ten simultaneous retained contexts cannot fit. The 160-line point requires a skewed or set-selective allocation because a uniform partition cannot assign half a way.

A 32-bit line-address/history entry costs 1.0, 1.25, or 1.5 KiB per context for combined I+D histories. Across ten logical contexts, the raw minimum is about five, six, or seven BRAM18 blocks before banking, generation tags, confidence, and ports. Raw storage capacity is not the main obstacle; replay installation and cache-capacity policy are.

## Architectural conclusion

Use a hybrid design:

- Retain or partition selected cache state for the two resident contexts so a 5–11-cycle hardware handoff can begin hot immediately.
- Use background replay for nonresident contexts or ordinary Linux scheduling, where roughly 11.35k cycles of resume work provide enough lead.
- Keep the two-entry previous-first signature as a small first-touch complement and confidence probe, not as the main cold-state mechanism.

This matches the measured timing. Hundreds of lines cannot be restored during a five-cycle handoff, while the same replay volume plausibly fits under Linux scheduling with only a modest throughput increase over serial software replay.

## Reproduction and limits

Run `python3 logs/cache-resume-replay-vs-retention-20261006/model.py`. It reads the accepted replay-cost and scheduler result JSON files, writes `results.json`, and records their hashes. Script SHA-256 is `a01756fb90113bd00e6d9cfa08cff960a5202ed5d2e0ec8f9ceddf4d46321e1a`; result SHA-256 is `1502dd046a55af8e619c9a6f31396d1f74ef4165b6957fcd70be27e23b2e7afd`.

The model does not measure concurrent replay, cache pollution, or retention behavior. Refill-equivalent counts are sizing guides rather than exact unique histories, and the storage estimate omits implementation overhead.
