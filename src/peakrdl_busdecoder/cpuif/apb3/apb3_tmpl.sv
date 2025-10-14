{%- if cpuif.is_interface -%}
`ifndef SYNTHESIS
    initial begin
        assert_bad_addr_width: assert($bits({{cpuif.signal("PADDR")}}) >= {{ds.package_name}}::{{ds.module_name|upper}}_MIN_ADDR_WIDTH)
            else $error("Interface address width of %0d is too small. Shall be at least %0d bits", $bits({{cpuif.signal("PADDR")}}), {{ds.package_name}}::{{ds.module_name|upper}}_MIN_ADDR_WIDTH);
        assert_bad_data_width: assert($bits({{cpuif.signal("PWDATA")}}) == {{ds.package_name}}::{{ds.module_name|upper}}_DATA_WIDTH)
            else $error("Interface data width of %0d is incorrect. Shall be %0d bits", $bits({{cpuif.signal("PWDATA")}}), {{ds.package_name}}::{{ds.module_name|upper}}_DATA_WIDTH);
    end
`endif
{% endif -%}

assign cpuif_req   = {{cpuif.signal("PSELx")}};
assign cpuif_wr_en = {{cpuif.signal("PWRITE")}};
assign cpuif_wr_data = {{cpuif.signal("PWDATA")}};
assign cpuif_rd_en = !{{cpuif.signal("PWRITE")}};

{%- for child in cpuif.addressable_children -%}
{%- if child is array -%}
for (genvar g_{{child.inst_name|lower}}_idx = 0; g_{{child.inst_name|lower}}_idx < N_{{child.inst_name|upper}}S; g_{{child.inst_name|lower}}_idx++) begin : g_passthrough_{{child.inst_name|lower}}
    assign {{cpuif.signal("PCLK", child, f"g_{child.inst_name.lower()}_idx")}}    = {{cpuif.signal("PCLK")}};
    assign {{cpuif.signal("PRESETn", child, f"g_{child.inst_name.lower()}_idx")}} = {{cpuif.signal("PRESETn")}};
    assign {{cpuif.signal("PSELx", child, f"g_{child.inst_name.lower()}_idx")}}    = (cpuif_wr_req[{{loop.indx}}] || cpuif_rd_req[{{loop.indx}}]) ? 1'b1 : 1'b0;
    assign {{cpuif.signal("PENABLE", child, f"g_{child.inst_name.lower()}_idx")}} = {{cpuif.signal("PENABLE")}};
    assign {{cpuif.signal("PWRITE", child, f"g_{child.inst_name.lower()}_idx")}}  = (cpuif_wr_req[{{loop.index}}]) ? 1'b1 : 1'b0;
    assign {{cpuif.signal("PADDR", child, f"g_{child.inst_name.lower()}_idx")}}   = {{cpuif.get_address_slice(cpuif_wr_addr, child)}};
    assign {{cpuif.signal("PWDATA", child, f"g_{child.inst_name.lower()}_idx")}}  = cpuif_wr_data;
    assign cpuif_rd_ack[loop.index] = {{cpuif.signal("PREADY", child)}};
    assign cpuif_rd_data[loop.index] = {{cpuif.signal("PRDATA", child)}};
    assign cpuif_rd_err[loop.index] = {{cpuif.signal("PSLVERR", child)}};
end
{%- else -%}
assign {{cpuif.signal("PCLK", child)}}    = {{cpuif.signal("PCLK")}};
assign {{cpuif.signal("PRESETn", child)}} = {{cpuif.signal("PRESETn")}};
assign {{cpuif.signal("PSELx", child)}}    = (cpuif_wr_sel[{{loop.index0}}] || cpuif_rd_sel[{{loop.index0}}]) ? 1'b1 : 1'b0;
assign {{cpuif.signal("PENABLE", child)}} = {{cpuif.signal("PENABLE")}};
assign {{cpuif.signal("PWRITE", child)}}  = (cpuif_wr_req[{{loop.index}}]) ? 1'b1 : 1'b0;
assign {{cpuif.signal("PADDR", child)}}   = {{cpuif.get_address_slice(cpuif_wr_addr, child)}};
assign {{cpuif.signal("PWDATA", child)}}  = cpuif_wr_data;
assign cpuif_rd_ack[loop.index] = {{cpuif.signal("PREADY", child)}};
assign cpuif_rd_data[loop.index] = {{cpuif.signal("PRDATA", child)}};
assign cpuif_rd_err[loop.index] = {{cpuif.signal("PSLVERR", child)}};
{%- endif -%}
{%- endfor -%}

always_comb begin
    {{cpuif.signal("PREADY")}} = 1'b0;
    {{cpuif.signal("PRDATA")}} = '0;
    {{cpuif.signal("PSLVERR")}} = 1'b0;

    for(int i = 0; i < {{cpuif.addressable_children | length}}; i++) begin
        if (cpuif_rd_sel[i]) begin
            {{cpuif.signal("PREADY")}} = cpuif_rd_ack[i];
            {{cpuif.signal("PRDATA")}} = cpuif_rd_data[i];
            {{cpuif.signal("PSLVERR")}} = cpuif_rd_err[i];
        end
    end
end