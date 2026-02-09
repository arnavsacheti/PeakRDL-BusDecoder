from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb3 import APB3CpuifFlat
from peakrdl_busdecoder.cpuif.apb4 import APB4CpuifFlat
from peakrdl_busdecoder.cpuif.axi4lite import AXI4LiteCpuifFlat


PARAMETERIZED_CPUIFS = [
    (APB4CpuifFlat, "m_apb_", "PSEL"),
    (APB3CpuifFlat, "m_apb_", "PSEL"),
    (AXI4LiteCpuifFlat, "m_axil_", "AWVALID"),
]


@pytest.mark.parametrize(("cpuif_cls", "master_prefix", "signal"), PARAMETERIZED_CPUIFS)
def test_parameterized_generation_in_module_ports(
    compile_rdl: Callable[..., AddrmapNode],
    cpuif_cls: type,
    master_prefix: str,
    signal: str,
) -> None:
    """Arrayed children should emit module params and use them in port arrays."""
    rdl_source = """
    addrmap top {
        reg {
            field { sw=rw; hw=r; } data[31:0];
        } regs[4] @ 0x0;
    };
    """
    top = compile_rdl(rdl_source, top="top")

    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=cpuif_cls)

        module_file = Path(tmpdir) / "top.sv"
        content = module_file.read_text()

        assert "module top #(" in content
        assert "parameter N_REGSS = 4" in content
        assert f"{master_prefix}regs_{signal}[N_REGSS]" in content


def test_parameter_list_contains_each_array_size(compile_rdl: Callable[..., AddrmapNode]) -> None:
    """Multiple arrayed children should each get a size parameter."""
    rdl_source = """
    addrmap top {
        reg {
            field { sw=rw; hw=r; } data[31:0];
        } regs[4] @ 0x0;
        reg {
            field { sw=rw; hw=r; } data[7:0];
        } blocks[2] @ 0x100;
    };
    """
    top = compile_rdl(rdl_source, top="top")

    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=APB4CpuifFlat)

        module_file = Path(tmpdir) / "top.sv"
        content = module_file.read_text()

        assert "module top #(" in content
        assert "parameter N_REGSS = 4" in content
        assert "parameter N_BLOCKSS = 2" in content


def test_no_parameters_when_no_arrays(compile_rdl: Callable[..., AddrmapNode]) -> None:
    """Non-array designs should not emit module parameters."""
    rdl_source = """
    addrmap simple {
        reg {
            field { sw=rw; hw=r; } data[31:0];
        } reg0 @ 0x0;
    };
    """
    top = compile_rdl(rdl_source, top="simple")

    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=APB4CpuifFlat)

        module_file = Path(tmpdir) / "simple.sv"
        content = module_file.read_text()

        assert "module simple #(" not in content
        assert "parameter N_" not in content
