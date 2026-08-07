"""Regression tests for simple APB downstream fanout."""

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


def _export(
    compile_rdl: Callable[..., AddrmapNode],
    tmp_path: Path,
    cpuif_cls: type[APB3CpuifFlat] | type[APB4CpuifFlat],
) -> str:
    top = compile_rdl(_RDL, top="multi_slave")
    BusDecoderExporter().export(top, str(tmp_path), cpuif_cls=cpuif_cls)
    return (tmp_path / "multi_slave.sv").read_text()


def _master_fanout(sv: str) -> str:
    return "\n".join(line.strip() for line in sv.splitlines() if line.strip().startswith("assign m_apb_"))


def test_flat_apb_interfaces_omit_clock_and_reset_ports(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
) -> None:
    for cpuif_cls in (APB3CpuifFlat, APB4CpuifFlat):
        sv = _export(compile_rdl, tmp_path, cpuif_cls)

        assert "PCLK" not in sv
        assert "PRESETn" not in sv


def test_apb3_fanout_gates_enable_but_not_payload_signals(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
) -> None:
    fanout = _master_fanout(_export(compile_rdl, tmp_path, APB3CpuifFlat))

    for child in ("a", "b"):
        sel_expr = f"cpuif_wr_sel.{child}|cpuif_rd_sel.{child}"

        assert f"assign m_apb_{child}_PSEL = {sel_expr};" in fanout
        assert f"assign m_apb_{child}_PENABLE = ({sel_expr}) & s_apb_PENABLE;" in fanout
        assert f"assign m_apb_{child}_PWDATA = cpuif_wr_data;" in fanout

    assert all("?" not in line for line in fanout.splitlines() if "_PADDR =" in line)


def test_apb4_fanout_gates_enable_but_not_payload_signals(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
) -> None:
    fanout = _master_fanout(_export(compile_rdl, tmp_path, APB4CpuifFlat))

    for child in ("a", "b"):
        sel_expr = f"cpuif_wr_sel.{child}|cpuif_rd_sel.{child}"

        assert f"assign m_apb_{child}_PSEL = {sel_expr};" in fanout
        assert f"assign m_apb_{child}_PENABLE = ({sel_expr}) & s_apb_PENABLE;" in fanout
        assert f"assign m_apb_{child}_PPROT = s_apb_PPROT;" in fanout
        assert f"assign m_apb_{child}_PWDATA = cpuif_wr_data;" in fanout
        assert f"assign m_apb_{child}_PSTRB = cpuif_wr_byte_en;" in fanout

    assert all("?" not in line for line in fanout.splitlines() if "_PADDR =" in line)
