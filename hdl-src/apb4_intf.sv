interface apb4_intf #(
    parameter DATA_WIDTH = 32,
    parameter ADDR_WIDTH = 32
);
    // Clocking
    logic PCLK;
    logic PRESETn;

    // Command
    logic PSEL;
    logic PENABLE;
    logic PWRITE;
    logic [2:0] PPROT;
    logic [ADDR_WIDTH-1:0] PADDR;
    logic [DATA_WIDTH-1:0] PWDATA;
    logic [DATA_WIDTH/8-1:0] PSTRB;

    // Response
    logic [DATA_WIDTH-1:0] PRDATA;
    logic PREADY;
    logic PSLVERR;

    modport master (
        input PCLK,
        input PRESETn,

        output PSEL,
        output PENABLE,
        output PWRITE,
        output PPROT,
        output PADDR,
        output PWDATA,
        output PSTRB,

        input PRDATA,
        input PREADY,
        input PSLVERR
    );

    modport slave (
        input PCLK,
        input PRESETn,

        input PSEL,
        input PENABLE,
        input PWRITE,
        input PPROT,
        input PADDR,
        input PWDATA,
        input PSTRB,

        output PRDATA,
        output PREADY,
        output PSLVERR
    );
endinterface
