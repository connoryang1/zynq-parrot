#!/bin/bash
# Full replay model: hold fix, direct path for code and data, 24 in flight,
# I-cache pipeline-empty install gate, stale-data protection (L2 dirty filter
# + cancel on own write-back). Sim-only survival stats and install trace.
cd "$(dirname "$0")"
ulimit -f 409600
H=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_hybrid_benchmark.c
P=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_pingpong_benchmark.c
export BUFFER=0 PF_FULL=1 RINST=1 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64 HOLD=1 IBYP=1 PF_ELS=24 PF_OUT=24 IPF_ELS=24 MODEL_ROOT=/home/coyang/sim-models/replay-fix10
export DBG_DEFINES="BP_REPLAY_STATS BP_REPLAY_INSTALL_TRACE"
BUILD_JOBS=10 SRC=$P bash run_native_src.sh pp10-m2 160 256 -DMODES=2 -DROUNDS=4 -DWARMUP=1 > pp10-m2.out 2>&1 &
sleep 5; until ls $MODEL_ROOT/*/design/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench >/dev/null 2>&1 || grep -q "BUILD FAILED" pp10-m2.out; do sleep 20; done
grep -q "BUILD FAILED" pp10-m2.out && { echo BUILD_FAILED; wait; exit 1; }
sleep 20
SRC=$P bash run_native_src.sh pp10-m4 160 256 -DMODES=4 -DROUNDS=4 -DWARMUP=1 > pp10-m4.out 2>&1 &
for c in "0 2" "0 4" "3 2" "3 4" "1 2" "2 2"; do set -- $c
  SRC=$H bash run_native_src.sh h10-t$1-m$2 160 256 -DTRIG=$1 -DMODES=$2 -DROUNDS=4 -DWARMUP=1 > h10-t$1-m$2.out 2>&1 &
  sleep 5; done
wait; echo ALL_DONE
