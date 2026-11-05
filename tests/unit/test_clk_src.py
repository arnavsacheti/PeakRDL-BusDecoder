"""Executable clock-source contracts and real CLI/API rejection diagnostics.

The APB cases reuse the edge-counted buffer scoreboard, including unbuffered
clockless decoders. AXI4-Lite reuses the clocked target-routing harness. Exact
port inspection supplements these finite RTL executions; it does not replace
them.
"""

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from systemrdl import RDLCompileError
from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif import BaseCpuif
from peakrdl_busdecoder.cpuif.ahblite import AHBLiteCpuif, AHBLiteCpuifFlat
from peakrdl_busdecoder.cpuif.apb.apb_cpuif import APB4Cpuif
from peakrdl_busdecoder.cpuif.axi4lite import AXI4LiteCpuif, AXI4LiteCpuifFlat
from peakrdl_busdecoder.exporter import ExporterKwargs
from tests.formal.test_target_naming import _compile_and_run
from tests.unit.test_apb_buffer import _EXPORTS, _simulate

_REPO = Path(__file__).resolve().parents[2]
_APB_RDL = """
addrmap leaf {
    reg { field { sw=rw; hw=r; } data[31:0]; } first @ 0x0;
    reg { field { sw=rw; hw=r; } data[31:0]; } last @ 0xfc;
};
addrmap top_t { leaf a @ 0x0; leaf b @ 0x1000; };
"""
_AXIL_RDL = """
addrmap leaf {
    reg { field { sw=rw; hw=r; } data[31:0]; } word @ 0x0;
};
addrmap target_naming { leaf a @ 0x100; leaf b @ 0x200; };
"""
_CLOCK_SOURCES = (
    pytest.param(None, True, id="omitted"),
    pytest.param(None, False, id="api-none"),
    pytest.param("off", False, id="off"),
    pytest.param("design", False, id="design"),
    pytest.param("cpuif", False, id="cpuif"),
)


@pytest.fixture
def simple_top(compile_rdl: Callable[..., AddrmapNode]) -> AddrmapNode:
    return compile_rdl(_APB_RDL, top="top_t")


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize("apb4,interface,cpuif_cls", _EXPORTS)
@pytest.mark.parametrize("clk_src,omit_clk_src", _CLOCK_SOURCES)
def test_apb_clock_sources(
    simple_top: AddrmapNode,
    tmp_path: Path,
    apb4: bool,
    interface: bool,
    cpuif_cls: type[BaseCpuif],
    clk_src: str | None,
    omit_clk_src: bool,
) -> None:
    """Legacy ports, routing, waits, errors, and side effects work in each mode."""
    _simulate(
        simple_top,
        tmp_path,
        apb4=apb4,
        interface=interface,
        cpuif_cls=cpuif_cls,
        apb_buffer="none",
        gate_signals=True,
        clk_src=clk_src,
        omit_clk_src=omit_clk_src,
    )


@pytest.mark.parametrize("apb4,interface,cpuif_cls", _EXPORTS)
@pytest.mark.parametrize("clk_src,omit_clk_src", _CLOCK_SOURCES)
def test_apb_fixed_reset_follows_resolved_clock_source(
    simple_top: AddrmapNode,
    tmp_path: Path,
    apb4: bool,
    interface: bool,
    cpuif_cls: type[BaseCpuif],
    clk_src: str | None,
    omit_clk_src: bool,
) -> None:
    options: ExporterKwargs = {"cpuif_cls": cpuif_cls}
    if not omit_clk_src:
        options["clk_src"] = clk_src
    exporter = BusDecoderExporter()
    exporter.export(simple_top, str(tmp_path), **options)
    if clk_src in (None, "off"):
        assert exporter.cpuif.fixed_reset is None
    elif clk_src == "design":
        assert exporter.cpuif.fixed_reset == ("rst", False)
    else:
        reset = "s_apb.PRESETn" if interface else "s_apb_PRESETn"
        assert exporter.cpuif.fixed_reset == (reset, True)


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize(
    "interface,cpuif_cls",
    [
        pytest.param(False, AXI4LiteCpuifFlat, id="flat"),
        pytest.param(True, AXI4LiteCpuif, id="interface"),
    ],
)
@pytest.mark.parametrize(
    "clk_src,omit_clk_src",
    [
        pytest.param(None, True, id="omitted"),
        pytest.param(None, False, id="api-none"),
        pytest.param("design", False, id="design"),
    ],
)
def test_axi4lite_default_design_clock(
    compile_rdl: Callable[..., AddrmapNode],
    tmp_path: Path,
    interface: bool,
    cpuif_cls: type[BaseCpuif],
    clk_src: str | None,
    omit_clk_src: bool,
) -> None:
    """Default AXI queues still use generic design ports and real clock edges."""
    verilator = shutil.which("verilator")
    assert verilator is not None, "These behavioral clock-source regressions require Verilator"
    top = compile_rdl(_AXIL_RDL, top="target_naming")
    options: ExporterKwargs = {"cpuif_cls": cpuif_cls, "address_width": 11}
    if not omit_clk_src:
        options["clk_src"] = clk_src
    BusDecoderExporter().export(top, str(tmp_path), **options)
    content = (tmp_path / "target_naming.sv").read_text()
    header = re.search(r"\)\s*\((.*?)\);", content, flags=re.DOTALL)
    assert header is not None, "Expected AXI queue parameter and decoder ports"
    ports = [" ".join(port.split()) for port in header.group(1).split(",")]
    assert ports[:2] == ["input logic clk", "input logic rst"]
    assert "ACLK" not in content and "ARESETn" not in content
    _compile_and_run(
        tmp_path, verilator, "axi4lite", interface, False,
        targets=(("a", 0x100), ("b", 0x200)),
    )


