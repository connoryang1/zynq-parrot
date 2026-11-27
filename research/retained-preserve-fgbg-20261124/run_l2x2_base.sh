#!/bin/bash
# Larger-L2 baseline: L2 doubled to 128 sets (32 KiB, more than the ~8.5 KiB
# of replay storage), replay hardware present but never triggered (off) plus
# the warm reference, on both benchmarks.
cd "$(dirname "$0")"
ulimit -f 204800
H=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_hybrid_benchmark.c
P=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_pingpong_benchmark.c
export BUFFER=0 PF_FULL=1 RINST=1 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=128 HOLD=1 IBYP=1 PF_ELS=24 PF_OUT=24 IPF_ELS=24 MODEL_ROOT=/home/coyang/sim-models/l2x2
BUILD_JOBS=8 SRC=$H bash run_native_src.sh l2x2-h-off 160 256 -DMODES=1 -DROUNDS=4 -DWARMUP=1 > l2x2-h-off.out 2>&1
SRC=$H bash run_native_src.sh l2x2-h-warm 160 256 -DMODES=8 -DROUNDS=4 -DWARMUP=1 > l2x2-h-warm.out 2>&1 &
SRC=$P bash run_native_src.sh l2x2-p-off 160 256 -DMODES=1 -DROUNDS=4 -DWARMUP=1 > l2x2-p-off.out 2>&1 &
SRC=$P bash run_native_src.sh l2x2-p-warm 160 256 -DMODES=8 -DROUNDS=4 -DWARMUP=1 > l2x2-p-warm.out 2>&1 &
wait; echo ALL_DONE
