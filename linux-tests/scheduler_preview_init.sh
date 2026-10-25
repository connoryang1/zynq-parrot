#!/bin/sh
/bin/mount -t devtmpfs devtmpfs /dev
exec </dev/console >/dev/console 2>&1
echo SCHED_PREVIEW_INIT_START
/scheduler_data_preview
rc=$?
echo SCHED_PREVIEW_INIT_RESULT=$rc
/sbin/poweroff -f
