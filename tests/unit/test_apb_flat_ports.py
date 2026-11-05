"""Regression for the released APB decoder's clockless flat-port shape."""

from collections.abc import Callable
from pathlib import Path

from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb.apb_cpuif import APB3CpuifFlat, APB4CpuifFlat

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



def test_flat_apb_interfaces_omit_clock_and_reset_ports(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
) -> None:
    for cpuif_cls in (APB3CpuifFlat, APB4CpuifFlat):
        sv = _export(compile_rdl, tmp_path, cpuif_cls)

        assert "PCLK" not in sv
        assert "PRESETn" not in sv

