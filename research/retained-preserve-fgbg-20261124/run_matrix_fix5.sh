#!/bin/bash
# Replay hybrid comparison after the I-cache stale-tag fix (bp 252c9c9c8).
# Model lives on regular disk so a reboot does not wipe it.
cd "$(dirname "$0")"
export MODEL_ROOT=/home/coyang/sim-models/replay-fix5 BUFFER=0 PF_FULL=1 PF_ELS=8 PF_OUT=8 RINST=1 IPF_ELS=8 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64 BUILD_JOBS=10
ulimit -f 204800   # 200 MiB per file: a runaway sim log dies instead of filling the disk
S=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_hybrid_benchmark.c
SRC=$S bash run_native_src.sh h5-off 160 256 -DMODES=0x1 -DROUNDS=4 -DWARMUP=1 > h5-off.out 2>&1 &
sleep 5; until ls $MODEL_ROOT/*/design/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench >/dev/null 2>&1; do sleep 20; done; sleep 30
SRC=$S bash run_native_src.sh h5-warm 160 256 -DMODES=0x8 -DROUNDS=4 -DWARMUP=1 > h5-warm.out 2>&1 &
for c in "0 2" "0 4" "3 2" "3 4" "2 2"; do set -- $c
  SRC=$S bash run_native_src.sh h5-t$1-m$2 160 256 -DTRIG=$1 -DMODES=$2 -DROUNDS=4 -DWARMUP=1 > h5-t$1-m$2.out 2>&1 &
  sleep 5; done
wait; echo ALL_DONE
