# Shared-path bound for instruction and data resume replay

This is an aggregate feasibility bound built from accepted physical measurements and RTL topology. It does not claim an implemented instruction replay engine.

The physical Linux sweeps make the 32 KiB instruction penalty equivalent to 174.47 serialized cold-line increments and the 128 KiB clean-data penalty equivalent to 143.17. Rounding both upward gives 175 instruction lines and 144 kernel data lines. Adding the measured 160-line application point gives a deliberately strict target of **479 lines before first user dispatch**.

The serialized direct full-line data installer takes exactly 17 cycles per line
in its retained trace. The concurrent response-buffer path instead measures a
19-cycle median and 21-cycle maximum. The reconstructed banked path measures
the same 19-cycle median and 21-cycle maximum in the minimal wrapper; the
64-bit FPGA-facing wrapper measures a 19-cycle median and 25-cycle maximum.
The I-cache and D-cache have separate
UCEs, tag/data arrays, and install ports, so an eventual I-cache replay path can
in principle install in parallel with the D-cache. Both paths ultimately share
one 64-bit AXI read-data channel. Each 64-byte line consumes eight data beats,
and ordinary cache demand has priority over detached prefetch at AXI address
arbitration.

Under a conditional 41-cycle request-to-first-response-beat assumption and four outstanding slots, the finite-window AXI lower bound is 4,948.5 cycles. Separate cache installation is slightly slower: the larger D stream has 304 lines, so `41 + 8 + 304*17 = 5,217` cycles. This fits inside the measured 5,551-cycle hot combined Linux resume by **334 cycles**. It implies roughly 106 MB/s for the complete 30.7 KiB replay, versus 99.4 MB/s required and a 144 MB/s raw 64-bit/18 MHz AXI beat rate.

The conditional endpoint matters. The physical 41-cycle measurement is an
ordinary critical load-to-use interval, not detached 64-byte
request-to-first-beat latency. It does not physically validate this scenario;
the model instead states what would be feasible if the full-line path meets
that input.

The slot sensitivity matters:

| Outstanding slots | 41-cycle aggregate bound | Fits 5,551 cycles? |
|---:|---:|:---:|
| 1 | 19,647 cycles | No |
| 2 | 9,848 cycles | No |
| 3 | 6,581.7 cycles | No |
| 4 | 5,217 cycles | Yes |
| 5 | 5,217 cycles | Yes |
| 10 | 5,217 cycles | Yes |

Four slots are therefore the first feasible point only in the conditional
serialized 17-cycle installer row. The exact banked reconstruction contradicts
the earlier claim that reducing the buffer from ten slots to four preserves
performance: ten slots take 802 cycles and four slots take 2,241 cycles in the
same 33-node workload.

Installer rate is an equally strict condition. The 17-cycle row comes from
the direct installer. The concurrent response-buffer waveform measures a
19-cycle median and 21-cycle maximum; those rates produce 5,825 and 6,433
cycle bounds and miss the deadline by 274 and 882 cycles. The FPGA-facing
banked maximum of 25 cycles raises the bound to 7,649 cycles, missing by 2,098.
The 479-line target allows at most 18 cycles per line under the conditional
41-cycle response input. No measured concurrent implementation meets that
strict whole-footprint rate.

The more important architectural result is that **separate I-cache and D-cache installation is necessary**. If all 479 lines shared one 17-cycle installer, completion would take 8,192 cycles even before realistic interference, missing the hot-resume deadline. Separate installers reduce that conditional bound to 5,217 cycles, with the D-cache side becoming the limiter.

This is a narrow feasibility result. It does not establish useful-before-demand coverage. The 175/144 values are latency equivalents rather than exact line identities, an I-cache replay injector is still absent, and real scheduler demand has priority. The next measurement should focus on address order and trigger time: replay must begin early enough that the first kernel return-path lines arrive before their demands, while later application lines can use the remaining window.

Reproduce with:

```sh
python3 logs/cache-resume-shared-path-bound-20261006/model.py
```
