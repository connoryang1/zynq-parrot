#!/bin/bash
# (1) Replay installs wait for an unrelated demand miss instead of dropping
#     the line (BP_REPLAY_HOLD_ON_DEMAND), code replay still via L2.
# (2) Debug build with code replay on the direct path, to localize the
#     wake-mode corruption (BP_ICACHE_INSTALL_DEBUG).
cd "$(dirname "$0")"
ulimit -f 204800
H=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_hybrid_benchmark.c
P=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_pingpong_benchmark.c
COMMON="BUFFER=0 PF_FULL=1 PF_ELS=8 PF_OUT=8 RINST=1 IPF_ELS=8 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64 BUILD_JOBS=5"
env $COMMON MODEL_ROOT=/home/coyang/sim-models/replay-dbg IBYP=1 DBG_DEFINES=BP_ICACHE_INSTALL_DEBUG SRC=$H \
  bash run_native_src.sh dbg7-t2-m2 160 256 -DTRIG=2 -DMODES=2 -DROUNDS=2 -DWARMUP=1 > dbg7-t2-m2.out 2>&1 &
env $COMMON MODEL_ROOT=/home/coyang/sim-models/replay-fix7 HOLD=1 SRC=$P \
  bash run_native_src.sh pp7-m4 160 256 -DMODES=4 -DROUNDS=4 -DWARMUP=1 > pp7-m4.out 2>&1 &
sleep 5; until ls /home/coyang/sim-models/replay-fix7/*/design/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench >/dev/null 2>&1 || grep -q "BUILD FAILED" pp7-m4.out; do sleep 20; done
grep -q "BUILD FAILED" pp7-m4.out && { echo BUILD_FAILED; wait; exit 1; }
sleep 20
env $COMMON MODEL_ROOT=/home/coyang/sim-models/replay-fix7 HOLD=1 SRC=$P bash run_native_src.sh pp7-m2 160 256 -DMODES=2 -DROUNDS=4 -DWARMUP=1 > pp7-m2.out 2>&1 &
for c in "0 2" "0 4" "1 2" "1 4" "3 4"; do set -- $c
  env $COMMON MODEL_ROOT=/home/coyang/sim-models/replay-fix7 HOLD=1 SRC=$H bash run_native_src.sh h7-t$1-m$2 160 256 -DTRIG=$1 -DMODES=$2 -DROUNDS=4 -DWARMUP=1 > h7-t$1-m$2.out 2>&1 &
  sleep 5; done
wait; echo ALL_DONE
