# Full-line installer timing audit

This audit measures `prefetch_install_state_r` directly in four retained,
accepted RTL waveforms. Run the two analyzers under
`logs/banked-full-line-timing-20261006/` first, then run `python3 analyze.py`
to regenerate `results.json`.

| Implementation | Installs | Min | Median | Mean | Max |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct response installer | 40 | 17 | 17 | 17.00 | 17 |
| Concurrent response-buffer installer | 33 | 16 | 19 | 18.70 | 21 |
| Banked, 32-bit minimal wrapper | 33 | 16 | 19 | 18.70 | 21 |
| Banked, 64-bit full wrapper | 33 | 16 | 19 | 19.61 | 25 |

The direct path reproduces the prior 17-cycle audit exactly for all 40 lines.
The concurrent path, which permits later requests to issue while a prior line
installs, has distribution `16:1, 17:3, 18:3, 19:25, 21:1`. Reconstructing the
committed banked implementation in the 32-bit minimal wrapper produces the
same distribution exactly and an 802-cycle complete run. The 64-bit
FPGA-facing wrapper takes 805 cycles, with a 19-cycle median and 25-cycle
maximum. Its wider transport therefore does not shorten installation. The
historical 771-cycle banked result is not reproducible from the committed
state; the exact ten-slot reconstruction is 31 cycles slower, and the
four-slot control takes 2,241 cycles.

This changes the replay feasibility interpretation. With a conditional
41-cycle first-response-beat input, eight response beats, and 304 data lines:

- 17 cycles/line completes at 5,217 cycles, leaving 334 cycles in the 5,551
  cycle hot-resume window;
- 19 cycles/line completes at 5,825 cycles, missing by 274 cycles;
- 21 cycles/line completes at 6,433 cycles, missing by 882 cycles.

Thus four transport slots are sufficient only if the eventual concurrent
installer sustains at most 18 cycles per line for this strict 479-line target.
The current evidence proves 17 cycles for the serialized direct path, while
both banked traces miss that sustained-rate requirement. No instruction-cache
installer exists yet.
