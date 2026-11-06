// Literal maximum-size APB map: grid rows stride 0x60, columns stride 0x20;
// shared starts at 0x100 and tail stays at 0x180 for every enable setting.
module rdl_params_wrapper #(
    parameter int N_ROWS = 2,
    parameter int N_COLS = 3
) (
    input logic clk, rst,
    input logic PSEL, PENABLE, PWRITE,
    input logic [8:0] PADDR,
    input logic [31:0] PWDATA,
    input logic [2:0] PPROT,
    input logic [3:0] PSTRB,
    output logic PREADY, PSLVERR,
    output logic [31:0] PRDATA,
    output logic [31:0] configured_rows, configured_columns,
    output logic [8:0] child_psel, child_penable, child_pwrite,
    output logic [3:0] child_addr [9],
    output logic [31:0] child_wdata [9],
    output logic [2:0] child_prot [9],
    output logic [3:0] child_strb [9],
    output logic [31:0] child_reads [9], child_writes [9],
    output logic [31:0] child_memory [9][3]
);
    logic grid_psel [2][3], grid_penable [2][3], grid_pwrite [2][3];
    logic [3:0] grid_addr [2][3], grid_strb [2][3];
    logic [2:0] grid_prot [2][3];
    logic [31:0] grid_wdata [2][3], grid_rdata [2][3];
    logic grid_error [2][3];
    logic shared_psel [2], shared_penable [2], shared_pwrite [2];
    logic [3:0] shared_addr [2], shared_strb [2];
    logic [2:0] shared_prot [2];
    logic [31:0] shared_wdata [2], shared_rdata [2];
    logic shared_error [2];
    logic [31:0] child_rdata [9];

    assign configured_rows = N_ROWS;
    assign configured_columns = N_COLS;

    // These are generated-module SV overrides, not reduced RDL elaborations.
    rdl_params_t #(.N_ROWS(N_ROWS), .N_COLS(N_COLS)) dut (
        .clk(clk), .rst(rst),
        .s_apb_PSEL(PSEL), .s_apb_PENABLE(PENABLE), .s_apb_PWRITE(PWRITE),
        .s_apb_PADDR(PADDR), .s_apb_PWDATA(PWDATA),
        .s_apb_PPROT(PPROT), .s_apb_PSTRB(PSTRB),
        .s_apb_PREADY(PREADY), .s_apb_PSLVERR(PSLVERR), .s_apb_PRDATA(PRDATA),
        .m_apb_grid_PSEL(grid_psel), .m_apb_grid_PENABLE(grid_penable),
        .m_apb_grid_PWRITE(grid_pwrite), .m_apb_grid_PADDR(grid_addr),
        .m_apb_grid_PWDATA(grid_wdata), .m_apb_grid_PPROT(grid_prot),
        .m_apb_grid_PSTRB(grid_strb), .m_apb_grid_PREADY(grid_penable),
        .m_apb_grid_PSLVERR(grid_error), .m_apb_grid_PRDATA(grid_rdata),
        .m_apb_shared_PSEL(shared_psel), .m_apb_shared_PENABLE(shared_penable),
        .m_apb_shared_PWRITE(shared_pwrite), .m_apb_shared_PADDR(shared_addr),
        .m_apb_shared_PWDATA(shared_wdata), .m_apb_shared_PPROT(shared_prot),
        .m_apb_shared_PSTRB(shared_strb), .m_apb_shared_PREADY(shared_penable),
        .m_apb_shared_PSLVERR(shared_error), .m_apb_shared_PRDATA(shared_rdata),
        .m_apb_tail_PSEL(child_psel[8]), .m_apb_tail_PENABLE(child_penable[8]),
        .m_apb_tail_PWRITE(child_pwrite[8]), .m_apb_tail_PADDR(child_addr[8]),
        .m_apb_tail_PWDATA(child_wdata[8]), .m_apb_tail_PPROT(child_prot[8]),
        .m_apb_tail_PSTRB(child_strb[8]), .m_apb_tail_PREADY(child_penable[8]),
        .m_apb_tail_PSLVERR(1'b0), .m_apb_tail_PRDATA(child_rdata[8])
    );

    // The public child arrays deliberately remain at their compiled maxima.
    for (genvar row = 0; row < 2; row++) begin : rows
        for (genvar col = 0; col < 3; col++) begin : columns
            localparam int ID = row * 3 + col;
            assign child_psel[ID] = grid_psel[row][col];
            assign child_penable[ID] = grid_penable[row][col];
            assign child_pwrite[ID] = grid_pwrite[row][col];
            assign child_addr[ID] = grid_addr[row][col];
            assign child_wdata[ID] = grid_wdata[row][col];
            assign child_prot[ID] = grid_prot[row][col];
            assign child_strb[ID] = grid_strb[row][col];
            assign grid_rdata[row][col] = child_rdata[ID];
            assign grid_error[row][col] = 1'b0;
        end
        assign child_psel[6 + row] = shared_psel[row];
        assign child_penable[6 + row] = shared_penable[row];
        assign child_pwrite[6 + row] = shared_pwrite[row];
        assign child_addr[6 + row] = shared_addr[row];
        assign child_wdata[6 + row] = shared_wdata[row];
        assign child_prot[6 + row] = shared_prot[row];
        assign child_strb[6 + row] = shared_strb[row];
        assign shared_rdata[row] = child_rdata[6 + row];
        assign shared_error[row] = 1'b0;
    end

    for (genvar child = 0; child < 9; child++) begin : responses
        // A read changes the next response; every child and word has its own state.
        assign child_rdata[child] = child_addr[child][3:2] < 2'd3
            ? child_memory[child][child_addr[child][3:2]] ^ (child_reads[child] << 16)
            : 32'hbad00000;
    end

    always_ff @(posedge clk) begin
        for (int child = 0; child < 9; child++) begin
            if (rst) begin
                child_reads[child] <= '0;
                child_writes[child] <= '0;
                for (int word = 0; word < 3; word++)
                    child_memory[child][word] <= 32'ha5000000 | (32'(child) << 12) | 32'(word * 4);
            end else if (child_psel[child] && child_penable[child]) begin
                // PREADY=PENABLE: this rising edge is the actual child handshake.
                assert (child_addr[child] <= 4'h8 && child_addr[child][1:0] == 2'b00)
                    else $fatal(1, "parameter child received an invalid local offset");
                if (child_pwrite[child]) begin
                    child_writes[child] <= child_writes[child] + 1'b1;
                    for (int lane = 0; lane < 4; lane++) begin
                        if (child_strb[child][lane])
                            child_memory[child][child_addr[child][3:2]][lane * 8 +: 8]
                                <= child_wdata[child][lane * 8 +: 8];
                    end
                end else begin
                    child_reads[child] <= child_reads[child] + 1'b1;
                end
            end
        end
    end
endmodule
