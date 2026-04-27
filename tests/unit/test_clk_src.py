"""Tests for the clk_src exporter option."""

from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif import BaseCpuif
from peakrdl_busdecoder.cpuif.apb3 import APB3Cpuif, APB3CpuifFlat
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif, APB4CpuifFlat
from peakrdl_busdecoder.cpuif.axi4lite import AXI4LiteCpuif, AXI4LiteCpuifFlat


def _export_and_read(top: AddrmapNode, *, cpuif_cls: type[BaseCpuif], **kwargs) -> str:
    with TemporaryDirectory() as tmpdir:
        BusDecoderExporter().export(top, tmpdir, cpuif_cls=cpuif_cls, **kwargs)
        return (Path(tmpdir) / f"{top.inst_name}.sv").read_text()


@pytest.fixture
def simple_top(compile_rdl: Callable[..., AddrmapNode]) -> AddrmapNode:
    return compile_rdl(
        """
        addrmap leaf {
            reg { field { sw=rw; hw=r; } data[31:0]; } r0 @ 0x0;
        };
        addrmap top_t {
            leaf a @ 0x0;
            leaf b @ 0x1000;
        };
        """,
        top="top_t",
    )


# ---------------------------------------------------------------------------
# clk_src=design (default): no bus clk/reset, top-level clk/rst ports added
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "cpuif_cls,clk_signal,reset_signal",
    [
        (APB3CpuifFlat, "PCLK", "PRESETn"),
        (APB4CpuifFlat, "PCLK", "PRESETn"),
        (AXI4LiteCpuifFlat, "ACLK", "ARESETn"),
    ],
)
def test_design_default_drops_bus_clk_reset(
    simple_top: AddrmapNode, cpuif_cls: type[BaseCpuif], clk_signal: str, reset_signal: str
) -> None:
    content = _export_and_read(simple_top, cpuif_cls=cpuif_cls)
    for prefix in ("s_apb_", "s_axil_", "m_apb_a_", "m_apb_b_", "m_axil_a_", "m_axil_b_"):
        assert f"{prefix}{clk_signal}" not in content
        assert f"{prefix}{reset_signal}" not in content


@pytest.mark.parametrize(
    "cpuif_cls", [APB3CpuifFlat, APB4CpuifFlat, AXI4LiteCpuifFlat, APB3Cpuif, APB4Cpuif, AXI4LiteCpuif]
)
def test_design_adds_top_level_clk_rst_ports(
    simple_top: AddrmapNode, cpuif_cls: type[BaseCpuif]
) -> None:
    content = _export_and_read(simple_top, cpuif_cls=cpuif_cls)
    assert "input  logic clk" in content
    assert "input  logic rst" in content


# ---------------------------------------------------------------------------
# clk_src=cpuif: bus carries protocol clk/reset on slave + master, no top-level
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "cpuif_cls,slave_prefix,clk,rst",
    [
        (APB3CpuifFlat, "s_apb_", "PCLK", "PRESETn"),
        (APB4CpuifFlat, "s_apb_", "PCLK", "PRESETn"),
        (AXI4LiteCpuifFlat, "s_axil_", "ACLK", "ARESETn"),
    ],
)
def test_if_adds_bus_clk_reset_on_slave(
    simple_top: AddrmapNode,
    cpuif_cls: type[BaseCpuif],
    slave_prefix: str,
    clk: str,
    rst: str,
) -> None:
    content = _export_and_read(simple_top, cpuif_cls=cpuif_cls, clk_src="cpuif")
    assert f"{slave_prefix}{clk}" in content
    assert f"{slave_prefix}{rst}" in content


@pytest.mark.parametrize(
    "cpuif_cls,master_prefix,clk,rst",
    [
        (APB3CpuifFlat, "m_apb_a_", "PCLK", "PRESETn"),
        (APB4CpuifFlat, "m_apb_a_", "PCLK", "PRESETn"),
        (AXI4LiteCpuifFlat, "m_axil_a_", "ACLK", "ARESETn"),
    ],
)
def test_if_drives_master_clk_reset_in_fanout(
    simple_top: AddrmapNode,
    cpuif_cls: type[BaseCpuif],
    master_prefix: str,
    clk: str,
    rst: str,
) -> None:
    content = _export_and_read(simple_top, cpuif_cls=cpuif_cls, clk_src="cpuif")
    assert f"{master_prefix}{clk}" in content
    assert f"{master_prefix}{rst}" in content
    # And fanout assignment exists
    assert f"assign {master_prefix}{clk}" in content


@pytest.mark.parametrize(
    "cpuif_cls", [APB3CpuifFlat, APB4CpuifFlat, AXI4LiteCpuifFlat, APB3Cpuif, APB4Cpuif, AXI4LiteCpuif]
)
def test_if_omits_top_level_clk_rst_ports(
    simple_top: AddrmapNode, cpuif_cls: type[BaseCpuif]
) -> None:
    content = _export_and_read(simple_top, cpuif_cls=cpuif_cls, clk_src="cpuif")
    # Top-level "input logic clk," should not appear (note: protocol-named PCLK/ACLK
    # are fine; we look for the bare "clk" / "rst" port lines).
    assert "input  logic clk" not in content
    assert "input  logic rst" not in content


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_invalid_clk_src_rejected(simple_top: AddrmapNode) -> None:
    with pytest.raises(Exception):  # systemrdl raises a fatal compile error
        _export_and_read(simple_top, cpuif_cls=APB4Cpuif, clk_src="bogus")
