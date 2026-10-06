This analysis models the data-cache capacity cost of protecting ways for two resident contexts using the retained scan, trie, and pointer-compute traces. It warms a 64-set, eight-way LRU model with one complete trace pass and reports a second pass. It is a policy model, not implemented cache-partition RTL.

# Resident cache-retention trace model

## Policy

Contexts 1 and 2 own one, two, or three protected ways in every set. They fill an empty protected way first and may use shared ways for overflow. Context 0 uses only the remaining six, four, or two shared ways. Lines can still be hit regardless of which class currently holds them.

## Result

| Trace | Protected ways per resident | Shared-context misses, baseline → protected | Shared-context miss rate | Resident misses |
|---|---:|---:|---:|---:|
| Scan | 1 | 0 → 0 | 0% | 0 |
| Scan | 2 | 0 → 0 | 0% | 0 |
| Scan | 3 | 0 → 340 | 0.621% | 0 |
| Trie | 1 | 0 → 0 | 0% | 0 |
| Trie | 2 | 0 → 3 | 0.006% | 0 |
| Trie | 3 | 0 → 74 | 0.152% | 0 |
| Pointer + compute | 1 | 907 → 1,127 | 4.002% → 4.972% | 0 |
| Pointer + compute | 2 | 907 → 1,163 | 4.002% → 5.131% | 0 |
| Pointer + compute | 3 | 907 → 1,163 | 4.002% → 5.131% | 0 |

At the measured 39-cycle cold-data increment, the pointer trace's additional 256 misses under two-way protection correspond to about 9,984 cycles across 22,666 context-0 accesses, or 0.44 cycles per access. The relative miss-count increase is 28.2%, but the absolute miss-rate increase is 1.13 percentage points.

The workers have zero modeled misses in every policy because these retained traces are warm and their data survives ordinary sharing. That makes them a no-benefit capacity control: retention only helps when another footprint would otherwise displace resident state.

## Decision

Two protected ways per resident context are the safer first point. They cover 128 lines/context in a 64-set cache, match the lower physical replay sizing point, and leave four of eight ways shared. Three ways cover 192 lines but cause visible capacity loss even in scan/trie and leave only two shared ways.

The pointer trace warns that static protection can penalize a cache-sensitive unprotected context even at one or two ways. A practical policy should disable protection for inactive contexts, release low-confidence lines, or allow controlled stealing under shared pressure rather than permanently reserving ways.

## Reproduction and limits

Run `python3 logs/cache-retention-trace-model-20261006/model.py`. Script SHA-256 is `4fe8c28014f1fc544c24956d49a3b09dcbe616c3d867dcd76efa23b0979ea5b9`; result SHA-256 is `46ea132c361be76315580660e700f160fc24d9bea1461e0f36a298a6253bf355`.

The model includes data accesses only, approximates replacement with LRU, and repeats a captured trace to remove cold initialization. It does not model instruction-cache pressure, dirty victims, refill timing, or the exact BlackParrot replacement machinery.
