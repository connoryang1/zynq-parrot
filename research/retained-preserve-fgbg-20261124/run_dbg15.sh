#!/bin/bash
# Debug the deterministic restart (8 in flight, hold, code direct path,
# end-of-turn both lanes): trap, I-cache write and install traces.
cd "$(dirname "$0")"
ulimit -f 1048576
H=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_hybrid_benchmark.c
env BUFFER=0 PF_FULL=1 RINST=1 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64 BUILD_JOBS=10 HOLD=1 IBYP=1 PF_ELS=8 PF_OUT=8 IPF_ELS=8 \
  DBG_DEFINES="BP_ICACHE_INSTALL_DEBUG BP_REPLAY_INSTALL_TRACE BP_REPLAY_STATS BP_ICDBG_WIN_LO=158150 BP_ICDBG_WIN_HI=158207" MODEL_ROOT=/home/coyang/sim-models/dbg-pf8w2 \
  SRC=$H bash run_native_src.sh d15-pf8fe 160 256 -DTRIG=3 -DMODES=2 -DROUNDS=4 -DWARMUP=1 > d15-pf8fe.out 2>&1
echo ALL_DONE
