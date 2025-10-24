//==========================================================
//  Package: {{ds.package_name}}
//  Description: CPU Interface Bus Decoder Package
//  Author: PeakRDL-BusDecoder
//  License: LGPL-3.0
//  Date: {{current_date}}
//  Version: {{version}}
//  Links:
//    - https://github.com/arnavsacheti/PeakRDL-BusDecoder
//==========================================================


package {{ds.package_name}};
    localparam {{ds.module_name.upper()}}_DATA_WIDTH = {{ds.cpuif_data_width}};
    localparam {{ds.module_name.upper()}}_MIN_ADDR_WIDTH = {{ds.addr_width}};
    localparam {{ds.module_name.upper()}}_SIZE = {{SVInt(ds.top_node.size)}};
endpackage
{# (eof newline anchor) #}
