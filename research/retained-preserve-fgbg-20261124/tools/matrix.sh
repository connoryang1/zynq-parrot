#!/bin/bash
# Build one native full-core model and run a set of replay benchmark cells on it.
# Usage: tools/matrix.sh <prefix> <model_root> [cell ...]
# Cells: h-t<TRIG>-m<MODES> (hybrid), pp-m<MODES> (ping-pong), h-ref / pp-ref
# (MODES=9: off + warm references). Default: the standard 6-cell matrix.
# Knobs (env): DELAY (160), XCFLAGS (extra program CFLAGS, e.g. -DEVMARK),
# BUILD_JOBS (5), plus every run_native_src.sh knob (CAP, HOLD, DBG_DEFINES...).
# Writes <prefix>.done with one PASS/FAIL line per cell when everything ends.
set -u
cd "$(dirname "$0")/.."
ulimit -f 409600
prefix=$1; export MODEL_ROOT=$2; shift 2
cells=("$@"); [ ${#cells[@]} -eq 0 ] && cells=(h-t0-m2 h-t0-m4 h-t3-m2 h-t3-m4 pp-m2 pp-m4)
: "${BUFFER:=0}" "${PF_FULL:=1}" "${RINST:=1}" "${DRE:=256}" "${I_LINES:=0}" "${D_LINES:=0}" "${L2_SETS:=64}"
: "${HOLD:=1}" "${IBYP:=1}" "${PF_ELS:=24}" "${PF_OUT:=24}" "${IPF_ELS:=24}" "${DELAY:=160}" "${BUILD_JOBS:=5}"
export BUFFER PF_FULL RINST DRE I_LINES D_LINES L2_SETS HOLD IBYP PF_ELS PF_OUT IPF_ELS BUILD_JOBS
T=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl
run_cell() { # $1 cell
  local c=$1 src args
  case $c in
    h-ref) src=$T/replay_hybrid_benchmark.c; args="-DTRIG=0 -DMODES=9" ;;
    pp-ref) src=$T/replay_pingpong_benchmark.c; args="-DMODES=9" ;;
    h-t*-m*) src=$T/replay_hybrid_benchmark.c; t=${c#h-t}; args="-DTRIG=${t%%-*} -DMODES=${c##*-m}" ;;
    pp-m*) src=$T/replay_pingpong_benchmark.c; args="-DMODES=${c##*-m}" ;;
    *) echo "bad cell $c"; return 1 ;;
  esac
  SRC=$src bash run_native_src.sh $prefix-$c $DELAY 256 $args -DROUNDS=4 -DWARMUP=1 ${XCFLAGS:-} > $prefix-$c.out 2>&1
}
rm -f $prefix.done
run_cell ${cells[0]} &
sleep 5
until ls $MODEL_ROOT/*/design/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench >/dev/null 2>&1 || grep -q "BUILD FAILED" $prefix-${cells[0]}.out 2>/dev/null; do sleep 15; done
if grep -q "BUILD FAILED" $prefix-${cells[0]}.out; then echo "BUILD_FAILED $(grep -m1 '%Error' $prefix-${cells[0]}/build.log)" > $prefix.done; exit 1; fi
sleep 20
for c in "${cells[@]:1}"; do run_cell $c & sleep 3; done
wait
for c in "${cells[@]}"; do
  f=$prefix-$c/run.log
  # Debug displays (EV/REPLAYSTATS/DTRACE) interleave mid-line with program output.
  st=$(python3 -c "import re,sys;t=re.sub(r'(EV |REPLAYSTATS|DTRACE)[^\n]*\n','',open(sys.argv[1],errors='replace').read());print('PASS' if '[BSG-PASS]' in t else 'FAIL '+(re.findall(r'\[BSG-FAIL\][^\n]*',t)+[''])[0])" $f 2>/dev/null || echo FAIL)
  if [ "$st" = PASS ]; then echo "PASS $prefix-$c"; else echo "FAIL $prefix-$c ${st#FAIL}"; fi
done > $prefix.done
