# Standalone synthesis feasibility only; no implementation/bitstream/board.
# Root owns execution in isolated host RAM/remote VM with pinned Vivado.
if {$argc != 1} { error "usage: vivado -mode batch -source inference.tcl -tclargs NEW_OUTPUT_DIR" }
set here [file dirname [file normalize [info script]]]
set root [file normalize [file join $here ../../..]]
set output [file normalize [lindex $argv 0]]
if {[file exists $output]} { error "preserve prior inference evidence; output must be new" }
file mkdir $output
set source_handle [open [file join $output source-identities.txt] w]
foreach source [list [info script] [file join $root cosim/black-parrot-example/v/bp_axi_response_delay.sv] [file join $root cosim/black-parrot-example/v/bp_axi_response_delay_fifo.sv]] {
  puts $source_handle [exec sha256sum $source]
}
close $source_handle
read_verilog -sv [list [file join $root cosim/black-parrot-example/v/bp_axi_response_delay.sv] [file join $root cosim/black-parrot-example/v/bp_axi_response_delay_fifo.sv]]
synth_design -top bp_axi_response_delay -mode out_of_context -part xc7z020clg400-1 -flatten_hierarchy rebuilt
report_utilization -hierarchical -file [file join $output utilization.rpt]
report_ram_utilization -file [file join $output ram-utilization.rpt]
set primitives [get_cells -hierarchical -filter {REF_NAME =~ RAMB*}]
set handle [open [file join $output primitives.txt] w]
puts $handle "Vivado [version -short]; response-delay default MAX384 FIFO512 R73 B8"
set r_count 0
set b_count 0
foreach cell $primitives {
  puts $handle "$cell [get_property REF_NAME $cell]"
  if {[string match "*r_fifo*" $cell]} { incr r_count }
  if {[string match "*b_fifo*" $cell]} { incr b_count }
}
puts $handle "R_FIFO_BRAM_PRIMITIVES=$r_count B_FIFO_BRAM_PRIMITIVES=$b_count"
close $handle
if {$r_count == 0 || $b_count == 0} { error "both timestamped response FIFOs must retain identifiable inferred BRAM; inspect reports" }
write_checkpoint [file join $output shim-synth.dcp]
puts "AXI_RESPONSE_DELAY_BRAM_INFERENCE_ONLY_PASS"
