#!/bin/sh

case "$1" in
  start)
    echo "[BP-LINUX-CTXTSW] launching user-mode handoff smoke"
    /usr/bin/ctxtsw_user_smoke
    status=$?
    if [ "$status" -ne 0 ]; then
      echo "[BP-LINUX-CTXTSW] FAIL: program exit status $status"
      # Leave the target running so the bounded host runner reports failure;
      # a poweroff after a failed test could otherwise look like success.
      exit "$status"
    fi
    echo "[BP-LINUX-CTXTSW] powering off"
    poweroff -f -d 3
    ;;
esac

exit 0
