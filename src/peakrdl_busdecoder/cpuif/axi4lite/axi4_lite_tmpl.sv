{%- if cpuif.is_interface -%}
`ifndef SYNTHESIS
    initial begin
        // Width checks (AXI4-Lite)
        assert_bad_awaddr_width: assert($bits({{cpuif.signal("AWADDR")}}) >= {{ds.package_name}}::{{ds.module_name|upper}}_MIN_ADDR_WIDTH)
            else $error("AWADDR width %0d < MIN_ADDR_WIDTH %0d",
                        $bits({{cpuif.signal("AWADDR")}}), {{ds.package_name}}::{{ds.module_name|upper}}_MIN_ADDR_WIDTH);

        assert_bad_araddr_width: assert($bits({{cpuif.signal("ARADDR")}}) >= {{ds.package_name}}::{{ds.module_name|upper}}_MIN_ADDR_WIDTH)
            else $error("ARADDR width %0d < MIN_ADDR_WIDTH %0d",
                        $bits({{cpuif.signal("ARADDR")}}), {{ds.package_name}}::{{ds.module_name|upper}}_MIN_ADDR_WIDTH);

        assert_bad_data_width: assert($bits({{cpuif.signal("WDATA")}}) == {{ds.package_name}}::{{ds.module_name|upper}}_DATA_WIDTH)
            else $error("WDATA width %0d != DATA_WIDTH %0d",
                        $bits({{cpuif.signal("WDATA")}}), {{ds.package_name}}::{{ds.module_name|upper}}_DATA_WIDTH);
    end

    assert_rd_resp_enc: assert property (@(posedge {{cpuif.clock_signal}})
        {{cpuif.signal("RVALID")}} |-> (^{{cpuif.signal("RRESP")}} !== 1'bx))
            else $error("RRESP must be known when RVALID is high");

    assert_wr_resp_enc: assert property (@(posedge {{cpuif.clock_signal}})
        {{cpuif.signal("BVALID")}} |-> (^{{cpuif.signal("BRESP")}} !== 1'bx))
            else $error("BRESP must be known when BVALID is high");
`endif
{% endif -%}

localparam int AXIL_PTR_WIDTH =
    (AXI4LITE_MAX_OUTSTANDING <= 1) ? 1 : $clog2(AXI4LITE_MAX_OUTSTANDING);
localparam int AXIL_COUNT_WIDTH = $clog2(AXI4LITE_MAX_OUTSTANDING + 1);

