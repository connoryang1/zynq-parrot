source [file join [file dirname [info script]] ../../../cosim/tcl/vivado-utils.tcl]
set names {BP_RETAINED_BUFFER BP_RETAINED_I_LINES BP_RETAINED_D_LINES BP_RETAINED_SETS BP_RETAINED_OBSERVE BP_AXI_RESPONSE_DELAY}
foreach name $names { unset -nocomplain ::env($name) }
proc check {condition message} { if {![uplevel 1 [list expr $condition]]} {error $message} }
proc rejects {script} { check {[catch {uplevel 1 $script}]} "expected rejection: $script" }
check {[vivado_experiment_defines] eq {}} "legacy ambient configuration changed"
set ::env(BP_RETAINED_BUFFER) 1
rejects {vivado_experiment_defines}
set ::env(BP_RETAINED_I_LINES) 1280
set ::env(BP_RETAINED_D_LINES) 0
set ::env(BP_RETAINED_SETS) 256
set ::env(BP_RETAINED_OBSERVE) 1
set ::env(BP_AXI_RESPONSE_DELAY) 200
check {[vivado_experiment_defines] eq {BP_RETAINED_BUFFER=1 BP_RETAINED_I_LINES=1280 BP_RETAINED_D_LINES=0 BP_RETAINED_SETS=256 BP_RETAINED_OBSERVE=1 BP_AXI_RESPONSE_DELAY=200}} "wrong define set"
foreach {name values} {BP_RETAINED_BUFFER {2 DEFINED -1 01 {1;error oops}} BP_RETAINED_SETS {0 3 65536} BP_RETAINED_I_LINES {65536} BP_AXI_RESPONSE_DELAY {385 -1}} {
    set good $::env($name)
    foreach bad $values { set ::env($name) $bad; rejects {vivado_experiment_defines} }
    set ::env($name) $good
}
set fake_defines {EXISTING=7}
proc get_filesets {name} { return $name }
proc current_project {} { return mock_source_or_consumer }
proc get_property {property object} { return $::fake_defines }
proc set_property {property value object} { set ::fake_defines $value }
vivado_apply_experiment_defines
check {[llength $fake_defines] == 7 && "EXISTING=7" in $fake_defines} "lost existing define"
vivado_apply_experiment_defines
check {[llength $fake_defines] == 7} "duplicate defines"
lappend fake_defines BP_RETAINED_BUFFER=0
rejects {vivado_apply_experiment_defines}
set fake_defines {}
rename set_property working_set_property
proc set_property {property value object} {}
rejects {vivado_apply_experiment_defines}
rename set_property {}
rename working_set_property set_property
puts "PASS allowlist, static config independence, zero side, validation, idempotence and conflict rejection"
