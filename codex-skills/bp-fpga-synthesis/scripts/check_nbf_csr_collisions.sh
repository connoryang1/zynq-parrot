#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <program.nbf> <csr-hex> [csr-hex ...]" >&2
  exit 2
}

[[ $# -ge 2 ]] || usage

nbf=$1
shift
[[ -f "$nbf" ]] || { echo "error: NBF not found: $nbf" >&2; exit 2; }

wanted=$(printf '%s\n' "$@" | tr '[:upper:]' '[:lower:]' | sed 's/^0x//' | paste -sd,)

awk -F_ -v wanted="$wanted" '
  BEGIN {
    count = split(wanted, csr_list, ",");
    for (i = 1; i <= count; i++) target[csr_list[i]] = 1;
    collisions = 0;
  }
  function check_word(word, lane, base, csr) {
    if (length(word) != 8 || tolower(substr(word, 7, 2)) != "73") return;
    csr = tolower(substr(word, 1, 3));
    if (csr in target) {
      printf("NBF_CSR_COLLISION line=%d nbf_addr=0x%s lane=%s instruction=0x%s csr=0x%s\n", NR, base, lane, word, csr);
      collisions++;
    }
  }
  $1 == "03" {
    for (i = 3; i <= NF; i++) {
      data = $i;
      if (length(data) == 16) {
        check_word(substr(data, 9, 8), "low", $2);
        check_word(substr(data, 1, 8), "high", $2);
      }
    }
  }
  END {
    if (collisions) exit 1;
    printf("NBF_CSR_COLLISION_FREE nbf=%s csrs=%s\n", ARGV[1], wanted);
  }
' "$nbf"
