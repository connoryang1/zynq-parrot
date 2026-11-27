#!/bin/bash
# Combined: hold fix + code replay on the direct path (with the install now
# waiting for an empty I-cache pipeline) + 24 requests in flight, with the
# sim-only replay survival counters (BP_REPLAY_STATS).
cd "$(dirname "$0")"
ulimit -f 204800
H=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_hybrid_benchmark.c
P=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_pingpong_benchmark.c
C="BUFFER=0 PF_FULL=1 RINST=1 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64 HOLD=1 IBYP=1 PF_ELS=24 PF_OUT=24 IPF_ELS=24 DBG_DEFINES=BP_REPLAY_STATS MODEL_ROOT=/home/coyang/sim-models/replay-fix9"
env $C BUILD_JOBS=4 SRC=$H bash run_native_src.sh h9-t2-m2 160 256 -DTRIG=2 -DMODES=2 -DROUNDS=4 -DWARMUP=1 > h9-t2-m2.out 2>&1 &
sleep 5; until ls /home/coyang/sim-models/replay-fix9/*/design/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench >/dev/null 2>&1 || grep -q "BUILD FAILED" h9-t2-m2.out; do sleep 20; done
grep -q "BUILD FAILED" h9-t2-m2.out && { echo BUILD_FAILED; wait; exit 1; }
until grep -q ALL_DONE run_mlp24_fix8.log 2>/dev/null; do sleep 30; done
for c in "0 2" "0 4" "3 2" "3 4" "1 2"; do set -- $c
  env $C SRC=$H bash run_native_src.sh h9-t$1-m$2 160 256 -DTRIG=$1 -DMODES=$2 -DROUNDS=4 -DWARMUP=1 > h9-t$1-m$2.out 2>&1 &
  sleep 5; done
for m in 1 2 4; do
  env $C SRC=$P bash run_native_src.sh pp9-m$m 160 256 -DMODES=$m -DROUNDS=4 -DWARMUP=1 > pp9-m$m.out 2>&1 &
  sleep 5; done
wait; echo ALL_DONE
