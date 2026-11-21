`timescale 1ns/1ps
module retained_line_store_tb;
  parameter int I_LINES = 93;
  parameter int D_LINES = 131;
  localparam int PA = 34;
  localparam int SETS = 64;
  logic clock;
  logic [1:0] clk, reset, clear, inv_v, lookup_v, lookup_ready;
  logic [1:0][PA-1:0] inv_addr, lookup_addr, insert_addr;
  logic [1:0] resp_v, resp_ready, resp_hit, insert_v, insert_ready;
  logic [1:0][511:0] resp_data, insert_data;
  logic [1:0] insert_replace, insert_cancel, insert_done, insert_published, unused_busy, epoch_wrap;
  logic [1:0][31:0] queries, responses, inserts, terminals, publications;
  initial clock = 1'b0;
  always #5 clock <= ~clock;
  assign clk = {~clock,clock};

  bp_retained_line_store
   #(.paddr_width_p(PA), .sets_p(SETS), .i_lines_p(I_LINES), .d_lines_p(D_LINES), .epoch_width_p(2)) dut
   (.clk_i(clk), .reset_i(reset), .clear_i(clear), .invalidate_v_i(inv_v), .invalidate_addr_i(inv_addr)
    ,.lookup_v_i(lookup_v), .lookup_ready_o(lookup_ready), .lookup_addr_i(lookup_addr)
    ,.resp_v_o(resp_v), .resp_ready_i(resp_ready), .resp_hit_o(resp_hit), .resp_data_o(resp_data)
    ,.insert_v_i(insert_v), .insert_ready_o(insert_ready), .insert_addr_i(insert_addr), .insert_data_i(insert_data)
    ,.insert_replace_i(insert_replace), .insert_cancel_i(insert_cancel), .insert_done_o(insert_done)
    ,.insert_published_o(insert_published), .busy_o(unused_busy), .epoch_wrap_o(epoch_wrap));

  for (genvar lane = 0; lane < 2; lane++) begin : monitor
    logic [31:0] q, r, i, t, p;
    assign queries[lane] = q; assign responses[lane] = r;
    assign inserts[lane] = i; assign terminals[lane] = t; assign publications[lane] = p;
    always @(posedge clk[lane]) begin
      if (reset[lane]) begin q <= 0; r <= 0; i <= 0; t <= 0; p <= 0; end
      else begin
        if (lookup_v[lane] && lookup_ready[lane]) q <= q+1;
        if (resp_v[lane] && resp_ready[lane]) begin
          assert (r < q) else $fatal(1,"response without outstanding lookup lane%0d",lane);
          r <= r+1;
        end
        if (insert_v[lane] && insert_ready[lane]) i <= i+1;
        if (insert_done[lane]) begin
          assert (t < i) else $fatal(1,"terminal without accepted insert lane%0d",lane);
          t <= t+1;
        end
        if (insert_published[lane]) p <= p+1;
        if (epoch_wrap[lane]) assert (!lookup_ready[lane]) else $fatal(1,"wrap did not block lookup");
      end
    end
  end

  function automatic logic [PA-1:0] address(input int lane, input int ordinal);
    return PA'('h01000000) + PA'(lane)*PA'('h00400000) + PA'(ordinal)*PA'(64);
  endfunction
  function automatic logic [511:0] payload(input logic [PA-1:0] addr, input int salt);
    logic [511:0] value;
    for (int word = 0; word < 8; word++)
      value[word*64+:64] = (64'h13579bdf02468ace ^ 64'(addr)) + 64'(word)*64'h1111111111111111 + 64'(salt);
    return value;
  endfunction
  task automatic step(input int lane);
    assert (lane >= 0 && lane < 2) else $fatal(1,"invalid test lane");
    @(negedge clk[lane]);
  endtask
  task automatic ready(input int lane);
    int count = 0;
    while (!lookup_ready[lane]) begin step(lane); count++;
      assert (count < I_LINES+D_LINES+200) else $fatal(1,"ready timeout lane%0d",lane);
    end
  endtask
  task automatic query_start(input int lane, input logic [PA-1:0] addr);
    step(lane); ready(lane); lookup_v[lane] = 1'b1; lookup_addr[lane] = addr;
    step(lane); lookup_v[lane] = 1'b0;
  endtask
  task automatic response(input int lane, input bit expect_hit, input logic [511:0] expect_data);
    int count = 0;
    while (!resp_v[lane]) begin step(lane); count++;
      assert (count < 200) else $fatal(1,"response timeout lane%0d",lane);
    end
    assert (resp_hit[lane] == expect_hit) else $fatal(1,"wrong response hit lane%0d",lane);
    if (expect_hit) assert (resp_data[lane] === expect_data) else $fatal(1,"wrong full64B payload lane%0d",lane);
    step(lane);
  endtask
  task automatic query(input int lane, input logic [PA-1:0] addr, input bit expect_hit, input int salt = 0);
    query_start(lane,addr); response(lane,expect_hit,payload(addr & ~PA'(63),salt));
  endtask
  task automatic insert_start(input int lane, input logic [PA-1:0] addr, input int salt = 0, input bit replace = 1);
    int count = 0;
    step(lane);
    while (!insert_ready[lane]) begin step(lane); count++;
      assert (count < I_LINES+D_LINES+200) else $fatal(1,"insert ready timeout lane%0d",lane);
    end
    insert_addr[lane] = addr; insert_data[lane] = payload(addr,salt);
    insert_replace[lane] = replace; insert_v[lane] = 1'b1;
    step(lane); insert_v[lane] = 1'b0;
  endtask
  task automatic terminal(input int lane, input bit published);
    int count = 0;
    while (!insert_done[lane]) begin step(lane); count++;
      assert (count < 200) else $fatal(1,"insert terminal timeout lane%0d",lane);
    end
    assert (insert_published[lane] == published) else $fatal(1,"wrong publication lane%0d",lane);
    step(lane);
  endtask
  task automatic put(input int lane, input logic [PA-1:0] addr, input int salt = 0, input bit replace = 1, input bit published = 1);
    insert_start(lane,addr,salt,replace); terminal(lane,published);
  endtask
  task automatic invalidate(input int lane, input logic [PA-1:0] addr);
    step(lane); inv_v[lane] = 1'b1; inv_addr[lane] = addr; step(lane); inv_v[lane] = 1'b0;
  endtask
  task automatic flush(input int lane);
    step(lane); clear[lane] = 1'b1; step(lane); clear[lane] = 1'b0; ready(lane);
  endtask
  task automatic capacity(input int lane, input int lines);
    ready(lane);
    if (lines == 0) begin
      query(lane,address(lane,0),0); put(lane,address(lane,0),0,1,0);
    end else begin
      query(lane,address(lane,0),0);
      for (int n = 0; n < lines; n++) put(lane,address(lane,n));
      for (int n = 0; n < lines; n++) query(lane,address(lane,n),1);
      // A full set refuses a new pinned line, then RR replaces exactly one.
      put(lane,address(lane,((lines+SETS-1)/SETS)*SETS),9,0,0);
      query(lane,address(lane,0),1);
      put(lane,address(lane,((lines+SETS-1)/SETS)*SETS),9);
      query(lane,address(lane,0),0);
      query(lane,address(lane,((lines+SETS-1)/SETS)*SETS),1,9);
      // Refreshing an existing physical tag is allowed in pinned mode.
      if (lines > 1) begin put(lane,address(lane,1),31,0); query(lane,address(lane,1),1,31); end
    end
    $display("RETAINED_CAPACITY_CHECK lane=%0d lines=%0d full64B=1",lane,lines);
  endtask

  initial begin
    $dumpfile("retained-line-store.fst"); $dumpvars(0,retained_line_store_tb);
    reset = '1; clear = 0; inv_v = 0; inv_addr = 0; lookup_v = 0; lookup_addr = 0;
    resp_ready = '1; insert_v = 0; insert_addr = 0; insert_data = 0;
    insert_replace = '1; insert_cancel = 0;
    repeat (8) step(0); reset = 0;
    fork capacity(0,I_LINES); capacity(1,D_LINES); join
    if (I_LINES >= SETS && D_LINES >= SETS) begin
      // Same physical address, simultaneous clocks/partitions, different data.
      fork put(0,PA'('h3000000),101); put(1,PA'('h3000000),202); join
      fork query(0,PA'('h3000000),1,101); query(1,PA'('h3000000),1,202); join
      // Indexed invalidation intentionally kills collateral same-set entries.
      flush(0); put(0,address(0,1));
      if (I_LINES > SETS+1) put(0,address(0,SETS+1));
      put(0,address(0,2)); invalidate(0,address(0,1)+PA'(7));
      query(0,address(0,1),0);
      if (I_LINES > SETS+1) query(0,address(0,SETS+1),0);
      query(0,address(0,2),1);
      // Kill a lookup after its synchronous payload-read pipeline starts.
      query_start(0,address(0,2));
      while (!dut.data_v[0]) step(0);
      inv_addr[0] = address(0,2); inv_v[0] = 1'b1;
      step(0); inv_v[0] = 0; response(0,0,'0);
      // A queued hit is revoked while response ready is low; ownership stays.
      put(0,address(0,3)); resp_ready[0] = 0; query_start(0,address(0,3));
      while (!resp_v[0]) step(0);
      assert (resp_hit[0]);
      repeat (3) begin step(0); assert (resp_v[0] && resp_hit[0]); end
      inv_addr[0] = address(0,3); inv_v[0] = 1;
      #1; assert (resp_v[0] && !resp_hit[0]);
      step(0); inv_v[0] = 0;
      repeat (2) begin step(0); assert (resp_v[0] && !resp_hit[0]); end
      resp_ready[0] = 1; response(0,0,'0);
      // Cancel an insert after a real payload write; partial line stays hidden.
      insert_start(0,address(0,4));
      while (!(dut.data_v[0] && dut.data_w[0])) step(0);
      step(0); insert_cancel[0] = 1; step(0); insert_cancel[0] = 0;
      terminal(0,0); query(0,address(0,4),0);
      // Store/coherence on the final write edge suppresses publication.
      insert_start(0,address(0,5));
      while (!(dut.data_v[0] && dut.data_w[0] && (dut.data_addr[0][2:0] == 7))) step(0);
      inv_addr[0] = address(0,5); inv_v[0] = 1; step(0); inv_v[0] = 0;
      terminal(0,0); query(0,address(0,5),0);
      // Clear must return a miss, not lose an accepted lookup and hang UCE.
      put(0,address(0,6)); query_start(0,address(0,6));
      clear[0] = 1; step(0); clear[0] = 0; response(0,0,'0); ready(0);
      query(0,address(0,6),0);
      // Clear also cancels an accepted in-flight insertion.
      insert_start(0,address(0,7));
      while (!(dut.data_v[0] && dut.data_w[0])) step(0);
      clear[0] = 1; step(0); clear[0] = 0; terminal(0,0); ready(0);
      query(0,address(0,7),0);
      // Two-bit test epochs exercise real wrap: no stale epoch resurrection.
      flush(1); put(1,address(1,8)); put(1,address(1,9));
      repeat (3) invalidate(1,address(1,8));
      query(1,address(1,9),1);
      resp_ready[1] = 0; query_start(1,address(1,9));
      while (!resp_v[1]) step(1);
      assert (resp_hit[1]); inv_addr[1] = address(1,8); inv_v[1] = 1;
      #1; assert (!resp_hit[1]);
      step(1); assert (epoch_wrap[1]); inv_v[1] = 0;
      resp_ready[1] = 1; response(1,0,'0); ready(1);
      query(1,address(1,8),0); query(1,address(1,9),0);
      put(1,address(1,8),77); query(1,address(1,8),1,77);
    end
    repeat (4) step(0);
    for (int lane = 0; lane < 2; lane++) begin
      assert (queries[lane] == responses[lane]) else $fatal(1,"lost/extra lookup response lane%0d",lane);
      assert (inserts[lane] == terminals[lane]) else $fatal(1,"lost/extra insert terminal lane%0d",lane);
      $display("RETAINED_COUNTS lane=%0d queries=%0d responses=%0d inserts=%0d terminals=%0d published=%0d",
        lane,queries[lane],responses[lane],inserts[lane],terminals[lane],publications[lane]);
    end
    $display("RETAINED_LINE_STORE_PASS I=%0d D=%0d",I_LINES,D_LINES); $finish;
  end
  initial begin #50000000; $fatal(1,"standalone retained-store watchdog"); end
endmodule