function automatic logic [AXIL_PTR_WIDTH-1:0] axil_next_ptr(
    input logic [AXIL_PTR_WIDTH-1:0] ptr
);
    if (ptr == AXIL_PTR_WIDTH'(AXI4LITE_MAX_OUTSTANDING - 1)) begin
        axil_next_ptr = '0;
    end else begin
        axil_next_ptr = ptr + 1'b1;
    end
endfunction

// AW and W are independent AXI channels. Each can be accepted first and is
// retained here until a complete write request can be enqueued.
logic aw_hold_valid;
logic [{{cpuif.addr_width-1}}:0] aw_hold_addr;
logic [2:0] aw_hold_prot;
logic w_hold_valid;
logic [{{cpuif.data_width-1}}:0] w_hold_data;
logic [{{cpuif.data_width//8-1}}:0] w_hold_strb;

// Write request/response order queue.
cpuif_sel_t axil_wr_dest_q [0:AXI4LITE_MAX_OUTSTANDING-1];
logic [{{cpuif.addr_width-1}}:0] axil_wr_addr_q [0:AXI4LITE_MAX_OUTSTANDING-1];
logic [2:0] axil_wr_prot_q [0:AXI4LITE_MAX_OUTSTANDING-1];
logic [{{cpuif.data_width-1}}:0] axil_wr_data_q [0:AXI4LITE_MAX_OUTSTANDING-1];
logic [{{cpuif.data_width//8-1}}:0] axil_wr_strb_q [0:AXI4LITE_MAX_OUTSTANDING-1];
logic axil_wr_issued_q [0:AXI4LITE_MAX_OUTSTANDING-1];
logic axil_wr_aw_sent_q [0:AXI4LITE_MAX_OUTSTANDING-1];
logic axil_wr_w_sent_q [0:AXI4LITE_MAX_OUTSTANDING-1];
logic [AXIL_PTR_WIDTH-1:0] axil_wr_head_ptr;
logic [AXIL_PTR_WIDTH-1:0] axil_wr_tail_ptr;
logic [AXIL_PTR_WIDTH-1:0] axil_wr_issue_ptr;
logic [AXIL_COUNT_WIDTH-1:0] axil_wr_count;
logic [AXIL_COUNT_WIDTH-1:0] axil_wr_issue_count;

// Read request/response order queue.
cpuif_sel_t axil_rd_dest_q [0:AXI4LITE_MAX_OUTSTANDING-1];
logic [{{cpuif.addr_width-1}}:0] axil_rd_addr_q [0:AXI4LITE_MAX_OUTSTANDING-1];
logic [2:0] axil_rd_prot_q [0:AXI4LITE_MAX_OUTSTANDING-1];
logic axil_rd_issued_q [0:AXI4LITE_MAX_OUTSTANDING-1];
logic [AXIL_PTR_WIDTH-1:0] axil_rd_head_ptr;
logic [AXIL_PTR_WIDTH-1:0] axil_rd_tail_ptr;
logic [AXIL_PTR_WIDTH-1:0] axil_rd_issue_ptr;
logic [AXIL_COUNT_WIDTH-1:0] axil_rd_count;
logic [AXIL_COUNT_WIDTH-1:0] axil_rd_issue_count;

// The issue selection and response-head selection are deliberately separate.
// A later request may be issued while only the oldest response is permitted
// to see READY.
cpuif_sel_t axil_wr_issue_sel;
cpuif_sel_t axil_rd_issue_sel;
cpuif_sel_t axil_wr_resp_sel;
cpuif_sel_t axil_rd_resp_sel;

logic [{{cpuif.addr_width-1}}:0] axil_wr_issue_addr;
logic [2:0] axil_wr_issue_prot;
logic [{{cpuif.data_width-1}}:0] axil_wr_issue_data;
logic [{{cpuif.data_width//8-1}}:0] axil_wr_issue_strb;
logic axil_wr_issue_aw_sent;
logic axil_wr_issue_w_sent;
logic [{{cpuif.addr_width-1}}:0] axil_rd_issue_addr;
logic [2:0] axil_rd_issue_prot;

logic axil_wr_issue_aw_ready;
logic axil_wr_issue_w_ready;
logic axil_rd_issue_ar_ready;
logic [1:0] axil_wr_resp;
logic [1:0] axil_rd_resp;

wire axil_in_reset = {{cpuif.reset_asserted}};
wire axil_wr_queue_has_space =
    axil_wr_count < AXIL_COUNT_WIDTH'(AXI4LITE_MAX_OUTSTANDING);
wire axil_rd_queue_has_space =
    axil_rd_count < AXIL_COUNT_WIDTH'(AXI4LITE_MAX_OUTSTANDING);

assign {{cpuif.signal("AWREADY")}} =
    !axil_in_reset && !aw_hold_valid && axil_wr_queue_has_space;
assign {{cpuif.signal("WREADY")}} =
    !axil_in_reset && !w_hold_valid && axil_wr_queue_has_space;
assign {{cpuif.signal("ARREADY")}} = !axil_in_reset && axil_rd_queue_has_space;

wire axil_aw_capture = {{cpuif.signal("AWVALID")}} & {{cpuif.signal("AWREADY")}};
wire axil_w_capture = {{cpuif.signal("WVALID")}} & {{cpuif.signal("WREADY")}};
wire axil_wr_enqueue = aw_hold_valid & w_hold_valid & axil_wr_queue_has_space;
wire axil_rd_enqueue = {{cpuif.signal("ARVALID")}} & {{cpuif.signal("ARREADY")}};

// Feed the existing address decoder from the complete request being accepted
// into an order queue. Read and write decode can occur in the same cycle.
assign cpuif_req = axil_wr_enqueue | axil_rd_enqueue;
assign cpuif_wr_en = axil_wr_enqueue;
assign cpuif_rd_en = axil_rd_enqueue;
assign cpuif_wr_addr = aw_hold_addr;
assign cpuif_rd_addr = {{cpuif.signal("ARADDR")}};
assign cpuif_wr_data = w_hold_data;
assign cpuif_wr_byte_en = w_hold_strb;

always_comb begin
    axil_wr_issue_sel = '{default: '0};
    axil_wr_issue_addr = '0;
    axil_wr_issue_prot = '0;
    axil_wr_issue_data = '0;
    axil_wr_issue_strb = '0;
    axil_wr_issue_aw_sent = 1'b0;
    axil_wr_issue_w_sent = 1'b0;

    if (axil_wr_issue_count != '0) begin
        axil_wr_issue_sel = axil_wr_dest_q[axil_wr_issue_ptr];
        axil_wr_issue_addr = axil_wr_addr_q[axil_wr_issue_ptr];
        axil_wr_issue_prot = axil_wr_prot_q[axil_wr_issue_ptr];
        axil_wr_issue_data = axil_wr_data_q[axil_wr_issue_ptr];
        axil_wr_issue_strb = axil_wr_strb_q[axil_wr_issue_ptr];
        axil_wr_issue_aw_sent = axil_wr_aw_sent_q[axil_wr_issue_ptr];
        axil_wr_issue_w_sent = axil_wr_w_sent_q[axil_wr_issue_ptr];
    end
end

always_comb begin
    axil_rd_issue_sel = '{default: '0};
    axil_rd_issue_addr = '0;
    axil_rd_issue_prot = '0;

    if (axil_rd_issue_count != '0) begin
        axil_rd_issue_sel = axil_rd_dest_q[axil_rd_issue_ptr];
        axil_rd_issue_addr = axil_rd_addr_q[axil_rd_issue_ptr];
        axil_rd_issue_prot = axil_rd_prot_q[axil_rd_issue_ptr];
    end
end

always_comb begin
    axil_wr_resp_sel = '{default: '0};
    if ((axil_wr_count != '0) && axil_wr_issued_q[axil_wr_head_ptr]) begin
        axil_wr_resp_sel = axil_wr_dest_q[axil_wr_head_ptr];
    end
end

always_comb begin
    axil_rd_resp_sel = '{default: '0};
    if ((axil_rd_count != '0) && axil_rd_issued_q[axil_rd_head_ptr]) begin
        axil_rd_resp_sel = axil_rd_dest_q[axil_rd_head_ptr];
    end
end

//--------------------------------------------------------------------------
// Fanout CPU Bus interface signals
//--------------------------------------------------------------------------
{{fanout|walk(cpuif=cpuif)}}
{%- if cpuif.is_interface %}

//--------------------------------------------------------------------------
// Intermediate signals for interface array fanin
//--------------------------------------------------------------------------
{{fanin_intermediate|walk(cpuif=cpuif)}}
{%- endif %}

//--------------------------------------------------------------------------
// Request READY fanin
//--------------------------------------------------------------------------
{{ready_fanin|walk(cpuif=cpuif)}}

wire axil_wr_issue_valid =
    (axil_wr_issue_count != '0) && !axil_wr_issue_sel.cpuif_err;
wire axil_wr_issue_aw_fire =
    axil_wr_issue_valid && !axil_wr_issue_aw_sent && axil_wr_issue_aw_ready;
wire axil_wr_issue_w_fire =
    axil_wr_issue_valid && !axil_wr_issue_w_sent && axil_wr_issue_w_ready;
wire axil_wr_issue_advance =
    (axil_wr_issue_count != '0) &&
    (axil_wr_issue_sel.cpuif_err ||
     ((axil_wr_issue_aw_sent || axil_wr_issue_aw_fire) &&
      (axil_wr_issue_w_sent || axil_wr_issue_w_fire)));

wire axil_rd_issue_valid =
    (axil_rd_issue_count != '0) && !axil_rd_issue_sel.cpuif_err;
wire axil_rd_issue_advance =
    (axil_rd_issue_count != '0) &&
    (axil_rd_issue_sel.cpuif_err || axil_rd_issue_ar_ready);

//--------------------------------------------------------------------------
// Fanin CPU Bus interface signals
//--------------------------------------------------------------------------
{{fanin|walk(cpuif=cpuif)}}

assign {{cpuif.signal("BVALID")}} =
    (axil_wr_count != '0) && axil_wr_issued_q[axil_wr_head_ptr] && cpuif_wr_ack;
assign {{cpuif.signal("BRESP")}} = axil_wr_resp;
assign {{cpuif.signal("RVALID")}} =
    (axil_rd_count != '0) && axil_rd_issued_q[axil_rd_head_ptr] && cpuif_rd_ack;
assign {{cpuif.signal("RDATA")}} = cpuif_rd_data;
assign {{cpuif.signal("RRESP")}} = axil_rd_resp;

wire axil_wr_dequeue = {{cpuif.signal("BVALID")}} & {{cpuif.signal("BREADY")}};
wire axil_rd_dequeue = {{cpuif.signal("RVALID")}} & {{cpuif.signal("RREADY")}};

always_ff @(posedge {{cpuif.clock_signal}} or {{cpuif.reset_sensitivity}}) begin
    if ({{cpuif.reset_asserted}}) begin
        aw_hold_valid <= 1'b0;
        w_hold_valid <= 1'b0;
        axil_wr_head_ptr <= '0;
        axil_wr_tail_ptr <= '0;
        axil_wr_issue_ptr <= '0;
        axil_wr_count <= '0;
        axil_wr_issue_count <= '0;
        axil_rd_head_ptr <= '0;
        axil_rd_tail_ptr <= '0;
        axil_rd_issue_ptr <= '0;
        axil_rd_count <= '0;
        axil_rd_issue_count <= '0;
    end else begin
        if (axil_aw_capture) begin
            aw_hold_valid <= 1'b1;
            aw_hold_addr <= {{cpuif.signal("AWADDR")}};
            aw_hold_prot <= {{cpuif.signal("AWPROT")}};
        end
        if (axil_w_capture) begin
            w_hold_valid <= 1'b1;
            w_hold_data <= {{cpuif.signal("WDATA")}};
            w_hold_strb <= {{cpuif.signal("WSTRB")}};
        end

        if (axil_wr_enqueue) begin
            aw_hold_valid <= 1'b0;
            w_hold_valid <= 1'b0;
            axil_wr_dest_q[axil_wr_tail_ptr] <= cpuif_wr_sel;
            axil_wr_addr_q[axil_wr_tail_ptr] <= aw_hold_addr;
            axil_wr_prot_q[axil_wr_tail_ptr] <= aw_hold_prot;
            axil_wr_data_q[axil_wr_tail_ptr] <= w_hold_data;
            axil_wr_strb_q[axil_wr_tail_ptr] <= w_hold_strb;
            axil_wr_issued_q[axil_wr_tail_ptr] <= cpuif_wr_sel.cpuif_err;
            axil_wr_aw_sent_q[axil_wr_tail_ptr] <= 1'b0;
            axil_wr_w_sent_q[axil_wr_tail_ptr] <= 1'b0;
            axil_wr_tail_ptr <= axil_next_ptr(axil_wr_tail_ptr);
        end

        if (axil_wr_issue_aw_fire) begin
            axil_wr_aw_sent_q[axil_wr_issue_ptr] <= 1'b1;
        end
        if (axil_wr_issue_w_fire) begin
            axil_wr_w_sent_q[axil_wr_issue_ptr] <= 1'b1;
        end
        if (axil_wr_issue_advance) begin
            axil_wr_issued_q[axil_wr_issue_ptr] <= 1'b1;
            axil_wr_issue_ptr <= axil_next_ptr(axil_wr_issue_ptr);
        end
        if (axil_wr_dequeue) begin
            axil_wr_head_ptr <= axil_next_ptr(axil_wr_head_ptr);
        end

        case ({axil_wr_enqueue, axil_wr_dequeue})
            2'b10: axil_wr_count <= axil_wr_count + 1'b1;
            2'b01: axil_wr_count <= axil_wr_count - 1'b1;
            default: axil_wr_count <= axil_wr_count;
        endcase
        case ({axil_wr_enqueue, axil_wr_issue_advance})
            2'b10: axil_wr_issue_count <= axil_wr_issue_count + 1'b1;
            2'b01: axil_wr_issue_count <= axil_wr_issue_count - 1'b1;
            default: axil_wr_issue_count <= axil_wr_issue_count;
        endcase

        if (axil_rd_enqueue) begin
            axil_rd_dest_q[axil_rd_tail_ptr] <= cpuif_rd_sel;
            axil_rd_addr_q[axil_rd_tail_ptr] <= {{cpuif.signal("ARADDR")}};
            axil_rd_prot_q[axil_rd_tail_ptr] <= {{cpuif.signal("ARPROT")}};
            axil_rd_issued_q[axil_rd_tail_ptr] <= cpuif_rd_sel.cpuif_err;
            axil_rd_tail_ptr <= axil_next_ptr(axil_rd_tail_ptr);
        end
        if (axil_rd_issue_advance) begin
            axil_rd_issued_q[axil_rd_issue_ptr] <= 1'b1;
            axil_rd_issue_ptr <= axil_next_ptr(axil_rd_issue_ptr);
        end
        if (axil_rd_dequeue) begin
            axil_rd_head_ptr <= axil_next_ptr(axil_rd_head_ptr);
        end

        case ({axil_rd_enqueue, axil_rd_dequeue})
            2'b10: axil_rd_count <= axil_rd_count + 1'b1;
            2'b01: axil_rd_count <= axil_rd_count - 1'b1;
            default: axil_rd_count <= axil_rd_count;
        endcase
        case ({axil_rd_enqueue, axil_rd_issue_advance})
            2'b10: axil_rd_issue_count <= axil_rd_issue_count + 1'b1;
            2'b01: axil_rd_issue_count <= axil_rd_issue_count - 1'b1;
            default: axil_rd_issue_count <= axil_rd_issue_count;
        endcase
    end
end
