#!/bin/bash
# Why does early replay lose in ping-pong? Phase timing, and the tail scan
# replaced by an idle wait (TAIL_SPIN) to isolate interference from the tail.
cd "$(dirname "$0")"
export MODEL_ROOT=/home/coyang/sim-models/replay-fix5 BUFFER=0 PF_FULL=1 PF_ELS=8 PF_OUT=8 RINST=1 IPF_ELS=8 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64
ulimit -f 204800
P=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_pingpong_benchmark.c
for sp in 0 50000; do for m in 1 2 4; do
  SRC=$P bash run_native_src.sh ppd-s$sp-m$m 160 256 -DMODES=$m -DTAIL_SPIN=$sp -DROUNDS=4 -DWARMUP=1 > ppd-s$sp-m$m.out 2>&1 &
  sleep 5; done; done
wait; echo ALL_DONE
