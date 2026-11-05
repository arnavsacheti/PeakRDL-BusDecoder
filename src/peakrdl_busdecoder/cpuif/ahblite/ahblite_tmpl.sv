// Address-phase decoding remains combinational. HREADY gates acceptance,
// not HSEL, so a following address can coexist with the pending data phase.
assign cpuif_req = {{cpuif.signal('HRESETn')}} && {{cpuif.signal('HSEL')}} && {{cpuif.signal('HTRANS')}}[1];
assign cpuif_wr_en = {{cpuif.signal('HWRITE')}};
assign cpuif_rd_en = !{{cpuif.signal('HWRITE')}};
assign cpuif_wr_addr = {{cpuif.signal('HADDR')}};
assign cpuif_rd_addr = {{cpuif.signal('HADDR')}};
assign cpuif_wr_data = {{cpuif.signal('HWDATA')}};
assign cpuif_wr_byte_en = '1;

logic [{{cpuif.target_count-1}}:0] ahb_addr_sel;
logic [{{cpuif.target_count-1}}:0] ahb_data_sel;
logic [{{cpuif.target_count-1}}:0] ahb_child_ready;
logic [{{cpuif.target_count-1}}:0] ahb_child_resp;
logic [{{cpuif.data_width-1}}:0] ahb_child_rdata [{{cpuif.target_count}}];
logic ahb_data_valid;
logic ahb_data_write;
logic ahb_data_error;
logic ahb_error_last;
logic ahb_readyout;
logic ahb_resp;
logic [{{cpuif.data_width-1}}:0] ahb_rdata;

// Constant-index bridges also make rolled SV-interface arrays legal: no
// procedural response mux ever indexes an interface instance dynamically.
{{cpuif.target_assignments}}
{{cpuif.interface_checks}}

always_ff @(posedge {{cpuif.signal('HCLK')}} or negedge {{cpuif.signal('HRESETn')}}) begin
    if (!{{cpuif.signal('HRESETn')}}) begin
        ahb_data_sel <= '0;
        ahb_data_valid <= 1'b0;
        ahb_data_write <= 1'b0;
        ahb_data_error <= 1'b0;
        ahb_error_last <= 1'b0;
    end else begin
        // The first local ERROR cycle deliberately forces HREADY low. Advance
        // its response phase independently, or the local default target stalls
        // forever. The retained destination still changes only on HREADY.
        if (ahb_data_valid && ahb_data_error && !ahb_error_last) begin
            ahb_error_last <= 1'b1;
        end
        if ({{cpuif.signal('HREADY')}}) begin
            ahb_data_sel <= ahb_addr_sel;
            ahb_data_valid <= cpuif_req;
            ahb_data_write <= {{cpuif.signal('HWRITE')}};
            ahb_data_error <= cpuif_req && !(|ahb_addr_sel);
            ahb_error_last <= 1'b0;
        end
    end
end

always_comb begin
    ahb_readyout = 1'b1;
    ahb_resp = 1'b0;
    ahb_rdata = '0;
    if ({{cpuif.signal('HRESETn')}} && ahb_data_valid) begin
        if (ahb_data_error) begin
            // Arm's two-cycle ERROR: not-ready/ERROR, then ready/ERROR.
            ahb_readyout = ahb_error_last;
            ahb_resp = 1'b1;
        end else begin
            for (int i = 0; i < {{cpuif.target_count}}; i++) begin
                if (ahb_data_sel[i]) begin
                    ahb_readyout = ahb_child_ready[i];
                    ahb_resp = ahb_child_resp[i];
                    ahb_rdata = ahb_child_rdata[i];
                end
            end
        end
    end
end

assign {{cpuif.signal('HREADYOUT')}} = ahb_readyout;
assign {{cpuif.signal('HRESP')}} = ahb_resp;
assign {{cpuif.signal('HRDATA')}} = ahb_rdata;

// Common response wires describe the held data phase, never the next address.
assign cpuif_wr_ack = ahb_data_valid && ahb_data_write && ahb_readyout;
assign cpuif_wr_err = ahb_data_valid && ahb_data_write && ahb_resp;
assign cpuif_rd_ack = ahb_data_valid && !ahb_data_write && ahb_readyout;
assign cpuif_rd_err = ahb_data_valid && !ahb_data_write && ahb_resp;
assign cpuif_rd_data = ahb_rdata;
