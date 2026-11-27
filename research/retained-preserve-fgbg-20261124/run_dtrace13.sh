#!/bin/bash
# Cap-8 early/TRIG0 data-corruption localization: same RTL as cap13-c8 plus the
# display-only BP_REPLAY_DATA_TRACE on bg[0x1c40]'s line and the rodata line.
cd "$(dirname "$0")"
ulimit -f 409600
H=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_hybrid_benchmark.c
export BUFFER=0 PF_FULL=1 RINST=1 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64 HOLD=1 IBYP=1 PF_ELS=24 PF_OUT=24 IPF_ELS=24 CAP=8
export DBG_DEFINES="BP_REPLAY_STATS BP_REPLAY_DATA_TRACE BP_DT_W0=33556936 BP_DT_W1=33555842"
export MODEL_ROOT=/home/coyang/sim-models/dtrace13-c8
BUILD_JOBS=6 SRC=$H bash run_native_src.sh dt13-8-h-t0-m4 160 256 -DTRIG=0 -DMODES=4 -DROUNDS=4 -DWARMUP=1 > dt13-8-h-t0-m4.out 2>&1
echo ALL_DONE
