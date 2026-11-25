#!/usr/bin/env bash
# Isolated native full-model (black-parrot-example) build + run of the
# foreground/background retained-line microbenchmark. No FPGA/board actions.
# Usage: run_native.sh <label> <delay> <sets> [extra CFLAGS...]
# Builds in /run/user/1001 (RAM) because / is full; copies logs to research.
set -euo pipefail
label=$1; delay=$2; sets=$3; shift 3
TOP=/home/coyang/zynq-parrot-retained-preserve-20261124
BP=/home/coyang/bp-retained-preserve-20261124
INSTALL=/home/coyang/zynq-parrot-linux-research/install
IMPORT=/home/coyang/zynq-parrot-linux-research/import
HERE=$TOP/research/retained-preserve-fgbg-20261124
MODEL=${MODEL_ROOT:-/run/user/1001}/zp-retained-fgbg-model-d${delay}-s${sets}-i${I_LINES:-256}-d${D_LINES:-256}-l2s${L2_SETS:-64}
OUT=$HERE/$label
mkdir -p "$OUT"
export LD_LIBRARY_PATH=$INSTALL/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
CFG=e_bp_unicore_zynqparrot_prefetch16k_cfg
opts=(TOP=$TOP ZP_INSTALL_DIR=$INSTALL ZP_IMPORT_DIR=$IMPORT BP_RTL_DIR=$BP CFG=$CFG
      BP_RETAINED_I_LINES=${I_LINES:-256} BP_RETAINED_D_LINES=${D_LINES:-256} BP_RETAINED_SETS=$sets BP_ZP_L2_SETS=${L2_SETS:-64}
      BP_AXI_RESPONSE_DELAY=$delay BP_CACHE_MISS_TRACE=0 BP_RETAINED_OBSERVE=1)
if [[ ! -x $MODEL/design/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench ]]; then
  rm -rf "$MODEL"; mkdir -p "$MODEL/design/verilator" "$MODEL/program/bootrom"
  for n in Makefile.design Makefile.hardware Makefile.collateral ps.cpp ps.hpp; do
    cp $TOP/cosim/black-parrot-example/$n $MODEL/design/$n; done
  ln -s $TOP/cosim/black-parrot-example/v $MODEL/design/v
  cp $TOP/cosim/black-parrot-example/verilator/Makefile $MODEL/design/verilator/Makefile
  cp /home/coyang/zynq-parrot-linux-research/riscv/bootrom/bootrom.none.riscv $MODEL/program/bootrom/
  ( cd $MODEL/design/verilator && /usr/bin/time -v make -j1 build "${opts[@]}" ZP_RISCV_DIR=$MODEL/program \
      VERILATOR_BUILD_JOBS=${BUILD_JOBS:-10} EXTRA_DEFINES=BSG_HIDE_FROM_SYNTHESIS \
      VERILATOR_SUPPORT_SOURCES=$TOP/testing/rtl/scoped-assertions/bsg_clkgate_optional.sv ) > "$OUT/build.log" 2>&1 \
      || { echo "BUILD FAILED; see $OUT/build.log"; tail -30 "$OUT/build.log"; exit 1; }
fi
run=$MODEL/design/verilator
CC=$INSTALL/bin/riscv64-unknown-elf-gcc
$CC -O2 -I$TOP/software/include -I$INSTALL/riscv64-unknown-elf/include \
  --specs=$INSTALL/riscv64-unknown-elf/lib/dramfs.specs --specs=$INSTALL/riscv64-unknown-elf/lib/perch.specs \
  "$@" -o $OUT/prog.riscv ${SRC:-$TOP/testing/rtl/retained_fgbg_benchmark.c}
# Per-label NBF and cwd so several cases can run in parallel on one model.
exec 9>$MODEL/.nbf.lock; flock 9
cp $OUT/prog.riscv $run/prog.riscv
rm -f $run/prog.mem $run/prog.nbf
( cd $run && make prog.nbf "${opts[@]}" ZP_RISCV_DIR=$MODEL/program ) > "$OUT/nbf.log" 2>&1
cp $run/prog.nbf $OUT/prog.nbf
flock -u 9
( cd $OUT && timeout 7200 $run/obj_dir/Vbsg_nonsynth_zynq_testbench +c_args=$OUT/prog.nbf ) > "$OUT/run.log" 2>&1 || true
grep -aE "FGBG|BSG-PASS|BSG-FAIL|CORE PASS|CORE FAIL" "$OUT/run.log" | head -20
