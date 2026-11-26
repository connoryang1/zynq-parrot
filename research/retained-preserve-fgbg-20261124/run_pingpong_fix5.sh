#!/bin/bash
# Symmetric two-program ping-pong: each program evicts the other; at the end of
# its turn a program replays the other's code+data address list. Shares the
# fix5 model (bp 252c9c9c8) with run_matrix_fix5.sh.
cd "$(dirname "$0")"
export MODEL_ROOT=/home/coyang/sim-models/replay-fix5 BUFFER=0 PF_FULL=1 PF_ELS=8 PF_OUT=8 RINST=1 IPF_ELS=8 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64 BUILD_JOBS=10
ulimit -f 204800
S=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_pingpong_benchmark.c
for m in 1 2 4; do
  SRC=$S bash run_native_src.sh pp5-m$m 160 256 -DMODES=$m -DROUNDS=4 -DWARMUP=1 > pp5-m$m.out 2>&1 &
  sleep 5
done
wait; echo ALL_DONE
