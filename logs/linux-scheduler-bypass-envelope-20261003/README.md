# Linux scheduling bypass envelope

This analysis combines three accepted measurements from the same qualified
FPGA platform: the hot Linux scheduler decomposition, dynamic user context
dispatch, and correctness-checked ready-context selectors. It is a derived
model rather than a new physical run. Run `python3 -B analyze.py` from this
directory to regenerate `analysis.json` and `analysis.stdout`.

The mean of the two measured Linux same-address-space handoff medians is
5,545.5 cycles. Its measured decomposition is:

| Component | Cycles | Share |
| --- | ---: | ---: |
| Physical counter pair | 1 | 0.02% |
| Minimal syscall beyond the counter | 622 | 11.22% |
| `sched_yield` path beyond a minimal syscall | 2,734 | 49.30% |
| Alternate-task selection, switch, and return | 2,188.5 | 39.46% |

This changes the optimization target. Even an optimistic elimination of the
entire last row leaves the measured 3,357-cycle no-peer yield floor, limiting a
switch-only improvement to 1.65x. Calling a new kernel ABI on every handoff
also retains at least the measured 623-cycle minimal-syscall cost before doing
any context work. A U-mode instruction avoids both costs.

| Replacement path | Measured or modeled cycles | Linux/path ratio |
| --- | ---: | ---: |
| Optimistic kernel-only floor | 3,357 | 1.65x |
| Optimistic minimal syscall plus direct resident dispatch | 628.125 | 8.83x |
| Direct register-target, resident | 5.125 | 1,082.05x |
| Direct register-target, nonresident | 9.164 | 605.15x |
| Linux-hosted general ready-bitmap selector, resident | 17.074 | 324.79x |
| Linux-hosted general ready-bitmap selector, nonresident | 22.090 | 251.04x |
| Fair three-context round robin | 26.59 | 208.56x |

The general selector is the more realistic fast path: it atomically claims one
ready context, preserves other runnable bits, publishes the source as ready,
and dynamically dispatches the target. The FPGA benchmark validates the ready
word, spectator context, selected context, return source, and zero LR/SC
retries in each context's final measured operation. The later persistent Linux
probe supplies aggregate retry accounting. The fair result rotates among three
contexts and validates completion by all three.

The modeled end-to-end benefit depends on useful work between handoffs:

| Useful work cycles | Kernel-only | Syscall + direct | General resident | General nonresident | Fair round robin |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 1.65x | 8.83x | 324.79x | 251.04x | 208.56x |
| 100 | 1.63x | 7.75x | 48.24x | 46.26x | 44.60x |
| 500 | 1.57x | 5.36x | 11.69x | 11.58x | 11.48x |
| 1,000 | 1.50x | 4.02x | 6.44x | 6.40x | 6.38x |
| 5,000 | 1.26x | 1.87x | 2.10x | 2.10x | 2.10x |
| 10,000 | 1.16x | 1.46x | 1.55x | 1.55x | 1.55x |
| 50,000 | 1.04x | 1.10x | 1.11x | 1.11x | 1.11x |
| 100,000 | 1.02x | 1.05x | 1.06x | 1.06x | 1.06x |

With the measured 17.074-cycle hosted resident selector, the handoff mechanism alone
supports at least 2x total speedup when useful work between handoffs is below
about 5,511 cycles, 1.5x below about 11,040 cycles, and 1.1x below about 55,267
cycles. Cache prefetch can improve these totals separately by reducing cold
resume stalls; it is not included in this scheduler-only model.

The measurements support a two-level implementation: Linux allocates and
accounts for a protected context group at coarse time-slice boundaries, while
the running group uses the U-mode selector for ordinary ready-to-ready
handoffs. Linux still handles the slow cases: no ready context, page faults,
blocking I/O, signals, migration, and preemption of the entire group.
