logic axi_wr_valid;
logic axi_wr_invalid;
logic cpuif_wr_ack_int;
logic cpuif_rd_ack_int;

assign axi_wr_valid = {{cpuif.signal("AWVALID")}} & {{cpuif.signal("WVALID")}};
assign axi_wr_invalid = {{cpuif.signal("AWVALID")}} ^ {{cpuif.signal("WVALID")}};

// Ready/acceptance follows the simplified single-beat requirement
assign {{cpuif.signal("AWREADY")}} = axi_wr_valid;
assign {{cpuif.signal("WREADY")}}  = axi_wr_valid;
assign {{cpuif.signal("ARREADY")}} = {{cpuif.signal("ARVALID")}};
assign cpuif_req     = {{cpuif.signal("AWVALID")}} | {{cpuif.signal("ARVALID")}};
assign cpuif_wr_en   = axi_wr_valid;
assign cpuif_rd_en   = {{cpuif.signal("ARVALID")}};

assign cpuif_wr_addr = {{cpuif.signal("AWADDR")}};
assign cpuif_rd_addr = {{cpuif.signal("ARADDR")}};

assign cpuif_wr_data    = {{cpuif.signal("WDATA")}};
assign cpuif_wr_byte_en = {{cpuif.signal("WSTRB")}};

//
// Return paths back to AXI master from generic cpuif_*
// Read: ack=RVALID, err=RRESP[1] (SLVERR/DECERR), data=RDATA
//
assign {{cpuif.signal("RDATA")}}  = cpuif_rd_data;
assign cpuif_rd_ack_int = cpuif_rd_ack | cpuif_rd_sel.cpuif_err;
assign {{cpuif.signal("RVALID")}} = cpuif_rd_ack_int;
assign {{cpuif.signal("RRESP")}}  = (cpuif_rd_err | cpuif_rd_sel.cpuif_err | cpuif_wr_sel.cpuif_err) ? 2'b10 : 2'b00;

// Write: ack=BVALID, err=BRESP[1]
assign cpuif_wr_ack_int = cpuif_wr_ack | cpuif_wr_sel.cpuif_err | axi_wr_invalid;
assign {{cpuif.signal("BVALID")}} = cpuif_wr_ack_int;
assign {{cpuif.signal("BRESP")}}  = (cpuif_wr_err | cpuif_wr_sel.cpuif_err | cpuif_rd_sel.cpuif_err | axi_wr_invalid) ? 2'b10 : 2'b00;

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
// Fanin CPU Bus interface signals
//--------------------------------------------------------------------------
{{fanin|walk(cpuif=cpuif)}}
