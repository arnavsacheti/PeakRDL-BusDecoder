// Sparse, width-generic stress peripheral. The test driver never supplies PRDATA.
// Like apb_stateful_child, only real downstream ACCESS handshakes change state.
module apb_ram_child #(
    parameter int unsigned ADDR_WIDTH = 2,
    parameter int unsigned DATA_WIDTH = 32
) (
    input  logic                  clk,
    input  logic                  resetn,
    input  logic                  PSEL,
    input  logic                  PENABLE,
    input  logic                  PWRITE,
    input  logic [ADDR_WIDTH-1:0] PADDR,
    input  logic [DATA_WIDTH-1:0] PWDATA,
    input  logic [DATA_WIDTH/8-1:0] PSTRB,
    output logic [DATA_WIDTH-1:0] PRDATA,
    output logic                  PREADY,
    output logic                  PSLVERR,
    output logic [31:0]            completions,
    output logic [31:0]            writes,
    output logic [31:0]            reads
);
    // Associative storage keeps large sparse local address spaces inexpensive.
    logic [DATA_WIDTH-1:0] ram [bit [ADDR_WIDTH-1:0]];
    logic [DATA_WIDTH-1:0] merged;
    logic [1:0] elapsed;
    logic [1:0] wait_cycles;

    always_comb begin
        PRDATA = '0;
        if (ram.exists(PADDR) != 0)
            PRDATA = ram[PADDR];
        merged = PRDATA;
        for (int lane = 0; lane < DATA_WIDTH/8; lane++) begin
            if (PSTRB[lane])
                merged[lane*8 +: 8] = PWDATA[lane*8 +: 8];
        end
        // Fixed address-dependent stalls are independent of the request driver.
        wait_cycles = 2'(PADDR % 3);
    end
    assign PREADY = elapsed >= wait_cycles;
    assign PSLVERR = 1'b0;

    always @(posedge clk) begin
        if (!resetn) begin
            ram.delete();
            elapsed <= 0;
            completions <= 0;
            writes <= 0;
            reads <= 0;
        end else begin
            if (!PSEL || !PENABLE || PREADY)
                elapsed <= 0;
            else
                elapsed <= elapsed + 1'b1;
            if (PSEL && PENABLE && PREADY) begin
                completions <= completions + 1'b1;
                if (PWRITE) begin
                    writes <= writes + 1'b1;
                    // Dynamic testbench storage cannot use an NBA update.
                    if (|PSTRB)
                        ram[PADDR] = merged;
                end else begin
                    reads <= reads + 1'b1;
                end
            end
        end
    end
endmodule
