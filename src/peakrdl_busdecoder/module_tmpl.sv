//==========================================================
//  Module: {{ds.module_name}}
//  Description: CPU Interface Bus Decoder
//  Author: PeakRDL-BusDecoder
//  License: LGPL-3.0
//  Date: {{current_date}}
//  Version: {{version}}
//  Links:
//    - https://github.com/arnavsacheti/PeakRDL-BusDecoder
//==========================================================


module {{ds.module_name}}
{%- if cpuif.parameters %} #(
    {{cpuif.parameters|join(",\n")|indent(4)}}
) {%- endif %} (
    {{cpuif.port_declaration|indent(4)}}
);
    //--------------------------------------------------------------------------
    // CPU Bus interface logic
    //--------------------------------------------------------------------------
    logic cpuif_req;
    logic cpuif_wr_en;
    logic cpuif_rd_en;
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
    {{cpuif_select|walk|indent(4)}}
    cpuif_sel_t cpuif_wr_sel;
    cpuif_sel_t cpuif_rd_sel;

    //--------------------------------------------------------------------------
    // Slave <-> Internal CPUIF <-> Master
    //--------------------------------------------------------------------------
    {{cpuif.get_implementation()|indent(4)}}

    //--------------------------------------------------------------------------
    // Write Address Decoder
    //--------------------------------------------------------------------------
    always_comb begin
        // Default all write select signals to 0
        cpuif_wr_sel = '{default: '0};

        if (cpuif_req && cpuif_wr_en) begin
            // A write request is pending
            {{cpuif_decode|walk(flavor=cpuif_decode_flavor.WRITE)|indent(12)}}
        end else begin
            // No write request, all select signals remain 0
        end
    end

    //--------------------------------------------------------------------------
    // Read Address Decoder
    //--------------------------------------------------------------------------
    always_comb begin
        // Default all read select signals to 0
        cpuif_rd_sel = '{default: '0};

        if (cpuif_req && cpuif_rd_en) begin
            // A read request is pending
            {{cpuif_decode|walk(flavor=cpuif_decode_flavor.READ)|indent(12)}}
        end else begin
            // No read request, all select signals remain 0
        end
    end
endmodule
{# (eof newline anchor) #}
