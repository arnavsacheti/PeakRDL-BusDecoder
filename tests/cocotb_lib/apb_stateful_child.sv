// Finite APB test peripheral. All architectural state changes on real handshakes.
module apb_stateful_child #(
    parameter int unsigned ID = 0
) (
    input  logic        clk,
    input  logic        resetn,
    input  logic        PSEL,
    input  logic        PENABLE,
    input  logic        PWRITE,
    input  logic [3:0]  PADDR,
    input  logic [31:0] PWDATA,
    input  logic [3:0]  PSTRB,
    output logic [31:0] PRDATA,
    output logic        PREADY,
    output logic        PSLVERR,
    output logic [31:0] completions,
    output logic [31:0] errors,
    output logic [31:0] read_effects,
    output logic [31:0] write_effects,
    output logic [31:0] memory0,
    output logic [31:0] memory1
);
    logic [31:0] ram [2];
    logic [2:0] elapsed;
    logic [2:0] wait_cycles;

    // Word 0 is zero-wait RAM; word 1 stalls for ID+1 ACCESS edges.
    // Word 2 returns the pre-handshake read-effect count. Word 3 errors
    // after one wait edge and must not change RAM or side-effect counts.
    always_comb begin
        case (PADDR[3:2])
            2'd1: wait_cycles = 3'(ID + 1);
            2'd3: wait_cycles = 3'd1;
            default: wait_cycles = 3'd0;
        endcase
        case (PADDR[3:2])
            2'd0: PRDATA = ram[0];
            2'd1: PRDATA = ram[1];
            2'd2: PRDATA = read_effects;
            default: PRDATA = 32'hbad00000 + ID;
        endcase
    end

    // PREADY may legally be high in SETUP or while this child is idle.
    assign PREADY = elapsed >= wait_cycles;
    assign PSLVERR = (PADDR[3:2] == 2'd3) && PREADY;
    assign memory0 = ram[0];
    assign memory1 = ram[1];

    always_ff @(posedge clk) begin
        if (!resetn) begin
            elapsed <= 0;
            completions <= 0;
            errors <= 0;
            read_effects <= 0;
            write_effects <= 0;
            ram[0] <= ID == 0 ? 32'h10203040 : 32'h90a0b0c0;
            ram[1] <= ID == 0 ? 32'h50607080 : 32'hd0e0f000;
        end else begin
            if (!PSEL || !PENABLE || PREADY)
                elapsed <= 0;
            else
                elapsed <= elapsed + 1'b1;

            if (PSEL && PENABLE && PREADY) begin
                completions <= completions + 1'b1;
                if (PSLVERR) begin
                    errors <= errors + 1'b1;
                end else if (PWRITE) begin
                    // A zero-strobe APB4 write is accepted but has no side effect.
                    if (|PSTRB) begin
                        write_effects <= write_effects + 1'b1;
                        if (PADDR[3:2] < 2) begin
                            for (int lane = 0; lane < 4; lane++) begin
                                if (PSTRB[lane])
                                    ram[PADDR[2]][lane*8 +: 8] <= PWDATA[lane*8 +: 8];
                            end
                        end
                    end
                end else begin
                    read_effects <= read_effects + 1'b1;
                end
            end
        end
    end
endmodule
