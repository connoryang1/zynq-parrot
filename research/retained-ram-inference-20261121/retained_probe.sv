// Exact retained RAM geometry/clock template, isolated from policy and CPU logic.
// Probe only: compare native inference, area attribute, and bounded banks.
module retained_probe #(parameter AREA=0, BANKED=0)
 (input [1:0] clk_i, v_i, w_i
  ,input [1:0][14:0] data_addr_i
  ,input [1:0][11:0] tag_addr_i
  ,input [1:0][63:0] data_i
  ,input [1:0][28:0] tag_i
  ,output [1:0][63:0] data_o
  ,output [1:0][28:0] tag_o);
  retained_probe_ram #(.WIDTH(64),.DEPTH(20480),.AW(15),.AREA(AREA),.BANKED(BANKED)) payload
   (.clk_i(clk_i),.v_i(v_i),.w_i(w_i),.addr_i(data_addr_i),.data_i(data_i),.data_o(data_o));
  retained_probe_ram #(.WIDTH(29),.DEPTH(2560),.AW(12),.AREA(AREA),.BANKED(BANKED)) tags
   (.clk_i(clk_i),.v_i(v_i),.w_i(w_i),.addr_i(tag_addr_i),.data_i(tag_i),.data_o(tag_o));
endmodule

module retained_probe_ram #(parameter WIDTH=64, DEPTH=20480, AW=15, AREA=0, BANKED=0)
 (input [1:0] clk_i,v_i,w_i
  ,input [1:0][AW-1:0] addr_i
  ,input [1:0][WIDTH-1:0] data_i
  ,output [1:0][WIDTH-1:0] data_o);
  if (!BANKED) begin : flat
    if (AREA) begin : area_mapping
      (* ram_style="block", ram_decomp="area" *) logic [WIDTH-1:0] mem [DEPTH];
      for (genvar p=0;p<2;p++) begin : port_rw
        logic [WIDTH-1:0] q;
        assign data_o[p]=q;
        always @(posedge clk_i[p]) if(v_i[p]) begin
          if(w_i[p]) mem[addr_i[p]]<=data_i[p];
          q<=mem[addr_i[p]];
        end
      end
    end else begin : native_mapping
      (* ram_style="block" *) logic [WIDTH-1:0] mem [DEPTH];
      for (genvar p=0;p<2;p++) begin : port_rw
        logic [WIDTH-1:0] q;
        assign data_o[p]=q;
        always @(posedge clk_i[p]) if(v_i[p]) begin
          if(w_i[p]) mem[addr_i[p]]<=data_i[p];
          q<=mem[addr_i[p]];
        end
      end
    end
  end else begin : banks
    localparam N=(DEPTH+1023)/1024;
    localparam BW=(N>1)?$clog2(N):1;
    logic [1:0][N-1:0][WIDTH-1:0] q;
    logic [1:0][BW-1:0] selected_r;
    for(genvar p=0;p<2;p++) begin : select_port
      always @(posedge clk_i[p]) if(v_i[p]) selected_r[p]<=BW'(addr_i[p]>>10);
      assign data_o[p]=q[p][selected_r[p]];
    end
    for(genvar b=0;b<N;b++) begin : bank
      localparam D=(DEPTH-b*1024>=1024)?1024:DEPTH-b*1024;
      (* ram_style="block" *) logic [WIDTH-1:0] mem [D];
      for(genvar p=0;p<2;p++) begin : port_rw
        always @(posedge clk_i[p]) if(v_i[p] && (addr_i[p]>>10)==b) begin
          if(w_i[p]) mem[addr_i[p][9:0]]<=data_i[p];
          q[p][b]<=mem[addr_i[p][9:0]];
        end
      end
    end
  end
endmodule
