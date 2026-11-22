create_clock -name owning_clock -period 50 -waveform {0 25} [get_ports clk_i]
set_input_delay 0 -clock owning_clock [get_ports -filter {DIRECTION == IN && NAME != clk_i}]
set_output_delay 0 -clock owning_clock [get_ports -filter {DIRECTION == OUT}]