@pytest.mark.parametrize(
    "cpuif_cls,diagnostic,remedy",
    [
        pytest.param(
            AXI4LiteCpuifFlat, "--clk-src off is not supported by AXI4-Lite",
            "use --clk-src design", id="axil-flat",
        ),
        pytest.param(
            AXI4LiteCpuif, "--clk-src off is not supported by AXI4-Lite",
            "use --clk-src design", id="axil-interface",
        ),
        pytest.param(
            AHBLiteCpuifFlat, "--clk-src off is not supported by AHB-Lite",
            "Omit --clk-src or select cpuif", id="ahb-flat",
        ),
        pytest.param(
            AHBLiteCpuif, "--clk-src off is not supported by AHB-Lite",
            "Omit --clk-src or select cpuif", id="ahb-interface",
        ),
    ],
)
def test_stateful_cpuif_rejects_off(
    simple_top: AddrmapNode,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    cpuif_cls: type[BaseCpuif],
    diagnostic: str,
    remedy: str,
) -> None:
    with pytest.raises(RDLCompileError, match=re.escape(diagnostic)):
        BusDecoderExporter().export(simple_top, str(tmp_path), cpuif_cls=cpuif_cls, clk_src="off")
    captured = capsys.readouterr()
    assert remedy in captured.out + captured.err


@pytest.mark.parametrize(
    "cpuif,apb_buffer,required",
    [
        pytest.param(
            cpuif, mode,
            ("--apb-buffer", "--clk-src design", "omit --clk-src", "--apb-buffer none"),
            id=f"{cpuif}-{mode}",
        )
        for cpuif in ("apb3", "apb3-flat", "apb4", "apb4-flat")
        for mode in ("in", "out", "both")
    ] + [
        pytest.param(
            cpuif, "none",
            ("--clk-src off", "AXI4-Lite", "--clk-src design", "--clk-src cpuif"),
            id=cpuif,
        )
        for cpuif in ("axi4-lite", "axi4-lite-flat")
    ] + [
        pytest.param(
            cpuif, "none",
            ("--clk-src off", "AHB-Lite", "HCLK/HRESETn", "Omit --clk-src", "select cpuif"),
            id=cpuif,
        )
        for cpuif in ("ahb-lite", "ahb-lite-flat")
    ],
)
def test_cli_rejects_stateful_off_without_traceback(
    tmp_path: Path, cpuif: str, apb_buffer: str, required: tuple[str, ...]
) -> None:
    """Invoke the installed plugin through the current interpreter, not a mock."""
    rdl_path = tmp_path / "clock_modes.rdl"
    rdl_path.write_text(_APB_RDL)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(_REPO / "src"), environment.get("PYTHONPATH", "")) if value
    )
    result = subprocess.run(
        [
            sys.executable, "-m", "peakrdl", "busdecoder", str(rdl_path),
            "-t", "top_t", "-o", str(tmp_path / "rtl"),
            "--cpuif", cpuif, "--clk-src", "off", "--apb-buffer", apb_buffer,
        ],
        cwd=_REPO,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    message = result.stdout + result.stderr
    assert result.returncode != 0, f"CLI unexpectedly accepted stateful off:\n{message}"
    assert "Traceback" not in message, message
    for fragment in required:
        assert fragment in message, message


def test_invalid_clk_src_rejected(simple_top: AddrmapNode, tmp_path: Path) -> None:
    with pytest.raises(RDLCompileError, match="--clk-src must be 'off', 'cpuif' or 'design'"):
        BusDecoderExporter().export(simple_top, str(tmp_path), cpuif_cls=APB4Cpuif, clk_src="bogus")
