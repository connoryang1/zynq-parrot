set_param general.maxThreads 4
foreach {label area banked} {native 0 0 area 1 0 banked 0 1} {
  create_project -in_memory -part xc7z020clg400-1
  read_verilog -sv retained_probe.sv
  synth_design -top retained_probe -part xc7z020clg400-1 -generic AREA=$area -generic BANKED=$banked
  create_clock -name lane0 -period 50 [get_ports {clk_i[0]}]
  create_clock -name lane1 -period 50 [get_ports {clk_i[1]}]
  set_clock_groups -asynchronous -group lane0 -group lane1
  report_utilization -hierarchical -file ${label}-utilization.rpt
  set f [open ${label}-primitives.tsv w]
  puts $f "cell\tprimitive\tram_mode\tread_a\twrite_a\tread_b\twrite_b"
  foreach c [lsort [get_cells -hier -filter {REF_NAME =~ RAMB*}]] {
    puts $f [join [list $c [get_property REF_NAME $c] [get_property RAM_MODE $c] [get_property READ_WIDTH_A $c] [get_property WRITE_WIDTH_A $c] [get_property READ_WIDTH_B $c] [get_property WRITE_WIDTH_B $c]] "\t"]
  }
  close $f
  write_checkpoint -force ${label}.dcp
  close_project
}
