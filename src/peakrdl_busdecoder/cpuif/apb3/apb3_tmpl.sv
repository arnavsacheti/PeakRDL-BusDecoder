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

//======================================================
// Address Decode Logic
//======================================================
always_comb begin
    // Default all PSELx signals to 0
{%- for child in cpuif.addressable_children -%}
{%- if child is array -%}
    for (int {{child.inst_name|lower}}_idx = 0; {{child.inst_name|lower}}_idx < N_{{child.inst_name|upper}}S; {{child.inst_name|lower}}_idx++) begin
        {{self.signal("PSELx", child, f"{child.inst_name.lower()}_idx")}} = 1'b0;
    end
{%- else -%}
    {{self.signal("PSELx", child)}} = 1'b0;
{%- endif -%}
{%- endfor -%}

    if ({{self.signal("PSELx")}}) begin
{%- for child in cpuif.addressable_children -%}
{%- if loop.first -%}
        if ({{cpuif.get_address_decode_condition(child)}}) begin
{%- else -%}
        end else if ({{cpuif.get_address_decode_condition(child)}}) begin
{%- endif -%}
            // Address matched for {{child.inst_name}} 
{%- if child is array -%}
            for (genvar {{child.inst_name|lower}}_idx = 0; {{child.inst_name|lower}}_idx < N_{{child.inst_name|upper}}S; {{child.inst_name|lower}}_idx++) begin
                {{self.signal("PSELx", child, f"{child.inst_name.lower()}_idx")}} = 1'b1;
            end
{%- else -%}
            {{self.signal("PSELx", child)}} = 1'b1;
{%- endif -%} 
{%- if loop.last -%}
        end else begin
            // No address matched
{%- endif -%}
{%- endfor -%}
        end
    end else begin
        // PSELx is low, nothing to do
    end
end

//======================================================
// Read Data Mux
//======================================================
always_comb begin
    // Default read data to 0
    {{self.signal("PRDATA")}} = '0;
    {{self.signal("PREADY")}} = 1'b1;
    {{self.signal("PSLVERR")}} = 1'b0;

    if ({{self.signal("PSELx")}} && !{{self.signal("PWRITE")}} && {{self.signal("PENABLE")}}) begin
{%- for child in cpuif.addressable_children -%}
{%- if loop.first -%}
        if ({{cpuif.get_address_decode_condition(child)}}) begin
{%- else -%}
        end else if ({{cpuif.get_address_decode_condition(child)}}) begin
{%- endif -%}
            // Address matched for {{child.inst_name}} 
{%- if child is array -%}
            for (genvar {{child.inst_name|lower}}_idx = 0; {{child.inst_name|lower}}_idx < N_{{child.inst_name|upper}}S; {{child.inst_name|lower}}_idx++) begin
                {{self.signal("PRDATA")}} = {{self.signal("PRDATA", child, f"{child.inst_name.lower()}_idx")}};
                {{self.signal("PREADY")}} = {{self.signal("PREADY", child, f"{child.inst_name.lower()}_idx")}};
                {{self.signal("PSLVERR")}} = {{self.signal("PSLVERR", child, f"{child.inst_name.lower()}_idx")}};
            end
{%- else -%}
            {{self.signal("PRDATA")}}  = {{self.signal("PRDATA", child)}};
            {{self.signal("PREADY")}}  = {{self.signal("PREADY", child)}};
            {{self.signal("PSLVERR")}} = {{self.signal("PSLVERR", child)}};
{%- endif -%} 
{%- if loop.last -%}
        end else begin
            // No address matched
            {{self.signal("PRDATA")}} = {'hdeadbeef}[{{ds.data_width - 1}}:0]; // Indicate error on no match
            {{self.signal("PSLVERR")}} = 1'b1; // Indicate error on no match
        end
{%- endif -%}
{%- endfor -%}
    end else begin
        // Not a read transfer, nothing to do
    end
end