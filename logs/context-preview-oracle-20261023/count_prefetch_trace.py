#!/usr/bin/env python3
"""Count key prefetch signal edges from a VCD stream without storing VCD."""

import collections
import sys

scopes = []
signals = collections.defaultdict(list)
in_header = True
for line in sys.stdin:
    if in_header:
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "$scope":
            scopes.append(fields[2])
        elif fields[0] == "$upscope":
            scopes.pop()
        elif fields[0] == "$var":
            _, kind, width, ident, name, *_ = fields
            if (name in {"prefetch_issue", "prefetch_accept", "prefetch_response",
                         "prefetch_buffer_hit_tv"}
                    or "prefetch_hit" in name):
                signals[ident].append(".".join(scopes + [name]))
        elif fields[0] == "$enddefinitions":
            in_header = False
            counts = collections.Counter()
            prev = {}
        continue
    if line and line[0] in "01" and line[1:].strip() in signals:
        ident = line[1:].strip()
        value = line[0]
        if value == "1" and prev.get(ident) != "1":
            counts[ident] += 1
        prev[ident] = value

for ident, names in signals.items():
    if counts[ident]:
        print(counts[ident], ident, " | ".join(names[:3]))
