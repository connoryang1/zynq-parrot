#!/bin/bash
# Timing stress of fix14 (BP d70ec851e): same matrix at memory delays 100 and
# 240 (vs 160), uncapped, to move cycle alignments that exposed earlier races.
cd "$(dirname "$0")"
ulimit -f 409600
H=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_hybrid_benchmark.c
P=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_pingpong_benchmark.c
export BUFFER=0 PF_FULL=1 RINST=1 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64 HOLD=1 IBYP=1 PF_ELS=24 PF_OUT=24 IPF_ELS=24 DBG_DEFINES=BP_REPLAY_STATS
for d in 100 240; do
 ( export MODEL_ROOT=/home/coyang/sim-models/stress14-d$d; p=s14d$d
   BUILD_JOBS=5 SRC=$H bash run_native_src.sh $p-h-t0-m4 $d 256 -DTRIG=0 -DMODES=4 -DROUNDS=4 -DWARMUP=1 > $p-h-t0-m4.out 2>&1 &
   sleep 5; until ls $MODEL_ROOT/*/design/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench >/dev/null 2>&1 || grep -q "BUILD FAILED" $p-h-t0-m4.out; do sleep 20; done
   grep -q "BUILD FAILED" $p-h-t0-m4.out && { echo "$p BUILD_FAILED"; exit 1; }
   sleep 20
   SRC=$P bash run_native_src.sh $p-pp-m2 $d 256 -DMODES=2 -DROUNDS=4 -DWARMUP=1 > $p-pp-m2.out 2>&1 &
   SRC=$P bash run_native_src.sh $p-pp-m4 $d 256 -DMODES=4 -DROUNDS=4 -DWARMUP=1 > $p-pp-m4.out 2>&1 &
   for c in "0 2" "3 2" "3 4"; do set -- $c
     SRC=$H bash run_native_src.sh $p-h-t$1-m$2 $d 256 -DTRIG=$1 -DMODES=$2 -DROUNDS=4 -DWARMUP=1 > $p-h-t$1-m$2.out 2>&1 &
     sleep 5; done
   wait ) &
 sleep 30
done
wait; echo ALL_DONE
