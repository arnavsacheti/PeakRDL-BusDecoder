assign cpuif_req   = {{cpuif.signal("PSEL")}};
assign cpuif_wr_en = {{cpuif.signal("PWRITE")}};
assign cpuif_rd_en = !{{cpuif.signal("PWRITE")}};

assign cpuif_wr_addr = {{cpuif.signal("PADDR")}};
assign cpuif_rd_addr = {{cpuif.signal("PADDR")}};

assign cpuif_wr_data = {{cpuif.signal("PWDATA")}};

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
