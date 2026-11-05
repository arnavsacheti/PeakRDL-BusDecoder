"""Clocked APB buffering regressions, not generated-source shape assertions.

The child models count side-effecting reads/writes on actual rising-edge APB
handshakes. A common standalone Verilator scoreboard exercises all four public
APB port forms, buffer modes, and optional payload gating. These finite temporal
checks are not an unbounded formal proof.
"""

from collections.abc import Callable
from pathlib import Path
import shutil
import subprocess

import pytest
from systemrdl import RDLCompileError
from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif import BaseCpuif
from peakrdl_busdecoder.cpuif.apb.apb_cpuif import (
    APB3Cpuif,
    APB3CpuifFlat,
    APB4Cpuif,
    APB4CpuifFlat,
)
from peakrdl_busdecoder.cpuif.axi4lite import AXI4LiteCpuif

_REPO = Path(__file__).resolve().parents[2]
_SCOREBOARD = Path(__file__).with_name("apb_buffer_scoreboard.cpp")
_EXPORTS = (
    pytest.param(False, False, APB3CpuifFlat, id="apb3-flat"),
    pytest.param(False, True, APB3Cpuif, id="apb3-interface"),
    pytest.param(True, False, APB4CpuifFlat, id="apb4-flat"),
    pytest.param(True, True, APB4Cpuif, id="apb4-interface"),
)


@pytest.fixture
def simple_top(compile_rdl: Callable[..., AddrmapNode]) -> AddrmapNode:
    return compile_rdl(
        """
        addrmap leaf {
            reg { field { sw=rw; hw=r; } data[31:0]; } first @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } last @ 0xfc;
        };
        addrmap top_t { leaf a @ 0x0; leaf b @ 0x1000; };
        """,
        top="top_t",
    )


