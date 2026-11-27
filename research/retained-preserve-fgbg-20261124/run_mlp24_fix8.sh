#!/bin/bash
# Hold fix + 24 requests in flight (direct-path slots and per-cache prefetch
# buffers 8 -> 24). Code replay still through the L2 (IBYP off) pending the
# direct-path corruption fix. Also the ping-pong warm reference.
cd "$(dirname "$0")"
ulimit -f 204800
H=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_hybrid_benchmark.c
P=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_pingpong_benchmark.c
C="BUFFER=0 PF_FULL=1 RINST=1 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64 HOLD=1 BUILD_JOBS=8"
C8="$C PF_ELS=8 PF_OUT=8 IPF_ELS=8 MODEL_ROOT=/home/coyang/sim-models/replay-fix7"
C24="$C PF_ELS=24 PF_OUT=24 IPF_ELS=24 MODEL_ROOT=/home/coyang/sim-models/replay-fix8"
env $C24 SRC=$H bash run_native_src.sh h8-t3-m4 160 256 -DTRIG=3 -DMODES=4 -DROUNDS=4 -DWARMUP=1 > h8-t3-m4.out 2>&1 &
env $C8 SRC=$P bash run_native_src.sh pp7-m8 160 256 -DMODES=8 -DROUNDS=4 -DWARMUP=1 > pp7-m8.out 2>&1 &
sleep 5; until ls /home/coyang/sim-models/replay-fix8/*/design/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench >/dev/null 2>&1 || grep -q "BUILD FAILED" h8-t3-m4.out; do sleep 20; done
grep -q "BUILD FAILED" h8-t3-m4.out && { echo BUILD_FAILED; wait; exit 1; }
sleep 20
for c in "0 2" "0 4" "1 2" "3 2"; do set -- $c
  env $C24 SRC=$H bash run_native_src.sh h8-t$1-m$2 160 256 -DTRIG=$1 -DMODES=$2 -DROUNDS=4 -DWARMUP=1 > h8-t$1-m$2.out 2>&1 &
  sleep 5; done
for m in 2 4; do
  env $C24 SRC=$P bash run_native_src.sh pp8-m$m 160 256 -DMODES=$m -DROUNDS=4 -DWARMUP=1 > pp8-m$m.out 2>&1 &
  sleep 5; done
wait; echo ALL_DONE
