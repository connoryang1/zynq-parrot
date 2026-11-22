# ROOT-only host fixture, no Vivado loaded or launched. Use fresh admitted cwd.
if {[llength $argv]!=1} {error "one exact TOP Tcl path"}
source [lindex $argv 0]
array set properties {}
proc set_param {args} {}
proc get_runs {name} {return $name}
proc list_property {run} {global properties;return [array names properties]}
proc get_property {name run} {global properties;return $properties($name)}
proc set_property {name value run} {
 global properties
 if {$name eq "strategy"} {
  foreach step {OPT_DESIGN PLACE_DESIGN PHYS_OPT_DESIGN ROUTE_DESIGN POST_ROUTE_PHYS_OPT_DESIGN} {
   set properties(STEPS.$step.ARGS.DIRECTIVE) Explore
  }
  set properties(STEPS.ROUTE_DESIGN.ARGS.MORE_OPTIONS) {-tns_cleanup}
 } else {set properties($name) $value}
}
proc launch_runs {args} {global launched;set launched $args}
proc wait_on_run {args} {}
proc open_run {args} {}
set ::env(IMPL_STRATEGY) Performance_ExplorePostRoutePhysOpt
unset -nocomplain ::env(IMPL_OPT_DIRECTIVE)
vivado_impl_wrap 1 8
if {[get_property STEPS.OPT_DESIGN.ARGS.DIRECTIVE impl_1] ne "Explore"} {error "default"}
set ::env(IMPL_OPT_DIRECTIVE) ExploreArea
vivado_impl_wrap 1 8
if {[get_property STEPS.OPT_DESIGN.ARGS.DIRECTIVE impl_1] ne "ExploreArea"} {error "selected"}
foreach step {PLACE_DESIGN PHYS_OPT_DESIGN ROUTE_DESIGN POST_ROUTE_PHYS_OPT_DESIGN} {
 if {[get_property STEPS.$step.ARGS.DIRECTIVE impl_1] ne "Explore"} {error "changed other step"}
}
if {$launched ne {impl_1 -to_step write_bitstream -jobs 8}} {error "launch arguments"}
set ::env(IMPL_OPT_DIRECTIVE) invalid
if {![catch {vivado_impl_wrap 1 8}]} {error "invalid enum accepted"}
puts "OPT_SELECTOR_HOST_MOCK_PASS no_vendor=1"
