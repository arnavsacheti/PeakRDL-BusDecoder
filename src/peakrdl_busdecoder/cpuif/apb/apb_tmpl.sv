{%- if cpuif.is_interface %}
`ifndef SYNTHESIS
    initial begin
        assert_bad_addr_width: assert($bits({{cpuif.signal("PADDR")}}) >= {{ds.package_name}}::{{ds.module_name|upper}}_MIN_ADDR_WIDTH)
            else $error("Interface address width of %0d is too small. Shall be at least %0d bits", $bits({{cpuif.signal("PADDR")}}), {{ds.package_name}}::{{ds.module_name|upper}}_MIN_ADDR_WIDTH);
        assert_bad_data_width: assert($bits({{cpuif.signal("PWDATA")}}) == {{ds.package_name}}::{{ds.module_name|upper}}_DATA_WIDTH)
            else $error("Interface data width of %0d is incorrect. Shall be %0d bits", $bits({{cpuif.signal("PWDATA")}}), {{ds.package_name}}::{{ds.module_name|upper}}_DATA_WIDTH);
    end
`endif
{%- endif %}
{%- if cpuif.has_apb_buffer %}

//--------------------------------------------------------------------------
// APB transaction buffer: one owned request and, optionally, retained response.
//--------------------------------------------------------------------------
typedef enum logic [1:0] {
    APB_IDLE,
{%- if cpuif.buffer_in %}
    APB_SETUP,
{%- endif %}
    APB_ACCESS{{"," if cpuif.buffer_out else ""}}
{%- if cpuif.buffer_out %}
    APB_RESPONSE
{%- endif %}
} apb_state_t;
apb_state_t apb_state;

logic apb_req_PSEL, apb_req_PENABLE;
{%- if cpuif.buffer_in %}
logic apb_req_PWRITE;
logic [{{cpuif.addr_width-1}}:0] apb_req_PADDR;
logic [{{cpuif.data_width-1}}:0] apb_req_PWDATA;
{%- if cpuif.has_pprot %}
logic [2:0] apb_req_PPROT;
{%- endif %}
{%- if cpuif.has_pstrb %}
logic [{{cpuif.data_width_bytes-1}}:0] apb_req_PSTRB;
{%- endif %}
{%- endif %}
logic [{{cpuif.data_width-1}}:0] apb_rsp_PRDATA;
logic apb_rsp_PREADY, apb_rsp_PSLVERR;
{%- if cpuif.buffer_out %}
logic [{{cpuif.data_width-1}}:0] apb_response_data;
logic apb_response_error;
{%- endif %}

// A fresh upstream SETUP rearms the buffer, including after reset. Output-only
// buffering forwards that SETUP directly; input buffering retains its payload
// and emits a separate downstream SETUP before advancing to ACCESS.
assign apb_req_PSEL = !rst && {{cpuif.upstream_signal("PSEL")}} &&
{%- if cpuif.buffer_in %}
    ((apb_state == APB_SETUP) || (apb_state == APB_ACCESS));
{%- else %}
    ((apb_state == APB_ACCESS) || ((apb_state == APB_IDLE) && !{{cpuif.upstream_signal("PENABLE")}}));
{%- endif %}
assign apb_req_PENABLE = !rst && (apb_state == APB_ACCESS) && {{cpuif.upstream_signal("PENABLE")}};
{%- if cpuif.buffer_out %}
assign {{cpuif.upstream_signal("PRDATA")}} = apb_response_data;
assign {{cpuif.upstream_signal("PSLVERR")}} = !rst && (apb_state == APB_RESPONSE) && apb_response_error;
assign {{cpuif.upstream_signal("PREADY")}} = !rst && (apb_state == APB_RESPONSE);
{%- else %}
assign {{cpuif.upstream_signal("PRDATA")}} = apb_rsp_PRDATA;
assign {{cpuif.upstream_signal("PSLVERR")}} = apb_rsp_PSLVERR;
assign {{cpuif.upstream_signal("PREADY")}} = apb_req_PSEL && apb_req_PENABLE && apb_rsp_PREADY;
{%- endif %}

always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
        apb_state <= APB_IDLE;
{%- if cpuif.buffer_in %}
{%- for signal in cpuif.buffered_request_names %}
        apb_req_{{signal}} <= '0;
{%- endfor %}
{%- endif %}
{%- if cpuif.buffer_out %}
        apb_response_data <= '0;
        apb_response_error <= 1'b0;
{%- endif %}
    end else begin
        case (apb_state)
            APB_IDLE: begin
                if ({{cpuif.upstream_signal("PSEL")}} && !{{cpuif.upstream_signal("PENABLE")}}) begin
{%- if cpuif.buffer_in %}
{%- for signal in cpuif.buffered_request_names %}
                    apb_req_{{signal}} <= {{cpuif.upstream_signal(signal)}};
{%- endfor %}
                    apb_state <= APB_SETUP;
{%- else %}
                    apb_state <= APB_ACCESS;
{%- endif %}
                end
            end
{%- if cpuif.buffer_in %}
            APB_SETUP: begin
                if ({{cpuif.upstream_signal("PSEL")}} && {{cpuif.upstream_signal("PENABLE")}})
                    apb_state <= APB_ACCESS;
            end
{%- endif %}
            APB_ACCESS: begin
                if (apb_req_PSEL && apb_req_PENABLE && apb_rsp_PREADY) begin
{%- if cpuif.buffer_out %}
                    // Retire the child now, not when upstream later accepts.
                    apb_response_data <= apb_rsp_PRDATA;
                    apb_response_error <= apb_rsp_PSLVERR;
                    apb_state <= APB_RESPONSE;
{%- else %}
                    // With no response stage both interfaces complete together.
                    apb_state <= APB_IDLE;
{%- endif %}
                end
            end
{%- if cpuif.buffer_out %}
            APB_RESPONSE: begin
                if ({{cpuif.upstream_signal("PSEL")}} && {{cpuif.upstream_signal("PENABLE")}})
                    apb_state <= APB_IDLE;
            end
{%- endif %}
            default: apb_state <= APB_IDLE;
        endcase
    end
end
{%- endif %}

assign cpuif_req   = {{cpuif.signal("PSEL")}};
assign cpuif_wr_en = {{cpuif.signal("PWRITE")}};
assign cpuif_rd_en = !{{cpuif.signal("PWRITE")}};

assign cpuif_wr_addr = {{cpuif.signal("PADDR")}};
assign cpuif_rd_addr = {{cpuif.signal("PADDR")}};

assign cpuif_wr_data = {{cpuif.signal("PWDATA")}};
{%- if cpuif.has_pstrb %}
assign cpuif_wr_byte_en = {{cpuif.signal("PSTRB")}};
{%- endif %}

assign {{cpuif.signal("PRDATA")}} = cpuif_rd_data;
assign {{cpuif.signal("PREADY")}} = cpuif_rd_ack | cpuif_wr_ack; 
assign {{cpuif.signal("PSLVERR")}} = cpuif_rd_err | cpuif_wr_err;

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
