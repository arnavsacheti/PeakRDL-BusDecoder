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

    // Simple handshake sanity (one-cycle implication; relax/adjust as needed)
    assert_rd_resp_enc: assert property (@(posedge {{cpuif.signal("ACLK")}})
        {{cpuif.signal("RVALID")}} |-> (^{{cpuif.signal("RRESP")}} !== 1'bx))
            else $error("RRESP must be a legal AXI response when RVALID is high");

    assert_wr_resp_enc: assert property (@(posedge {{cpuif.signal("ACLK")}})
        {{cpuif.signal("BVALID")}} |-> (^{{cpuif.signal("BRESP")}} !== 1'bx))
            else $error("BRESP must be a legal AXI response when BVALID is high");
`endif
{% endif -%}


assign cpuif_req     = {{cpuif.signal("AWVALID")}} | {{cpuif.signal("ARVALID")}};
assign cpuif_wr_en   = {{cpuif.signal("AWVALID")}} & {{cpuif.signal("WVALID")}};
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
assign {{cpuif.signal("RVALID")}} = cpuif_rd_ack;
assign {{cpuif.signal("RRESP")}}  = (cpuif_rd_err | cpuif_rd_sel.cpuif_err | cpuif_wr_sel.cpuif_err) ? 2'b10 : 2'b00;

// Write: ack=BVALID, err=BRESP[1]
assign {{cpuif.signal("BVALID")}} = cpuif_wr_ack;
assign {{cpuif.signal("BRESP")}}  = (cpuif_wr_err | cpuif_wr_sel.cpuif_err | cpuif_rd_sel.cpuif_err) ? 2'b10 : 2'b00;

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