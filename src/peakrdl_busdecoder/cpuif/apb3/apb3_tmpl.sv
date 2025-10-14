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

//======================================================
// APB Fanout
//======================================================
{%- for child in cpuif.addressable_children -%}
{%- if child is array -%}
for (genvar g_{{child.inst_name|lower}}_idx = 0; g_{{child.inst_name|lower}}_idx < N_{{child.inst_name|upper}}S; g_{{child.inst_name|lower}}_idx++) begin : g_passthrough_{{child.inst_name|lower}}
    assign {{self.signal("PCLK", child, f"g_{child.inst_name.lower()}_idx")}}    = {{self.signal("PCLK")}};
    assign {{self.signal("PRESETn", child, f"g_{child.inst_name.lower()}_idx")}} = {{self.signal("PRESETn")}};
    assign {{self.signal("PENABLE", child, f"g_{child.inst_name.lower()}_idx")}} = {{self.signal("PENABLE")}};
    assign {{self.signal("PWRITE", child, f"g_{child.inst_name.lower()}_idx")}}  = {{self.signal("PWRITE")}};
    assign {{self.signal("PADDR", child, f"g_{child.inst_name.lower()}_idx")}}   = {{self.signal("PADDR")}} [{{child.addr_width - 1}}:0]; // FIXME: Check slicing
    assign {{self.signal("PWDATA", child, f"g_{child.inst_name.lower()}_idx")}}  = {{self.signal("PWDATA")}};
end
{%- else -%}
assign {{self.signal("PCLK", child)}}    = {{self.signal("PCLK")}};
assign {{self.signal("PRESETn", child)}} = {{self.signal("PRESETn")}};
assign {{self.signal("PENABLE", child)}} = {{self.signal("PENABLE")}};
assign {{self.signal("PWRITE", child)}}  = {{self.signal("PWRITE")}};
assign {{self.signal("PADDR", child)}}   = {{self.signal("PADDR")}} [{{child.addr_width - 1}}:0]; // FIXME: Check slicing
assign {{self.signal("PWDATA", child)}}  = {{self.signal("PWDATA")}};
{%- endif -%}
{%- endfor -%}