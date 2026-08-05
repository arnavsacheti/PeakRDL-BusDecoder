"""Focused generator checks for stateful AXI4-Lite response ordering."""

from collections.abc import Callable
from pathlib import Path

import pytest
from systemrdl import RDLCompileError
from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.axi4lite.axi4_lite_cpuif import AXI4LiteCpuif, AXI4LiteCpuifFlat
from peakrdl_busdecoder.design_state import DesignState


RDL = """
addrmap child {
    reg { field { sw=rw; hw=r; } value[31:0]; } data;
};
addrmap top {
    external child first @ 0x000;
    external child second @ 0x100;
};
"""


def test_stateful_order_queues_are_generated(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
) -> None:
    top = compile_rdl(RDL, top="top")
    exporter = BusDecoderExporter()
    exporter.export(
        top,
        str(tmp_path),
        cpuif_cls=AXI4LiteCpuifFlat,
        axi4lite_max_outstanding=7,
    )
    module = (tmp_path / "top.sv").read_text()

    assert "localparam AXI4LITE_MAX_OUTSTANDING = 7" in module
    assert "cpuif_sel_t axil_wr_dest_q [0:AXI4LITE_MAX_OUTSTANDING-1]" in module
    assert "cpuif_sel_t axil_rd_dest_q [0:AXI4LITE_MAX_OUTSTANDING-1]" in module
    assert "axil_wr_issue_ptr" in module
    assert "axil_wr_head_ptr" in module
    assert "axil_rd_issue_ptr" in module
    assert "axil_rd_head_ptr" in module

    # Response READY is selected from the response head, not from the request
    # currently being dispatched.
    assert "assign m_axil_first_BREADY = axil_wr_resp_sel.first & s_axil_BREADY;" in module
    assert "assign m_axil_second_RREADY = axil_rd_resp_sel.second & s_axil_RREADY;" in module
    assert "if (axil_wr_issue_sel.first)" in module
    assert "if (axil_rd_issue_sel.second)" in module
    assert "axil_wr_resp_sel.first" in module
    assert "axil_rd_resp_sel.second" in module


def test_outstanding_depth_must_be_positive(compile_rdl: Callable[..., AddrmapNode]) -> None:
    top = compile_rdl(RDL, top="top")
    with pytest.raises(RDLCompileError, match="greater than or equal to 1"):
        DesignState(top, {"axi4lite_max_outstanding": 0})


@pytest.mark.parametrize(
    ("cpuif_cls", "clock", "reset"),
    [
        (AXI4LiteCpuifFlat, "s_axil_ACLK", "s_axil_ARESETn"),
        (AXI4LiteCpuif, "s_axil.ACLK", "s_axil.ARESETn"),
    ],
)
def test_cpuif_clock_mode_uses_active_low_axi_reset(
    compile_rdl: Callable[..., AddrmapNode],
    tmp_path: Path,
    cpuif_cls: type,
    clock: str,
    reset: str,
) -> None:
    top = compile_rdl(RDL, top="top")
    output = tmp_path / cpuif_cls.__name__
    BusDecoderExporter().export(
        top,
        str(output),
        cpuif_cls=cpuif_cls,
        clk_src="cpuif",
        axi4lite_max_outstanding=1,
    )
    module = (output / "top.sv").read_text()
    assert f"always_ff @(posedge {clock} or negedge {reset})" in module
    assert f"if (!{reset})" in module
