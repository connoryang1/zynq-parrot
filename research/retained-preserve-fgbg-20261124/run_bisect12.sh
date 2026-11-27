#!/bin/bash
# Bisect the single-direction end-of-turn (TRIG=3) background-tail corruption:
# full model minus one feature each.
cd "$(dirname "$0")"
ulimit -f 204800
H=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_hybrid_benchmark.c
B="BUFFER=0 PF_FULL=1 RINST=1 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64 BUILD_JOBS=3"
env $B IBYP=1 PF_ELS=24 PF_OUT=24 IPF_ELS=24 MODEL_ROOT=/home/coyang/sim-models/bisect-nohold SRC=$H bash run_native_src.sh b12-nohold 160 256 -DTRIG=3 -DMODES=2 -DROUNDS=4 -DWARMUP=1 > b12-nohold.out 2>&1 &
env $B HOLD=1 PF_ELS=24 PF_OUT=24 IPF_ELS=24 MODEL_ROOT=/home/coyang/sim-models/bisect-noibyp SRC=$H bash run_native_src.sh b12-noibyp 160 256 -DTRIG=3 -DMODES=2 -DROUNDS=4 -DWARMUP=1 > b12-noibyp.out 2>&1 &
env $B HOLD=1 IBYP=1 PF_ELS=8 PF_OUT=8 IPF_ELS=8 MODEL_ROOT=/home/coyang/sim-models/bisect-pf8 SRC=$H bash run_native_src.sh b12-pf8 160 256 -DTRIG=3 -DMODES=2 -DROUNDS=4 -DWARMUP=1 > b12-pf8.out 2>&1 &
wait; echo ALL_DONE
