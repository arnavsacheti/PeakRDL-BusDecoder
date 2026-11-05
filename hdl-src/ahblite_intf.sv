interface ahblite_intf #(
    parameter DATA_WIDTH = 32,
    parameter ADDR_WIDTH = 32
) (
    input logic HCLK,
    input logic HRESETn
);
    // Address-phase selection and the shared bus-ready feedback are separate
    // from this subordinate's data-phase HREADYOUT response.
    logic HSEL;
    logic HREADY;
    logic [ADDR_WIDTH-1:0] HADDR;
    logic [1:0] HTRANS;
    logic HWRITE;
    logic [2:0] HSIZE;
    logic [2:0] HBURST;
    logic [3:0] HPROT;
    logic HMASTLOCK;
    logic [DATA_WIDTH-1:0] HWDATA;

    logic [DATA_WIDTH-1:0] HRDATA;
    logic HREADYOUT;
    logic HRESP;

    modport master (
        input HCLK,
        input HRESETn,

        output HSEL,
        output HREADY,
        output HADDR,
        output HTRANS,
        output HWRITE,
        output HSIZE,
        output HBURST,
        output HPROT,
        output HMASTLOCK,
        output HWDATA,

        input HRDATA,
        input HREADYOUT,
        input HRESP
    );

    modport slave (
        input HCLK,
        input HRESETn,

        input HSEL,
        input HREADY,
        input HADDR,
        input HTRANS,
        input HWRITE,
        input HSIZE,
        input HBURST,
        input HPROT,
        input HMASTLOCK,
        input HWDATA,

        output HRDATA,
        output HREADYOUT,
        output HRESP
    );
endinterface
