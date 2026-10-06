# Cache-miss recorder routed BRAM correction

The first routed recorder build exposed a synthesis-shape bug: the two
256x64 histories fed one ternary registered read, so Vivado rejected their
`ram_style="block"` attributes and implemented them as 168 additional
`RAM64M` primitives. Splitting the registered I- and D-history outputs lets
Vivado infer one simple dual-port `RAMB36` for each history while preserving
the CSR protocol and simultaneous I/D writes.

Both builds use the default `e_bp_unicore_zynqparrot_cfg`, 20 MHz ACLK, eight
Vivado workers, and identical dependencies apart from the single BlackParrot
fix. The source routed summaries are:

- before: `logs/fpga/20261006T173322Z-6da84fc6/`
- after: `logs/fpga/20261006T182248Z-e860ceea/`

Run `./compare.py > results.json` from this directory to reproduce the table.

| Routed metric | LUT-RAM build | BRAM build | Change |
|---|---:|---:|---:|
| Slice LUTs | 50,941 (95.75%) | 50,154 (94.27%) | -787 (-1.48 pp) |
| Slice registers | 21,640 | 21,577 | -63 |
| BRAM tiles | 80 | 82 | +2 |
| WNS | +1.777 ns | +3.390 ns | +1.613 ns |
| WHS | +0.035 ns | +0.023 ns | -0.012 ns |

Both builds have zero setup/hold failing endpoints and generated complete
bitstreams. The corrected build passes the directed trace test with the same
two instruction misses, one data miss, and `0x623be`/`0x623fd` timestamps as
before, plus the disarmed context-switch smoke test and all 15 harness checks.

This corrects the earlier sizing assumption that both histories together
would consume one BRAM tile. A 256x64 history requires one `RAMB36`, so the
pair consumes two of the Zynq-7020's 140 tiles.
