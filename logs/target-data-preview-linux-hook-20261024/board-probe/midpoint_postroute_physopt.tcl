open_checkpoint /tmp/zynq-parrot-fpga-20261025T072743Z-7f83df87/cosim/black-parrot-example/vivado/black_parrot_bd_proj.runs/impl_1/black_parrot_bd_1_wrapper_routed.dcp
report_timing_summary -max_paths 10 -report_unconstrained -warn_on_violation -file /home/coyang/fpga-logs-linux-52-prefetch5-physopt/20261025T081523Z-7f83df87/timing_pre_physopt.rpt
phys_opt_design -directive AggressiveExplore
report_route_status -file /home/coyang/fpga-logs-linux-52-prefetch5-physopt/20261025T081523Z-7f83df87/route_status.rpt
report_drc -file /home/coyang/fpga-logs-linux-52-prefetch5-physopt/20261025T081523Z-7f83df87/drc.rpt
report_timing_summary -max_paths 10 -report_unconstrained -warn_on_violation -file /home/coyang/fpga-logs-linux-52-prefetch5-physopt/20261025T081523Z-7f83df87/timing_summary.rpt
write_checkpoint -force /home/coyang/fpga-logs-linux-52-prefetch5-physopt/20261025T081523Z-7f83df87/midpoint-postroute-physopt.dcp
write_bitstream -force /home/coyang/fpga-logs-linux-52-prefetch5-physopt/20261025T081523Z-7f83df87/black_parrot_bd_1.bit
exit
