"""Pytest test runner for APB4 cocotb tests."""

import os
import tempfile
from pathlib import Path

import pytest

from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif

# Import the common test utilities
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from common.utils import compile_rdl_and_export


def generate_testbench_wrapper(top_name, slave_ports, tmpdir_path):
    """
    Generate a testbench wrapper that exposes interface signals.

    Args:
        top_name: Name of the top-level module
        slave_ports: List of slave port names
        tmpdir_path: Path to temporary directory

    Returns:
        Path to generated testbench file
    """
    tb_path = tmpdir_path / f"tb_{top_name}.sv"
    with open(tb_path, "w") as f:
        f.write(f"""
module tb_{top_name} (
    input logic clk,
    input logic rst
);
    // Instantiate APB4 interfaces
    apb4_intf #(
        .DATA_WIDTH(32),
        .ADDR_WIDTH(32)
    ) s_apb ();

""")
        # Create interface instances for each slave port
        for port in slave_ports:
            f.write(f"""
    apb4_intf #(
        .DATA_WIDTH(32),
        .ADDR_WIDTH(32)
    ) {port} ();
""")

        # Wire master signals
        f.write("""
    // Wire master signals from interface to top level for cocotb access
    logic s_apb_PSEL;
    logic s_apb_PENABLE;
    logic s_apb_PWRITE;
    logic [31:0] s_apb_PADDR;
    logic [31:0] s_apb_PWDATA;
    logic [3:0] s_apb_PSTRB;
    logic [2:0] s_apb_PPROT;
    logic [31:0] s_apb_PRDATA;
    logic s_apb_PREADY;
    logic s_apb_PSLVERR;

    assign s_apb.PSEL = s_apb_PSEL;
    assign s_apb.PENABLE = s_apb_PENABLE;
    assign s_apb.PWRITE = s_apb_PWRITE;
    assign s_apb.PADDR = s_apb_PADDR;
    assign s_apb.PWDATA = s_apb_PWDATA;
    assign s_apb.PSTRB = s_apb_PSTRB;
    assign s_apb.PPROT = s_apb_PPROT;
    assign s_apb_PRDATA = s_apb.PRDATA;
    assign s_apb_PREADY = s_apb.PREADY;
    assign s_apb_PSLVERR = s_apb.PSLVERR;

""")

        # Wire slave signals
        for port in slave_ports:
            f.write(f"""
    logic {port}_PSEL;
    logic {port}_PENABLE;
    logic {port}_PWRITE;
    logic [31:0] {port}_PADDR;
    logic [31:0] {port}_PWDATA;
    logic [3:0] {port}_PSTRB;
    logic [31:0] {port}_PRDATA;
    logic {port}_PREADY;
    logic {port}_PSLVERR;

    assign {port}_PSEL = {port}.PSEL;
    assign {port}_PENABLE = {port}.PENABLE;
    assign {port}_PWRITE = {port}.PWRITE;
    assign {port}_PADDR = {port}.PADDR;
    assign {port}_PWDATA = {port}.PWDATA;
    assign {port}_PSTRB = {port}.PSTRB;
    assign {port}.PRDATA = {port}_PRDATA;
    assign {port}.PREADY = {port}_PREADY;
    assign {port}.PSLVERR = {port}_PSLVERR;

""")

        # Instantiate DUT
        f.write(f"""
    // Instantiate DUT
    {top_name} dut (
        .s_apb(s_apb)""")

        for port in slave_ports:
            f.write(f",\n        .{port}({port})")

        f.write("""
    );

    // Dump waves
    initial begin
        $dumpfile("dump.vcd");
        $dumpvars(0, tb_{top_name});
    end
endmodule
""".format(top_name=top_name))

    return tb_path


@pytest.mark.skip(reason="Requires Icarus Verilog or other simulator to be installed")
def test_apb4_simple_register():
    """Test APB4 decoder with a simple register."""
    rdl_source = """
    addrmap simple_test {
        reg {
            field {
                sw=rw;
                hw=r;
            } data[31:0];
        } test_reg @ 0x0;
    };
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Compile RDL and export SystemVerilog
        module_path, package_path = compile_rdl_and_export(
            rdl_source, "simple_test", str(tmpdir_path), APB4Cpuif
        )

        # Generate testbench wrapper
        tb_path = generate_testbench_wrapper(
            "simple_test", ["m_apb_test_reg"], tmpdir_path
        )

        # Get HDL source directory
        hdl_src_dir = Path(__file__).parent.parent.parent.parent / "hdl-src"

        # Run simulation using cocotb.runner
        from cocotb.runner import get_runner

        runner = get_runner("icarus")
        runner.build(
            verilog_sources=[
                str(hdl_src_dir / "apb4_intf.sv"),
                str(package_path),
                str(module_path),
                str(tb_path),
            ],
            hdl_toplevel="tb_simple_test",
            always=True,
            build_dir=str(tmpdir_path / "sim_build"),
        )

        runner.test(
            hdl_toplevel="tb_simple_test",
            test_module="test_apb4_decoder",
            build_dir=str(tmpdir_path / "sim_build"),
        )


@pytest.mark.skip(reason="Requires Icarus Verilog or other simulator to be installed")
def test_apb4_multiple_registers():
    """Test APB4 decoder with multiple registers."""
    rdl_source = """
    addrmap multi_reg {
        reg {
            field {
                sw=rw;
                hw=r;
            } data[31:0];
        } reg1 @ 0x0;

        reg {
            field {
                sw=r;
                hw=w;
            } status[15:0];
        } reg2 @ 0x4;

        reg {
            field {
                sw=rw;
                hw=r;
            } control[7:0];
        } reg3 @ 0x8;
    };
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Compile RDL and export SystemVerilog
        module_path, package_path = compile_rdl_and_export(
            rdl_source, "multi_reg", str(tmpdir_path), APB4Cpuif
        )

        # Generate testbench wrapper
        tb_path = generate_testbench_wrapper(
            "multi_reg", ["m_apb_reg1", "m_apb_reg2", "m_apb_reg3"], tmpdir_path
        )

        # Get HDL source directory
        hdl_src_dir = Path(__file__).parent.parent.parent.parent / "hdl-src"

        # Run simulation
        from cocotb.runner import get_runner

        runner = get_runner("icarus")
        runner.build(
            verilog_sources=[
                str(hdl_src_dir / "apb4_intf.sv"),
                str(package_path),
                str(module_path),
                str(tb_path),
            ],
            hdl_toplevel="tb_multi_reg",
            always=True,
            build_dir=str(tmpdir_path / "sim_build"),
        )

        runner.test(
            hdl_toplevel="tb_multi_reg",
            test_module="test_apb4_decoder",
            test_args=["--test-case=test_multiple_registers"],
            build_dir=str(tmpdir_path / "sim_build"),
        )
