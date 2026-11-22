// Passive diagnostics only: no signal here can affect an AXI handshake.
module hp0_passive_read_timing_observer
  #(parameter int addr_width_p=32, id_width_p=6, cycle_width_p=32
    ,parameter int latency_width_p=16, count_width_p=16, sequence_width_p=32)
  (input logic clk_i, reset_i
   ,input logic arvalid_i, arready_i
   ,input logic [addr_width_p-1:0] araddr_i
   ,input logic [id_width_p-1:0] arid_i
   ,input logic [7:0] arlen_i
   ,input logic [2:0] arsize_i
   ,input logic [1:0] arburst_i
   ,input logic rvalid_i, rready_i, rlast_i
   ,input logic [id_width_p-1:0] rid_i
   ,input logic [1:0] rresp_i
   ,input logic awvalid_i, awready_i, wvalid_i, wready_i, wlast_i, bvalid_i, bready_i
   ,input logic freeze_i
   ,output logic frozen_o, freeze_pending_o, busy_o
   ,output logic [31:0] version_o, status_o, errors_o
   ,output logic [31:0] ar_count_o, ignored_ar_count_o, record_total_o
   ,output logic [15:0] read_outstanding_o, aw_outstanding_o, w_outstanding_o
   ,output logic [4:0] record_count_o, valid_count_o
   ,output logic [3:0] write_pointer_o
   ,input logic rd_v_i
   ,input logic [6:0] rd_index_i
   ,output logic rd_ready_o, rd_resp_v_o
   ,input logic rd_resp_ready_i
   ,output logic [6:0] rd_resp_index_o
   ,output logic [31:0] rd_resp_data_o
   );
  localparam logic [15:0] f_overlap=16'h0001, f_rid=16'h0002, f_resp=16'h0004
    ,f_len=16'h0008, f_latency=16'h0010, f_beats=16'h0020, f_stall=16'h0040
    ,f_cycle_wrap=16'h0080, f_width=16'h0100, f_ledger=16'h0200
    ,f_write=16'h0400, f_write_error=16'h0800, f_after_freeze=16'h1000
    ,f_sequence=16'h2000;
  localparam logic [15:0] informational_lp=f_cycle_wrap|f_write;
  localparam int count_max_lp=(1<<count_width_p)-1;
  typedef struct packed {
    logic active;
    logic [addr_width_p-1:0] addr;
    logic [id_width_p-1:0] id;
    logic [7:0] len;
    logic [2:0] size;
    logic [1:0] burst, response_or;
    logic [cycle_width_p-1:0] cycle;
    logic [latency_width_p-1:0] age;
    logic [15:0] first_offer, first_accept, full_offer, full_accept;
    logic [3:0] seen;
    logic [count_width_p-1:0] beats, stalls, peak;
    logic [15:0] flags;
    logic [31:0] ar_sequence;
  } capture_s;
  capture_s cap_r, cap_n, completed;
  logic [cycle_width_p-1:0] cycle_r;
  logic cycle_wrapped_r;
  logic [count_width_p-1:0] reads_r, reads_n, aws_r, aws_n, ws_r, ws_n;
  logic partial_w_r, partial_w_n, read_poison_r, read_poison_n, write_poison_r, write_poison_n;
  logic freeze_pending_r, freeze_pending_n, frozen_r, frozen_n;
  logic [sequence_width_p-1:0] ar_count_r, ar_count_n, ignored_r, ignored_n, total_r, total_n;
  logic [31:0] errors_r, errors_n;
  logic [3:0] pointer_r;
  logic [4:0] occupied_r, valid_r;
  logic [15:0] quality_r;
  logic commit_v, commit_quality;
  logic [255:0] commit_data;
  // One synchronous wide record RAM. Reset only invalidates its small index;
  // payload is neither reset nor read before freeze settles a final write.
  (* ram_style="block" *) logic [255:0] record_mem [16];
  logic [255:0] read_q;
  logic [6:0] read_index_r;
  logic read_pending_r, response_v_r, read_present_r;
  logic [31:0] response_data_r;
  logic [6:0] response_index_r;
  wire ar_fire=arvalid_i&&arready_i;
  wire r_fire=rvalid_i&&rready_i;
  wire last_fire=r_fire&&rlast_i;
  wire aw_fire=awvalid_i&&awready_i;
  wire w_fire=wvalid_i&&wready_i;
  wire wlast_fire=w_fire&&wlast_i;
  wire b_fire=bvalid_i&&bready_i;
  wire cycle_wrap=&cycle_r;
  wire freeze_block=freeze_i||freeze_pending_r||frozen_r;
  wire old_drains=last_fire&&(reads_r==1)&&!read_poison_r;
  wire eligible=ar_fire&&!freeze_block&&!read_poison_r&&((reads_r==0)||old_drains);
  wire write_activity=(aws_r!=0)||(ws_r!=0)||partial_w_r||aw_fire||w_fire||b_fire||write_poison_r;
  wire read_accept=rd_v_i&&rd_ready_o;
  logic read_error, write_error, sequence_error;
  integer signed read_sum, aw_sum, w_sum;
  logic [sequence_width_p:0] sequence_sum;

  function automatic [255:0] pack_record(input capture_s c, input logic quality);
    logic [31:0] metadata;
    logic unused_live_fields;
    begin
      // Active/age are live tracking state, deliberately absent from records.
      unused_live_fields=^{c.active,c.age};
      metadata='0;
      metadata[5:0]=6'(c.id); metadata[13:6]=c.len;
      metadata[16:14]=c.size; metadata[18:17]=c.burst; metadata[19]=quality;
      metadata[23:20]=c.seen; metadata[25:24]=c.response_or; metadata[31:28]=4'd1;
      return {c.ar_sequence,{16'(c.peak),c.flags},{16'(c.stalls),16'(c.beats)},metadata,
              {c.full_accept,c.full_offer},{c.first_accept,c.first_offer},32'(c.cycle),32'(c.addr)};
    end
  endfunction

  always_comb begin
    reads_n=reads_r;aws_n=aws_r;ws_n=ws_r;partial_w_n=partial_w_r;
    read_poison_n=read_poison_r;write_poison_n=write_poison_r;
    ar_count_n=ar_count_r;ignored_n=ignored_r;total_n=total_r;
    errors_n=errors_r;cap_n=cap_r;completed='0;
    freeze_pending_n=freeze_pending_r||freeze_i;frozen_n=frozen_r;
    commit_v=1'b0;commit_quality=1'b0;commit_data='0;
    read_error=1'b0;write_error=1'b0;sequence_error=1'b0;
    sequence_sum={1'b0,ar_count_r}+{{sequence_width_p{1'b0}},1'b1};
    read_sum=int'(reads_r)+int'(ar_fire)-int'(last_fire);
    aw_sum=int'(aws_r)+int'(aw_fire)-int'(b_fire);
    w_sum=int'(ws_r)+int'(wlast_fire)-int'(b_fire);
    if (read_sum<0 || (rvalid_i&&(reads_r==0)&&!ar_fire)) begin
      errors_n[0]=1'b1;read_poison_n=1'b1;read_error=1'b1;
    end
    if (read_sum>count_max_lp) begin
      errors_n[1]=1'b1;read_poison_n=1'b1;read_error=1'b1;
    end
    reads_n=(read_sum<0)?'0:(read_sum>count_max_lp)?'1:count_width_p'(read_sum);
    if ((aw_sum<0)||(w_sum<0)) begin
      errors_n[2]=1'b1;write_poison_n=1'b1;write_error=1'b1;
    end
    if ((aw_sum>count_max_lp)||(w_sum>count_max_lp)) begin
      errors_n[3]=1'b1;write_poison_n=1'b1;write_error=1'b1;
    end
    aws_n=(aw_sum<0)?'0:(aw_sum>count_max_lp)?'1:count_width_p'(aw_sum);
    ws_n=(w_sum<0)?'0:(w_sum>count_max_lp)?'1:count_width_p'(w_sum);
    if(w_fire)partial_w_n=!wlast_i;
    if(ar_fire) begin
      if(sequence_sum[sequence_width_p])begin errors_n[4]=1'b1;sequence_error=1'b1;end
      else ar_count_n=sequence_sum[sequence_width_p-1:0];
      if(!eligible) begin
        if(&ignored_r)begin errors_n[4]=1'b1;sequence_error=1'b1;end
        else ignored_n=ignored_r+1'b1;
      end
      if(freeze_block)errors_n[5]=1'b1;
    end
    if(rvalid_i&&rresp_i[1])errors_n[7]=1'b1;
    if(frozen_r&&(ar_fire||aw_fire||w_fire||b_fire||rvalid_i))errors_n[5]=1'b1;

    if(cap_r.active)begin
      if(&cap_r.age)cap_n.flags|=f_latency;
      else cap_n.age=cap_r.age+1'b1;
      if(cycle_wrap)cap_n.flags|=f_cycle_wrap;
      if(write_activity)cap_n.flags|=f_write;
      if(write_error||write_poison_r)cap_n.flags|=f_write_error;
      if(read_error||read_poison_r)cap_n.flags|=f_ledger;
      if(errors_r[4])cap_n.flags|=f_sequence;
      if(freeze_block&&ar_fire)cap_n.flags|=f_after_freeze;
      if(ar_fire&&!old_drains)cap_n.flags|=f_overlap;
      if(reads_n>cap_n.peak)cap_n.peak=reads_n;
      if(rvalid_i&&rresp_i[1])cap_n.flags|=f_resp;
      // Once there is overlap, responses cannot be attributed to this AR.
      // Preserve the invalid window through drain, without inventing latencies.
      if((cap_n.flags&f_overlap)==0)begin
        if(rvalid_i)begin
          cap_n.response_or|=rresp_i;
          if(rid_i!=cap_r.id)begin cap_n.flags|=f_rid;errors_n[6]=1'b1;end
          if(!cap_n.seen[0])begin cap_n.first_offer=16'(cap_n.age);cap_n.seen[0]=1'b1;end
          if(rlast_i&&!cap_n.seen[2])begin
            cap_n.full_offer=16'(cap_n.age);cap_n.seen[2]=1'b1;
            if(int'(cap_r.beats)+1!=int'(cap_r.len)+1)begin cap_n.flags|=f_len;errors_n[8]=1'b1;end
          end
          if(!rready_i)begin
            if(&cap_r.stalls)cap_n.flags|=f_stall;
            else cap_n.stalls=cap_r.stalls+1'b1;
          end
        end
        if(r_fire)begin
          if(!cap_n.seen[1])begin cap_n.first_accept=16'(cap_n.age);cap_n.seen[1]=1'b1;end
          if(&cap_r.beats)cap_n.flags|=f_beats;
          else cap_n.beats=cap_r.beats+1'b1;
          if(rlast_i)begin cap_n.full_accept=16'(cap_n.age);cap_n.seen[3]=1'b1;end
          if((int'(cap_r.beats)+1==int'(cap_r.len)+1)!=rlast_i || int'(cap_r.beats)+1>int'(cap_r.len)+1)begin
            cap_n.flags|=f_len;errors_n[8]=1'b1;
          end
        end
      end
      if(old_drains||read_error)begin completed=cap_n;completed.active=1'b0;commit_v=1'b1;cap_n.active=1'b0;end
    end

    // A completing old RLAST belongs to the old request. An AR on that edge
    // starts a fresh isolated window; its R beats can only start next cycle.
    if(eligible)begin
      cap_n='0;cap_n.active=1'b1;cap_n.addr=araddr_i;cap_n.id=arid_i;
      cap_n.len=arlen_i;cap_n.size=arsize_i;cap_n.burst=arburst_i;
      cap_n.cycle=cycle_r;cap_n.ar_sequence=32'(ar_count_n);cap_n.peak=count_width_p'(1);
      cap_n.first_offer='1;cap_n.first_accept='1;cap_n.full_offer='1;cap_n.full_accept='1;
      if((64'(araddr_i)>>32)!=0||(64'(arid_i)>>6)!=0)cap_n.flags|=f_width;
      if(write_activity)cap_n.flags|=f_write;
      if(write_error||write_poison_r)cap_n.flags|=f_write_error;
      if(read_error)cap_n.flags|=f_ledger;
      if(sequence_error||errors_r[4])cap_n.flags|=f_sequence;
      if(reads_r==0&&rvalid_i)begin
        cap_n.response_or=rresp_i;cap_n.first_offer=0;cap_n.seen[0]=1'b1;
        if(rid_i!=arid_i)begin cap_n.flags|=f_rid;errors_n[6]=1'b1;end
        if(rresp_i[1])cap_n.flags|=f_resp;
        if(rlast_i)begin cap_n.full_offer=0;cap_n.seen[2]=1'b1;
          if(arlen_i!=0)begin cap_n.flags|=f_len;errors_n[8]=1'b1;end
        end
        if(!rready_i)cap_n.stalls=count_width_p'(1);
        if(r_fire)begin
          cap_n.first_accept=0;cap_n.seen[1]=1'b1;cap_n.beats=count_width_p'(1);
          if(rlast_i)begin cap_n.full_accept=0;cap_n.seen[3]=1'b1;end
          if((arlen_i==0)!=rlast_i)begin cap_n.flags|=f_len;errors_n[8]=1'b1;end
        end
        if(last_fire)begin completed=cap_n;completed.active=1'b0;commit_v=1'b1;cap_n.active=1'b0;end
      end
    end
    if(commit_v)begin
      if(&total_r)begin completed.flags|=f_sequence;errors_n[4]=1'b1;end
      else total_n=total_r+1'b1;
      commit_quality=((completed.flags&~informational_lp)==0)&&(completed.seen==4'b1111)
                     &&(int'(completed.beats)==int'(completed.len)+1);
      commit_data=pack_record(completed,commit_quality);
    end
    // No read request is accepted until frozen_r is observed on a later edge.
    // In particular freeze+RLAST cannot expose the pre-write RAM contents.
    if(freeze_pending_n&&!frozen_r&&!commit_v&&!cap_n.active&&reads_n==0&&aws_n==0&&ws_n==0&&!partial_w_n&&!read_poison_n&&!write_poison_n)
      frozen_n=1'b1;
  end

  always_ff @(posedge clk_i)begin
    if(reset_i)begin
      cycle_r<='0;cycle_wrapped_r<=1'b0;reads_r<='0;aws_r<='0;ws_r<='0;partial_w_r<=1'b0;
      read_poison_r<=1'b0;write_poison_r<=1'b0;freeze_pending_r<=1'b0;frozen_r<=1'b0;
      ar_count_r<='0;ignored_r<='0;total_r<='0;errors_r<='0;cap_r<='0;
      pointer_r<='0;occupied_r<='0;valid_r<='0;quality_r<='0;
      read_pending_r<=1'b0;read_present_r<=1'b0;response_v_r<=1'b0;response_data_r<='0;response_index_r<='0;read_index_r<='0;
    end else begin
      cycle_r<=cycle_r+1'b1;if(cycle_wrap)cycle_wrapped_r<=1'b1;reads_r<=reads_n;aws_r<=aws_n;ws_r<=ws_n;partial_w_r<=partial_w_n;
      read_poison_r<=read_poison_n;write_poison_r<=write_poison_n;freeze_pending_r<=freeze_pending_n;frozen_r<=frozen_n;
      ar_count_r<=ar_count_n;ignored_r<=ignored_n;total_r<=total_n;errors_r<=errors_n;cap_r<=cap_n;
      if(commit_v&&!frozen_r)begin
        pointer_r<=pointer_r+1'b1;
        if(occupied_r<16)occupied_r<=occupied_r+1'b1;
        valid_r<=valid_r+5'(commit_quality)-5'(quality_r[pointer_r]);quality_r[pointer_r]<=commit_quality;
      end
      if(response_v_r&&rd_resp_ready_i)response_v_r<=1'b0;
      if(read_pending_r)begin
        response_data_r<=read_present_r?read_q[32*int'(read_index_r[2:0])+:32]:32'b0;response_index_r<=read_index_r;
        response_v_r<=1'b1;read_pending_r<=1'b0;
      end
      if(read_accept)begin read_pending_r<=1'b1;read_index_r<=rd_index_i;
        read_present_r<=(occupied_r==16)||(5'(rd_index_i[6:3])<occupied_r);end
    end
  end
  always_ff @(posedge clk_i)begin
    if(!reset_i&&commit_v&&!frozen_r)record_mem[pointer_r]<=commit_data;
    if(read_accept)read_q<=record_mem[rd_index_i[6:3]];
  end
  assign frozen_o=frozen_r;
  assign freeze_pending_o=freeze_pending_r;
  assign busy_o=cap_r.active||(reads_r!=0)||(aws_r!=0)||(ws_r!=0)||partial_w_r||read_poison_r||write_poison_r;
  assign rd_ready_o=frozen_r&&!reset_i&&!read_pending_r&&!response_v_r;
  assign rd_resp_v_o=response_v_r;
  assign rd_resp_index_o=response_index_r;
  assign rd_resp_data_o=response_data_r;
  assign ar_count_o=32'(ar_count_r);
  assign ignored_ar_count_o=32'(ignored_r);
  assign record_total_o=32'(total_r);
  assign read_outstanding_o=16'(reads_r);
  assign aw_outstanding_o=16'(aws_r);
  assign w_outstanding_o=16'(ws_r);
  assign record_count_o=occupied_r;
  assign valid_count_o=valid_r;
  assign write_pointer_o=pointer_r;
  assign errors_o=errors_r;
  assign version_o=32'h48503001;
  assign status_o={22'b0,cycle_wrapped_r,write_poison_r,read_poison_r,(occupied_r==16),partial_w_r,
                   response_v_r,read_pending_r,cap_r.active,freeze_pending_r,frozen_r};
  initial begin
    assert(addr_width_p>=1&&addr_width_p<=64&&id_width_p>=1&&id_width_p<=64);
    assert(cycle_width_p>=1&&cycle_width_p<=32&&latency_width_p>=1&&latency_width_p<=16);
    assert(count_width_p>=1&&count_width_p<=16&&sequence_width_p>=1&&sequence_width_p<=32);
  end
endmodule
