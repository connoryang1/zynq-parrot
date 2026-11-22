# Pure Tcl replay of the exact production parser; no Vivado commands sourced.
set p [open [lindex $argv 0] r];set source [read $p];close $p
set begin [string first {proc value } $source]
set end [string first {proc clockgate} $source]
if {$begin<0 || $end<=$begin} {error "exact parser boundaries"}
eval [string range $source $begin [expr {$end-1}]]
set labels {{Slice LUTs*} {LUT as Logic} {LUT as Memory} {LUT as Distributed RAM} {LUT as Shift Register} {Slice Registers}}
set expected {{54072 50099 3973 3817 156 26901} {53370 49397 3973 3817 156 26901} {51141 47194 3947 3807 140 26907}}
set reports {};set n 0
foreach path [lrange $argv 1 end] values $expected {
 set f [open $path r];set report [read $f];close $f;lappend reports $report
 foreach label $labels want $values {
  set got [value $report $label]
  if {$got ne $want} {error "actual report mismatch $path $label $got != $want"}
  incr n
 }
 puts "ACTUAL_REPORT_PASS $path expected=$values"
}
if {[llength $reports]!=3 || $n!=18} {error "three actual report/18 known-field comparisons"}
set sample [lindex $reports 0]
set row {| Slice LUTs*                | 54072 |}
if {[string first $row $sample]<0} {error "mutation anchor"}
proc reject {report label name} {
 if {![catch {value $report $label}]} {error "negative accepted: $name"}
 puts "NEGATIVE_REJECT $name"
}
reject [string map [list $row "$row\n$row"] $sample] {Slice LUTs*} duplicate_summary_row
reject [string map [list $row {| Removed                  | 54072 |}] $sample] {Slice LUTs*} missing_row
reject [string map [list $row {| Slice LUTs*                | 54072.5 |}] $sample] {Slice LUTs*} fractional_count
reject [string map [list $row {| Slice LUTs**               | 54072 |}] $sample] {Slice LUTs*} double_footnote
reject $sample {Some Other Resource} unknown_label
reject [string map [list $row {| Slice LUTs*                | 54,07 |}] $sample] {Slice LUTs*} malformed_comma_integer
set comma [string map [list $row {| Slice LUTs*                | 54,072 |}] $sample]
if {[value $comma {Slice LUTs}] ne "54072"} {error "valid integer grouping/optional input star"}
puts "PARSER_PASS actual_fields=18 negative_cases=6 valid_grouping=1 no_vendor=1"
