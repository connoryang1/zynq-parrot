set_param general.maxThreads 8
set routed_checkpoint "/tmp/zynq-parrot-fpga-20261026T014703Z-8eb12f4f/cosim/black-parrot-example/vivado/black_parrot_bd_proj.runs/impl_1/black_parrot_bd_1_wrapper_routed.dcp"
set out_dir "/home/coyang/fpga-logs-consume-only-pc-physopt-20261026"
file mkdir $out_dir
open_checkpoint $routed_checkpoint
report_timing_summary -max_paths 10 -report_unconstrained -warn_on_violation -file "$out_dir/timing_pre_physopt.rpt"
phys_opt_design -directive AggressiveExplore
report_timing_summary -max_paths 10 -report_unconstrained -warn_on_violation -file "$out_dir/timing_summary.rpt"
report_route_status -file "$out_dir/route_status.rpt"
report_utilization -file "$out_dir/utilization.rpt"
report_drc -file "$out_dir/drc.rpt"
write_checkpoint -force "$out_dir/consume-only-pc-postroute-physopt.dcp"
write_bitstream -force "$out_dir/black_parrot_bd_1.bit"
