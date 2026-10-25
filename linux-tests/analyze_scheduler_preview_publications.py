#!/usr/bin/env python3
"""Attribute Linux preview publications to physical target segments and misses."""

import argparse
import json
import re
from pathlib import Path

from analyze_scheduler_preview_events import analyze as analyze_events
from analyze_scheduler_preview_four import RECORD_PATTERN, target_index


PUBLICATIONS = re.compile(
    r"^SCHED_PREVIEW_PUBLICATIONS mode=(\d+) trial=(\d+) count=(\d+) "
    r"overflow=(\d+) records=([0-9a-f]{16}(?:,[0-9a-f]{16}){7})$"
)


def analyze(path: Path) -> dict:
    delivery = analyze_events(path)["trials"]
    publications = {}
    misses = {}
    for line in path.read_text(errors="replace").splitlines():
        match = PUBLICATIONS.fullmatch(line.strip())
        if match:
            mode, trial, count, overflow = map(int, match.groups()[:4])
            if trial in publications:
                raise ValueError(f"duplicate publication trial {trial}")
            if not 1 <= trial <= 48 or mode != delivery[trial]["mode"]:
                raise ValueError(f"wrong publication mode/trial {mode}/{trial}")
            if count > 8 or overflow:
                raise ValueError(f"publication overflow in trial {trial}")
            words = [int(word, 16) for word in match.group(5).split(",")]
            if any(words[count:]):
                raise ValueError(f"nonzero unused publication records in trial {trial}")
            if any((word >> 30) & 3 != 3 for word in words[:count]):
                raise ValueError(f"invalid publication record kind in trial {trial}")
            addresses = [((word & ((1 << 30) - 1)) << 4) for word in words[:count]]
            cycles = [word >> 32 for word in words[:count]]
            if cycles != sorted(cycles):
                raise ValueError(f"unordered publication cycles in trial {trial}")
            snapshots = delivery[trial]["snapshots"]
            if count != snapshots["load"][3] or snapshots["entry"][3] > count:
                raise ValueError(f"publication count disagrees with stages in trial {trial}")
            publications[trial] = dict(mode=mode, addresses=addresses, cycles=cycles,
                                       entry_count=snapshots["entry"][3])
            continue
        match = RECORD_PATTERN.fullmatch(line.strip())
        if match:
            mode, trial, lane, index, cycle, paddr, msg = match.groups()
            mode, trial, lane = int(mode), int(trial), int(lane)
            if not 1 <= trial <= 48 or not 0 <= lane < 4 or mode != delivery[trial]["mode"]:
                raise ValueError(f"wrong miss record mode/trial/lane {mode}/{trial}/{lane}")
            misses.setdefault((trial, lane), []).append(int(paddr, 16))
    if sorted(publications) != list(range(1, 49)):
        raise ValueError(f"expected 48 publication rows, found {len(publications)}")

    # The matched off control uniquely identifies the physical target page.
    bases = set()
    for trial in range(1, 49):
        if delivery[trial]["mode"] == 0:
            for lane in range(4):
                addresses = misses.get((trial, lane), [])
                if len(addresses) != 1:
                    raise ValueError(f"off control trial {trial} lane {lane} lacks one miss")
                bases.add(addresses[0] - 64 * target_index(trial, lane))
    if len(bases) != 1:
        raise ValueError(f"off controls imply {len(bases)} target physical bases")
    target_base = bases.pop()

    exact = {}
    for trial, row in publications.items():
        if row["mode"] != 1:
            continue
        expected = [target_base + 64 * target_index(trial, lane) for lane in range(4)]
        early = row["addresses"][:row["entry_count"]]
        target_published = [lane for lane, address in enumerate(expected)
                            if address in row["addresses"]]
        target_early = [lane for lane, address in enumerate(expected) if address in early]
        target_missed = [lane for lane, address in enumerate(expected)
                         if address in misses.get((trial, lane), [])]
        exact[trial] = dict(publications=[f"0x{x:x}" for x in row["addresses"]],
                            target_published_lanes=target_published,
                            target_published_by_entry_lanes=target_early,
                            target_missed_lanes=target_missed,
                            published_by_entry_but_missed_lanes=sorted(
                                set(target_early) & set(target_missed)))
    return dict(source=str(path), target_physical_base=f"0x{target_base:x}",
                exact_trials=exact,
                exact_published_by_entry_but_missed_trials=[
                    trial for trial, row in exact.items()
                    if row["published_by_entry_but_missed_lanes"]])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(analyze(args.transcript), indent=2, sort_keys=True))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