def _wrapper(*, apb4: bool, interface: bool, clk_src: str) -> str:
    """Adapt public flat/interface ports to one independently described test ABI."""
    signals = {
        "PSEL": "",
        "PENABLE": "",
        "PWRITE": "",
        "PADDR": "[12:0] ",
        "PWDATA": "[31:0] ",
        "PRDATA": "[31:0] ",
        "PREADY": "",
        "PSLVERR": "",
    }
    if apb4:
        signals.update(PPROT="[2:0] ", PSTRB="[3:0] ")
    inputs = {"PSEL", "PENABLE", "PWRITE", "PADDR", "PWDATA", "PPROT", "PSTRB"}
    lines = [
        """module apb_buffer_wrapper (
    input logic clk, rst, clear_counts,
    input logic PSEL, PENABLE, PWRITE,
    input logic [12:0] PADDR,
    input logic [31:0] PWDATA,
    input logic [2:0] PPROT,
    input logic [3:0] PSTRB,
    input logic [3:0] wait_cycles [2],
    input logic ready_in_setup,
    input logic [1:0] inject_error,
    input logic [31:0] data_seed [2],
    output logic PREADY, PSLVERR,
    output logic [31:0] PRDATA,
    output logic [1:0] child_psel, child_penable, child_pwrite,
    output logic [7:0] child_addr [2],
    output logic [31:0] child_wdata [2], child_rdata [2],
    output logic [2:0] child_prot [2],
    output logic [3:0] child_strb [2],
    output logic [1:0] child_ready, child_error, child_clock, child_resetn,
    output logic [31:0] child_reads [2], child_writes [2],
    output logic [31:0] upstream_reads, upstream_writes,
    output logic phase_error, hold_error
);
    import top_t_pkg::*;
    logic [3:0] wait_age [2];
    logic [1:0] previous_sel, previous_enable, previous_ready;
    logic [47:0] previous_request [2];"""
    ]
    connections = [".clk(clk)", ".rst(rst)"] if clk_src == "design" else []
    kind = "apb4_intf" if apb4 else "apb3_intf"
    if interface:
        lines += [
            f"    {kind} #(.ADDR_WIDTH(13), .DATA_WIDTH(32)) upstream();",
            "    assign upstream.PCLK = clk;",
            "    assign upstream.PRESETn = ~rst;",
        ]
        connections.append(".s_apb(upstream)")
        for signal in signals:
            lhs, rhs = (f"upstream.{signal}", signal) if signal in inputs else (signal, f"upstream.{signal}")
            lines.append(f"    assign {lhs} = {rhs};")
    else:
        connections += [f".s_apb_{signal}({signal})" for signal in signals]
        if clk_src == "cpuif":
            connections += [".s_apb_PCLK(clk)", ".s_apb_PRESETn(~rst)"]

    child_outputs = {
        "PSEL": "child_psel",
        "PENABLE": "child_penable",
        "PWRITE": "child_pwrite",
        "PADDR": "child_addr",
        "PWDATA": "child_wdata",
        "PPROT": "child_prot",
        "PSTRB": "child_strb",
    }
    child_inputs = {"PREADY": "child_ready", "PRDATA": "child_rdata", "PSLVERR": "child_error"}
    for index, name in enumerate(("a", "b")):
        if interface:
            port = f"downstream_{name}"
            lines += [
                f"    {kind} #(.ADDR_WIDTH(8), .DATA_WIDTH(32)) {port}();",
                f"    assign {port}.PCLK = clk;",
                f"    assign {port}.PRESETn = ~rst;",
            ]
            connections.append(f".m_apb_{name}({port})")
            for signal in signals:
                if signal in child_outputs:
                    lines.append(f"    assign {child_outputs[signal]}[{index}] = {port}.{signal};")
                else:
                    lines.append(f"    assign {port}.{signal} = {child_inputs[signal]}[{index}];")
            lines += [
                f"    assign child_clock[{index}] = {port}.PCLK;",
                f"    assign child_resetn[{index}] = {port}.PRESETn;",
            ]
        else:
            for signal in signals:
                value = (child_outputs | child_inputs)[signal]
                connections.append(f".m_apb_{name}_{signal}({value}[{index}])")
            if clk_src == "cpuif":
                connections += [
                    f".m_apb_{name}_PCLK(child_clock[{index}])",
                    f".m_apb_{name}_PRESETn(child_resetn[{index}])",
                ]
            else:
                lines += [
                    f"    assign child_clock[{index}] = clk;",
                    f"    assign child_resetn[{index}] = ~rst;",
                ]
        if not apb4:
            lines += [f"    assign child_prot[{index}] = '0;", f"    assign child_strb[{index}] = '0;"]

    lines += [
        "    top_t dut (" + ", ".join(connections) + ");",
        """
    // With wait_cycles=0 and ready_in_setup=0 this is exactly PREADY=PENABLE.
    for (genvar i = 0; i < 2; i++) begin : children
        assign child_ready[i] = (ready_in_setup || child_penable[i]) && (wait_age[i] >= wait_cycles[i]);
        // Read side effects change both response fields immediately after completion.
        assign child_rdata[i] = data_seed[i] + (child_reads[i] << 8) + {24'b0, child_addr[i]};
        assign child_error[i] = inject_error[i] ^ child_reads[i][0];
        always_ff @(posedge clk or posedge rst) begin
            if (rst) wait_age[i] <= '0;
            else if (!child_psel[i] || !child_penable[i]) wait_age[i] <= '0;
            else if (!child_ready[i]) wait_age[i] <= wait_age[i] + 1'b1;
        end
    end
    // Side-effect counters intentionally survive router reset. Reset cannot undo
    // a child's completed write/read when its response has not reached upstream.
    always_ff @(posedge clk) begin
        if (clear_counts) begin
            upstream_reads <= '0;
            upstream_writes <= '0;
            for (int i = 0; i < 2; i++) begin
                child_reads[i] <= '0;
                child_writes[i] <= '0;
            end
        end else begin
            if (PSEL && PENABLE && PREADY) begin
                if (PWRITE) upstream_writes <= upstream_writes + 1;
                else upstream_reads <= upstream_reads + 1;
            end
            for (int i = 0; i < 2; i++) begin
                if (child_psel[i] && child_penable[i] && child_ready[i]) begin
                    if (child_pwrite[i]) child_writes[i] <= child_writes[i] + 1;
                    else child_reads[i] <= child_reads[i] + 1;
                end
            end
        end
    end
    always_ff @(posedge clk or posedge rst) begin
        if (rst) begin
            previous_sel <= '0;
            previous_enable <= '0;
            previous_ready <= '0;
            phase_error <= 1'b0;
            hold_error <= 1'b0;
            for (int i = 0; i < 2; i++) previous_request[i] <= '0;
        end else begin
            for (int i = 0; i < 2; i++) begin
                if (child_psel[i] && child_penable[i] &&
                    !(previous_sel[i] && (!previous_enable[i] || !previous_ready[i])))
                    phase_error <= 1'b1;
                if (previous_sel[i] && previous_enable[i] && !previous_ready[i] &&
                    (!child_psel[i] || !child_penable[i] || previous_request[i] !=
                     {child_pwrite[i], child_addr[i], child_wdata[i], child_prot[i], child_strb[i]}))
                    hold_error <= 1'b1;
                previous_request[i] <=
                    {child_pwrite[i], child_addr[i], child_wdata[i], child_prot[i], child_strb[i]};
            end
            previous_sel <= child_psel;
            previous_enable <= child_penable;
            previous_ready <= child_ready;
        end
    end
endmodule
""",
    ]
    return "\n".join(lines)


