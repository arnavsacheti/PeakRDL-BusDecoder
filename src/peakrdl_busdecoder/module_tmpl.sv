
//==========================================================
//  Module: {{ds.module_name}}
//  Description: CPU Interface Bus Decoder
//  Author: PeakRDL-busdecoder
//  License: GLPLv3
//  Date: {{current_date}}
//  Version: {{version}}
//  Links:
//    - https://github.com/SystemRDL/PeakRDL-busdecoder
//==========================================================


module {{ds.module_name}}
    {%- if cpuif.parameters %} #(
        {{-cpuif.parameters|join(",\n")|indent(8)}}
    ) {%- endif %} (
        {{-cpuif.port_declaration|indent(8)}}
    );

    //--------------------------------------------------------------------------
    // CPU Bus interface logic
    //--------------------------------------------------------------------------
    logic cpuif_req;
    logic [{{cpuif.addr_width-1}}:0] cpuif_wr_addr;
    logic [{{cpuif.addr_width-1}}:0] cpuif_rd_addr;

    logic cpuif_wr_ack;
    logic cpuif_wr_err;
    logic [{{cpuif.data_width-1}}:0] cpuif_wr_data;
    logic [{{cpuif.data_width//8-1}}:0] cpuif_wr_byte_en;

    logic cpuif_rd_ack;
    logic cpuif_rd_err;
    logic [{{cpuif.data_width-1}}:0] cpuif_rd_data;

    //--------------------------------------------------------------------------
    // Child instance signals
    //--------------------------------------------------------------------------
    logic [{{cpuif.addressable_children | length}}-1:0] cpuif_wr_sel;
    logic [{{cpuif.addressable_children | length}}-1:0] cpuif_rd_sel;

    //--------------------------------------------------------------------------
    // Slave <-> Internal CPUIF <-> Master
    //--------------------------------------------------------------------------
    {{-cpuif.get_implementation()|indent}}

    //--------------------------------------------------------------------------
    // Write Address Decoder
    //--------------------------------------------------------------------------
    always_comb begin
        // Default all write select signals to 0
        cpuif_wr_sel = '0;

        if (cpuif_req && cpuif_wr_en) begin
            // A write request is pending
            {%- for child in cpuif.addressable_children -%}
            {%- if loop.first -%}
            if ({{cpuif.get_address_decode_condition(child)}}) begin
            {%- else -%}
            end else if ({{cpuif.get_address_decode_condition(child)}}) begin
            {%- endif -%}
                // Address matched for {{child.inst_name}} 
                cpuif_wr_sel[{{loop.index0}}] = 1'b1;
            {%- endfor -%}
            end else begin
                // No address match, all select signals remain 0
                cpuif_wr_err = 1'b1; // Indicate error on no match
            end
        end else begin
            // No write request, all select signals remain 0
        end
    end

    //--------------------------------------------------------------------------
    // Read Address Decoder
    //--------------------------------------------------------------------------
    always_comb begin
        // Default all read select signals to 0
        cpuif_rd_sel = '0;
        

        if (cpuif_req && !cpuif_wr_en) begin
            // A read request is pending
            {%- for child in cpuif.addressable_children -%}
            {%- if loop.first -%}
            if ({{cpuif.get_address_decode_condition(child)}}) begin
            {%- else -%}
            end else if ({{cpuif.get_address_decode_condition(child)}}) begin
            {%- endif -%}
                // Address matched for {{child.inst_name}} 
                cpuif_rd_sel[{{loop.index0}}] = 1'b1;
            {%- endfor -%}
            end else begin
                // No address match, all select signals remain 0
                cpuif_rd_err = 1'b1; // Indicate error on no match
            end
        end else begin
            // No read request, all select signals remain 0
        end
    end
endmodule
{# (eof newline anchor) #}
