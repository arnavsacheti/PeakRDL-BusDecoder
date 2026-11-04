"""The supported APB API uses the shared interface implementations."""

from collections.abc import Callable
from pathlib import Path

import pytest
from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb.apb_cpuif import (
    APB3Cpuif,
    APB3CpuifFlat,
    APB4Cpuif,
    APB4CpuifFlat,
)
from peakrdl_busdecoder.cpuif.apb.apb_interface import APBFlatInterface, APBSVInterface


@pytest.mark.parametrize(
    ("cpuif_cls", "interface", "version"),
    [
        (APB3Cpuif, True, 3),
        (APB3CpuifFlat, False, 3),
        (APB4Cpuif, True, 4),
        (APB4CpuifFlat, False, 4),
    ],
)
def test_apb_variants_use_shared_interfaces(
    compile_rdl: Callable[..., AddrmapNode],
    tmp_path: Path,
    cpuif_cls: type,
    interface: bool,
    version: int,
) -> None:
    top = compile_rdl("""
        addrmap apb_api {
            reg { field { sw=rw; hw=r; } data[31:0]; } control @ 0;
        };
    """, top="apb_api")
    exporter = BusDecoderExporter()
    exporter.export(top, str(tmp_path), cpuif_cls=cpuif_cls)
    bus = exporter.cpuif._interface
    module = (tmp_path / "apb_api.sv").read_text()
    if interface:
        assert isinstance(bus, APBSVInterface)
        assert bus.get_interface_type() == f"apb{version}_intf"
        assert f"apb{version}_intf.slave s_apb" in module
        assert f"apb{version}_intf.master m_apb_control" in module
    else:
        assert isinstance(bus, APBFlatInterface)
        for signal in ("PSEL", "PENABLE", "PWRITE", "PADDR", "PWDATA", "PRDATA", "PREADY", "PSLVERR"):
            assert f"s_apb_{signal}" in module
            assert f"m_apb_control_{signal}" in module
        for signal in ("PPROT", "PSTRB"):
            assert (f"s_apb_{signal}" in module) == (version == 4)
            assert (f"m_apb_control_{signal}" in module) == (version == 4)
