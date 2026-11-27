#!/bin/bash
# Code replay through the multi-outstanding bypass (BP_ICACHE_PREFETCH_BYPASS)
# vs the fix5 model (same RTL otherwise). Same benchmarks and knobs.
cd "$(dirname "$0")"
export MODEL_ROOT=/home/coyang/sim-models/replay-fix6 IBYP=1 BUFFER=0 PF_FULL=1 PF_ELS=8 PF_OUT=8 RINST=1 IPF_ELS=8 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64 BUILD_JOBS=3
ulimit -f 204800
H=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_hybrid_benchmark.c
P=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_pingpong_benchmark.c
# Build (first run), then wait for the fix5 batch to free the cores.
SRC=$H bash run_native_src.sh h6-t3-m4 160 256 -DTRIG=3 -DMODES=4 -DROUNDS=4 -DWARMUP=1 > h6-t3-m4.out 2>&1 &
sleep 5; until ls $MODEL_ROOT/*/design/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench >/dev/null 2>&1 || grep -q "BUILD FAILED" h6-t3-m4.out; do sleep 20; done
grep -q "BUILD FAILED" h6-t3-m4.out && { echo BUILD_FAILED; exit 1; }
until grep -q ALL_DONE run_matrix_fix5.log 2>/dev/null && grep -q ALL_DONE run_pingpong_fix5.log 2>/dev/null; do sleep 30; done
for c in "0 2" "0 4" "3 2" "2 2" "2 4"; do set -- $c
  SRC=$H bash run_native_src.sh h6-t$1-m$2 160 256 -DTRIG=$1 -DMODES=$2 -DROUNDS=4 -DWARMUP=1 > h6-t$1-m$2.out 2>&1 &
  sleep 5; done
for m in 2 4; do
  SRC=$P bash run_native_src.sh pp6-m$m 160 256 -DMODES=$m -DROUNDS=4 -DWARMUP=1 > pp6-m$m.out 2>&1 &
  sleep 5; done
wait; echo ALL_DONE