def _run(command: list[str], *, cwd: Path, timeout: int = 240) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    assert result.returncode == 0, f"Command failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}"
    return result


def _simulate(
    top: AddrmapNode,
    tmp_path: Path,
    *,
    apb4: bool,
    interface: bool,
    cpuif_cls: type[BaseCpuif],
    apb_buffer: str,
    gate_signals: bool,
    clk_src: str = "design",
) -> None:
    verilator = shutil.which("verilator")
    assert verilator is not None, "These behavioral APB regressions require Verilator"
    BusDecoderExporter().export(
        top,
        str(tmp_path),
        cpuif_cls=cpuif_cls,
        apb_buffer=apb_buffer,
        gate_signals=gate_signals,
        clk_src=clk_src,
        address_width=13,
    )
    wrapper = tmp_path / "apb_buffer_wrapper.sv"
    wrapper.write_text(_wrapper(apb4=apb4, interface=interface, clk_src=clk_src))
    sources = [tmp_path / "top_t_pkg.sv"]
    if interface:
        sources.append(_REPO / "hdl-src" / ("apb4_intf.sv" if apb4 else "apb3_intf.sv"))
    sources += [tmp_path / "top_t.sv", wrapper]
    _run(
        [
            verilator,
            "--cc",
            "--exe",
            "--build",
            "--assert",
            "-Wall",
            "-Wno-DECLFILENAME",
            "-Wno-UNUSEDPARAM",
            "-Wno-UNUSEDSIGNAL",
            "-Wno-GENUNNAMED",
            "--top-module",
            "apb_buffer_wrapper",
            "-Mdir",
            str(tmp_path / "obj_dir"),
            "-o",
            "sim",
            *(str(source) for source in sources),
            str(_SCOREBOARD),
        ],
        cwd=tmp_path,
    )
    result = _run(
        [
            str(tmp_path / "obj_dir" / "sim"),
            apb_buffer,
            str(int(apb4)),
            str(int(gate_signals)),
        ],
        cwd=tmp_path,
        timeout=30,
    )
    assert "APB_BUFFER_SUCCESS" in result.stdout


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize("apb4,interface,cpuif_cls", _EXPORTS)
@pytest.mark.parametrize("apb_buffer", ["none", "in", "out", "both"])
@pytest.mark.parametrize("gate_signals", [False, True], ids=["ungated", "gated"])
def test_apb_clocked_transfers(
    simple_top: AddrmapNode,
    tmp_path: Path,
    apb4: bool,
    interface: bool,
    cpuif_cls: type[BaseCpuif],
    apb_buffer: str,
    gate_signals: bool,
) -> None:
    _simulate(
        simple_top,
        tmp_path,
        apb4=apb4,
        interface=interface,
        cpuif_cls=cpuif_cls,
        apb_buffer=apb_buffer,
        gate_signals=gate_signals,
    )


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize("apb4,interface,cpuif_cls", _EXPORTS)
def test_unbuffered_cpuif_clock(
    simple_top: AddrmapNode,
    tmp_path: Path,
    apb4: bool,
    interface: bool,
    cpuif_cls: type[BaseCpuif],
) -> None:
    _simulate(
        simple_top,
        tmp_path,
        apb4=apb4,
        interface=interface,
        cpuif_cls=cpuif_cls,
        apb_buffer="none",
        gate_signals=True,
        clk_src="cpuif",
    )


def test_buffer_requires_clk_src_design(simple_top: AddrmapNode, tmp_path: Path) -> None:
    with pytest.raises(RDLCompileError, match="--apb-buffer requires --clk-src design"):
        BusDecoderExporter().export(
            simple_top,
            str(tmp_path),
            cpuif_cls=APB4CpuifFlat,
            apb_buffer="in",
            clk_src="cpuif",
        )


def test_buffer_rejected_on_non_apb_cpuif(simple_top: AddrmapNode, tmp_path: Path) -> None:
    with pytest.raises(RDLCompileError, match="choose an APB --cpuif"):
        BusDecoderExporter().export(simple_top, str(tmp_path), cpuif_cls=AXI4LiteCpuif, apb_buffer="in")


def test_invalid_apb_buffer_value(simple_top: AddrmapNode, tmp_path: Path) -> None:
    with pytest.raises(RDLCompileError, match="--apb-buffer must be one of"):
        BusDecoderExporter().export(simple_top, str(tmp_path), cpuif_cls=APB4CpuifFlat, apb_buffer="bogus")
