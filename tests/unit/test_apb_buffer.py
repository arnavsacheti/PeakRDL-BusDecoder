"""Tests for the apb_buffer exporter option."""

from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif import BaseCpuif
from peakrdl_busdecoder.cpuif.apb3 import APB3Cpuif, APB3CpuifFlat
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif, APB4CpuifFlat
from peakrdl_busdecoder.cpuif.axi4lite import AXI4LiteCpuif


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
        addrmap top_t { leaf a @ 0x0; leaf b @ 0x1000; };
        """,
        top="top_t",
    )


# ---------------------------------------------------------------------------
# Default: no buffer
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cpuif_cls", [APB3CpuifFlat, APB4CpuifFlat, APB3Cpuif, APB4Cpuif])
def test_default_no_buffer_signals(simple_top: AddrmapNode, cpuif_cls: type[BaseCpuif]) -> None:
    content = _export_and_read(simple_top, cpuif_cls=cpuif_cls)
    assert "apb_in_" not in content
    assert "apb_out_" not in content
    assert "APB I/O buffer" not in content


# ---------------------------------------------------------------------------
# apb_buffer="in"
# ---------------------------------------------------------------------------
def test_buffer_in_apb4_flat(simple_top: AddrmapNode) -> None:
    content = _export_and_read(simple_top, cpuif_cls=APB4CpuifFlat, apb_buffer="in")
    # Input wire declarations
    for sig in ("PSEL", "PENABLE", "PWRITE", "PADDR", "PWDATA", "PPROT", "PSTRB"):
        assert f"apb_in_{sig}" in content
    # Flop block reads from slave port
    assert "apb_in_PSEL <= s_apb_PSEL;" in content
    assert "apb_in_PADDR <= s_apb_PADDR;" in content
    # Downstream cpuif logic reads buffered signal, not raw port
    assert "assign cpuif_req   = apb_in_PSEL;" in content
    assert "assign cpuif_wr_data = apb_in_PWDATA;" in content
    # Output side untouched: PRDATA assigned directly to slave port
    assert "assign s_apb_PRDATA = cpuif_rd_data;" in content
    assert "apb_out_" not in content


def test_buffer_in_apb3_omits_pprot_pstrb(simple_top: AddrmapNode) -> None:
    """APB3 has no PPROT/PSTRB, so the buffer must skip them too."""
    content = _export_and_read(simple_top, cpuif_cls=APB3CpuifFlat, apb_buffer="in")
    assert "apb_in_PSEL" in content
    assert "apb_in_PPROT" not in content
    assert "apb_in_PSTRB" not in content


# ---------------------------------------------------------------------------
# apb_buffer="out"
# ---------------------------------------------------------------------------
def test_buffer_out_apb4_flat(simple_top: AddrmapNode) -> None:
    content = _export_and_read(simple_top, cpuif_cls=APB4CpuifFlat, apb_buffer="out")
    # Output wire declarations and flop block write to slave port
    for sig in ("PRDATA", "PREADY", "PSLVERR"):
        assert f"apb_out_{sig}" in content
        assert f"s_apb_{sig} <= apb_out_{sig};" in content
    # Cpuif logic writes to buffered signal
    assert "assign apb_out_PRDATA = cpuif_rd_data;" in content
    # Input side untouched
    assert "assign cpuif_req   = s_apb_PSEL;" in content
    assert "apb_in_" not in content


# ---------------------------------------------------------------------------
# apb_buffer="both"
# ---------------------------------------------------------------------------
def test_buffer_both_apb4_flat(simple_top: AddrmapNode) -> None:
    content = _export_and_read(simple_top, cpuif_cls=APB4CpuifFlat, apb_buffer="both")
    assert "apb_in_PSEL" in content
    assert "apb_out_PRDATA" in content
    # Two separate always_ff blocks
    assert content.count("always_ff @(posedge clk or posedge rst)") >= 2


# ---------------------------------------------------------------------------
# Master fanout untouched by buffer mode
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("apb_buffer", ["none", "in", "out", "both"])
def test_master_fanout_unchanged(simple_top: AddrmapNode, apb_buffer: str) -> None:
    content = _export_and_read(simple_top, cpuif_cls=APB4CpuifFlat, apb_buffer=apb_buffer)
    # Master ports always exist with protocol names regardless of buffer mode
    assert "m_apb_a_PSEL" in content
    assert "m_apb_a_PADDR" in content
    assert "m_apb_a_PRDATA" in content


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_buffer_requires_clk_src_design(simple_top: AddrmapNode) -> None:
    with pytest.raises(Exception):
        _export_and_read(
            simple_top, cpuif_cls=APB4CpuifFlat, apb_buffer="in", clk_src="cpuif"
        )


def test_buffer_rejected_on_non_apb_cpuif(simple_top: AddrmapNode) -> None:
    with pytest.raises(Exception):
        _export_and_read(simple_top, cpuif_cls=AXI4LiteCpuif, apb_buffer="in")


def test_invalid_apb_buffer_value(simple_top: AddrmapNode) -> None:
    with pytest.raises(Exception):
        _export_and_read(simple_top, cpuif_cls=APB4CpuifFlat, apb_buffer="bogus")
