"""Tests for the --gate-signals / gate_signals=True opt-in feature."""

from collections.abc import Callable
from pathlib import Path

from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb3 import APB3CpuifFlat
from peakrdl_busdecoder.cpuif.apb4 import APB4CpuifFlat


_RDL = """
addrmap multi_slave {
    reg { field { sw=rw; hw=r; } data[31:0]; } a @ 0x0;
    reg { field { sw=rw; hw=r; } data[31:0]; } b @ 0x4;
};
"""


def test_apb4_default_does_not_gate(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
) -> None:
    top = compile_rdl(_RDL, top="multi_slave")
    BusDecoderExporter().export(top, str(tmp_path), cpuif_cls=APB4CpuifFlat)
    sv = (tmp_path / "multi_slave.sv").read_text()
    # PENABLE/PADDR/PWDATA/PSTRB/PPROT must fan out unmodified
    assert "= s_apb_PENABLE;" in sv
    assert "= cpuif_wr_data;" in sv
    assert "= s_apb_PSTRB;" in sv
    assert "= s_apb_PPROT;" in sv
    # No gating expression on broadcast signals
    assert "& s_apb_PENABLE" not in sv
    assert "? cpuif_wr_data : '0" not in sv


def test_apb4_gate_signals_emits_gating(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
) -> None:
    top = compile_rdl(_RDL, top="multi_slave")
    BusDecoderExporter().export(
        top, str(tmp_path), cpuif_cls=APB4CpuifFlat, gate_signals=True
    )
    sv = (tmp_path / "multi_slave.sv").read_text()
    assert "& s_apb_PENABLE" in sv
    assert "? cpuif_wr_data : '0" in sv
    assert "? s_apb_PPROT : '0" in sv
    assert "? cpuif_wr_byte_en : '0" in sv


def test_apb3_default_does_not_gate(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
) -> None:
    top = compile_rdl(_RDL, top="multi_slave")
    BusDecoderExporter().export(top, str(tmp_path), cpuif_cls=APB3CpuifFlat)
    sv = (tmp_path / "multi_slave.sv").read_text()
    assert "= s_apb_PENABLE;" in sv
    assert "= cpuif_wr_data;" in sv
    assert "& s_apb_PENABLE" not in sv
    assert "? cpuif_wr_data : '0" not in sv


def test_apb3_gate_signals_emits_gating(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
) -> None:
    top = compile_rdl(_RDL, top="multi_slave")
    BusDecoderExporter().export(
        top, str(tmp_path), cpuif_cls=APB3CpuifFlat, gate_signals=True
    )
    sv = (tmp_path / "multi_slave.sv").read_text()
    assert "& s_apb_PENABLE" in sv
    assert "? cpuif_wr_data : '0" in sv
