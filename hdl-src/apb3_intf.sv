interface apb3_intf #(
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
    logic [ADDR_WIDTH-1:0] PADDR;
    logic [DATA_WIDTH-1:0] PWDATA;

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
        output PADDR,
        output PWDATA,

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
        input PADDR,
        input PWDATA,

        output PRDATA,
        output PREADY,
        output PSLVERR
    );
endinterface
