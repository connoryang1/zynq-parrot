# Banked full-line pipeline reconstruction

This artifact reconstructs the committed banked full-line prefetch path at top
commit `03955af9`, BlackParrot commit `259b8858`, and subsystem commit
`f9762c5b`. The benchmark uses three resident threads, ten logical contexts,
ten prefetch slots, 33 dependent nodes, and the pipelined synthetic memory
model with a nominal 40-cycle address-to-first-beat delay.

Two wrappers were measured with the same ELF and guest configuration:

| Wrapper | HP0 width | Beats/line | Cycles | Installer median | Installer max |
| --- | ---: | ---: | ---: | ---: | ---: |
| `black-parrot-minimal-example` | 32 bits | 16 | 802 | 19 | 21 |
| `black-parrot-example` | 64 bits | 8 | 805 | 19 | 25 |

The 64-bit waveform accounts for 33 accepted hints, 33 issued requests, 33
AXI bursts, 264 response beats, and 33 unique tag publications. Address to
first response beat is 40 cycles for 32 of 33 requests and 47 cycles for one;
each burst then takes exactly seven cycles from first to final beat. Allocation
to tag publication has an 84-cycle median and 118-cycle maximum. One install
held an accepted tag-write handshake for two cycles, so the trace contains 34
raw tag-write handshakes but 33 unique publications. The repeated write is
idempotent in this passing workload, but it is a real contention symptom and
should not be counted as another completed line.

The near-identical 802/805 totals show that this workload is not limited by
the external beat width. Cutting each line from sixteen beats to eight saves
transport time, but cache installation and request scheduling overlap that
transport and remain on the critical path. The banked storage also does not
shorten the installer state sequence: its 32-bit distribution is exactly the
same as the earlier concurrent flat-buffer trace. The previously recorded
771-cycle result and claim that four slots preserve throughput do not reproduce:
ten slots take 802 cycles in the minimal wrapper, while four slots take 2,241.

Run `python3 analyze.py` to regenerate the minimal-wrapper `results.json`, and
`python3 analyze_main64.py` to regenerate `results-main64.json`. The retained
filtered VCDs contain only the request, response, publication, commit, and
clock signals used by the analyzers. Both traces use synthetic memory rather
than physical DDR. The 64-bit run printed guest and host pass markers before a
pre-existing Verilator DPI finalization assertion made the process exit
nonzero; the measured guest result and waveform precede that assertion.
