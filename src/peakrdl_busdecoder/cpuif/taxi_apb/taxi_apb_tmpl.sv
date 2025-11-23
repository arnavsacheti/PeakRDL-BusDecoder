{%- if cpuif.is_interface %}
`ifndef SYNTHESIS
    initial begin
        assert_bad_addr_width: assert($bits({{cpuif.signal("paddr")}}) >= {{ds.package_name}}::{{ds.module_name|upper}}_MIN_ADDR_WIDTH)
            else $error("Interface address width of %0d is too small. Shall be at least %0d bits", $bits({{cpuif.signal("paddr")}}), {{ds.package_name}}::{{ds.module_name|upper}}_MIN_ADDR_WIDTH);
        assert_bad_data_width: assert($bits({{cpuif.signal("pwdata")}}) == {{ds.package_name}}::{{ds.module_name|upper}}_DATA_WIDTH)
            else $error("Interface data width of %0d is incorrect. Shall be %0d bits", $bits({{cpuif.signal("pwdata")}}), {{ds.package_name}}::{{ds.module_name|upper}}_DATA_WIDTH);
    end
    `ifdef PEAKRDL_ASSERTIONS
    assert_wr_sel: assert property (@(posedge {{cpuif.signal("PCLK")}}) {{cpuif.signal("psel")}} && {{cpuif.signal("pwrite")}} |-> ##1 ({{cpuif.signal("pready")}} || {{cpuif.signal("pslverr")}}))
        else $error("APB4 Slave port SEL implies that cpuif_wr_sel must be one-hot encoded");
    `endif
`endif
{%- endif %}

assign cpuif_req   = {{cpuif.signal("psel")}};
assign cpuif_wr_en = {{cpuif.signal("pwrite")}};
assign cpuif_rd_en = !{{cpuif.signal("pwrite")}};

assign cpuif_wr_addr = {{cpuif.signal("paddr")}};
assign cpuif_rd_addr = {{cpuif.signal("paddr")}};

assign cpuif_wr_data = {{cpuif.signal("pwdata")}};
assign cpuif_wr_byte_en = {{cpuif.signal("pstrb")}};

assign {{cpuif.signal("prdata")}} = cpuif_rd_data;
assign {{cpuif.signal("pready")}} = cpuif_rd_ack;
assign {{cpuif.signal("pslverr")}} = cpuif_rd_err | cpuif_rd_sel.cpuif_err | cpuif_wr_sel.cpuif_err;

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