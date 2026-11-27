#!/bin/bash
# Block until every given <prefix>.done exists, then print them (one notification).
cd "$(dirname "$0")/.."
for p in "$@"; do until [ -f $p.done ]; do sleep 20; done; done
for p in "$@"; do cat $p.done; done
