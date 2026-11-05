"""Compile real exported RTL and exercise interface-width diagnostics at runtime."""

import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif import BaseCpuif
from peakrdl_busdecoder.cpuif.ahblite import AHBLiteCpuif
from peakrdl_busdecoder.cpuif.apb.apb_cpuif import APB3Cpuif, APB4Cpuif
from peakrdl_busdecoder.cpuif.axi4lite import AXI4LiteCpuif

_REPO = Path(__file__).resolve().parents[2]
_PROTOCOLS: dict[str, tuple[type[BaseCpuif], str]] = {
    "apb3": (APB3Cpuif, "apb"),
    "apb4": (APB4Cpuif, "apb"),
    "axi4lite": (AXI4LiteCpuif, "axil"),
    "ahblite": (AHBLiteCpuif, "ahb"),
}
_SIMULATOR_BANNER = re.compile(
    r"(?:- .+interface_width_wrapper\.sv:\d+: Verilog \$finish"
    r"|- S i m u l a t i o n   R e p o r t: Verilator .+"
    r"|- Verilator: .+)"
)


def _wrapper(
    protocol: str,
    *,
    upstream_address_width: int = 16,
    upstream_data_width: int = 32,
    child_address_width: int = 10,
    child_data_width: int = 32,
) -> str:
    """Connect the supplied production interfaces, with idle traffic and real clocks."""
    bus = _PROTOCOLS[protocol][1]
    lines = [
        "module interface_width_wrapper;",
        "    logic clk = 1'b0;",
        "    logic rst = 1'b1;",
        "    always #1 clk = ~clk;",
    ]
    instances = (
        ("upstream", upstream_address_width, upstream_data_width),
        ("child_a", child_address_width, child_data_width),
    )
    for name, address_width, data_width in instances:
        clocks = "(.HCLK(clk), .HRESETn(~rst))" if protocol == "ahblite" else "()"
        lines.append(
            f"    {protocol}_intf #(.ADDR_WIDTH({address_width}), .DATA_WIDTH({data_width})) "
            f"{name} {clocks};"
        )

    if protocol in ("apb3", "apb4"):
        inputs = {signal: "'0" for signal in ("PSEL", "PENABLE", "PWRITE", "PADDR", "PWDATA")}
        if protocol == "apb4":
            inputs.update(PPROT="'0", PSTRB="'0")
        responses = {"PREADY": "1'b1", "PSLVERR": "1'b0", "PRDATA": "'0"}
        for name, _, _ in instances:
            lines += [f"    assign {name}.PCLK = clk;", f"    assign {name}.PRESETn = ~rst;"]
    elif protocol == "axi4lite":
        inputs = {
            signal: "'0"
            for signal in (
                "AWVALID", "AWADDR", "AWPROT", "WVALID", "WDATA", "WSTRB", "BREADY",
                "ARVALID", "ARADDR", "ARPROT", "RREADY",
            )
        }
        responses = {
            "AWREADY": "1'b1", "WREADY": "1'b1", "BVALID": "1'b0", "BRESP": "'0",
            "ARREADY": "1'b1", "RVALID": "1'b0", "RDATA": "'0", "RRESP": "'0",
        }
        for name, _, _ in instances:
            lines += [f"    assign {name}.ACLK = clk;", f"    assign {name}.ARESETn = ~rst;"]
    else:
        inputs = {
            signal: "'0"
            for signal in (
                "HSEL", "HADDR", "HTRANS", "HWRITE", "HSIZE", "HBURST", "HPROT",
                "HMASTLOCK", "HWDATA",
            )
        }
        inputs["HREADY"] = "1'b1"
        responses = {"HREADYOUT": "1'b1", "HRESP": "1'b0", "HRDATA": "'0"}

    lines.extend(f"    assign upstream.{signal} = {value};" for signal, value in inputs.items())
    lines.extend(f"    assign child_a.{signal} = {value};" for signal, value in responses.items())
    connections = [] if protocol == "ahblite" else [".clk(clk)", ".rst(rst)"]
    connections += [f".s_{bus}(upstream)", f".m_{bus}_a(child_a)"]
    lines += [
        "    width_router dut (" + ", ".join(connections) + ");",
        "    initial begin",
        "        #2 rst = 1'b0;",
        "        #2 $finish;",
        "    end",
        "endmodule",
    ]
    return "\n".join(lines) + "\n"


def _simulate(
    compile_rdl: Callable[..., AddrmapNode],
    tmp_path: Path,
    protocol: str,
    **widths: int,
) -> subprocess.CompletedProcess[str]:
    verilator = shutil.which("verilator")
    assert verilator is not None, "These behavioral interface-width regressions require Verilator"
    # The 1-KiB child at offset 0x400 makes the top require 11 address bits.
    # APB/AXI are configured for that minimum; their real ingress interfaces
    # may be wider. AHB is configured for 16 bits and requires that exact width.
    top = compile_rdl(
        """
        addrmap leaf {
            reg { field { sw=rw; hw=r; } data[31:0]; } first @ 0;
            reg { field { sw=rw; hw=r; } data[31:0]; } last @ 0x3fc;
        };
        addrmap width_map { leaf a @ 0x400; };
        """,
        top="width_map",
    )
    BusDecoderExporter().export(
        top,
        str(tmp_path),
        cpuif_cls=_PROTOCOLS[protocol][0],
        clk_src="design",
        address_width=16 if protocol == "ahblite" else 11,
        data_width=32,
        module_name="width_router",
        package_name="width_router_pkg",
    )
    wrapper = tmp_path / "interface_width_wrapper.sv"
    wrapper.write_text(_wrapper(protocol, **widths))
    obj_dir = tmp_path / "obj_dir"
    compilation = subprocess.run(
        [
            verilator, "--binary", "--timing", "--assert",
            "--top-module", "interface_width_wrapper",
            "--Mdir", str(obj_dir), "-o", "sim", "-j", "1",
            "-Wall", "-Wno-fatal", "-Wno-DECLFILENAME", "-Wno-UNUSEDPARAM",
            "-Wno-UNUSEDSIGNAL", "-Wno-GENUNNAMED",
            str(_REPO / "hdl-src" / f"{protocol}_intf.sv"),
            str(tmp_path / "width_router_pkg.sv"), str(tmp_path / "width_router.sv"), str(wrapper),
        ],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=240,
        check=False,
    )
    # Width-mismatch lint warnings must not prevent the runtime assertion from
    # executing. Compilation success and simulation failure are separate checks.
    assert compilation.returncode == 0, f"Verilator compilation failed:\n{compilation.stdout}"
    return subprocess.run(
        [str(obj_dir / "sim")],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize(
    ("protocol", "endpoint", "kind", "actual"),
    [
        pytest.param("apb3", "upstream", "address", 10, id="apb3-address"),
        pytest.param("apb3", "upstream", "data", 64, id="apb3-data"),
        pytest.param("apb4", "upstream", "address", 10, id="apb4-address"),
        pytest.param("apb4", "upstream", "data", 64, id="apb4-data"),
        pytest.param("axi4lite", "upstream", "address", 10, id="axi4lite-address"),
        pytest.param("axi4lite", "upstream", "data", 64, id="axi4lite-data"),
        pytest.param("ahblite", "upstream", "address", 17, id="ahblite-upstream-address"),
        pytest.param("ahblite", "upstream", "data", 64, id="ahblite-upstream-data"),
        pytest.param("ahblite", "child", "address", 11, id="ahblite-child-address"),
        pytest.param("ahblite", "child", "data", 64, id="ahblite-child-data"),
    ],
)
def test_invalid_interface_widths_fail_at_runtime(
    compile_rdl: Callable[..., AddrmapNode],
    tmp_path: Path,
    protocol: str,
    endpoint: str,
    kind: str,
    actual: int,
) -> None:
    """Every width diagnostic reports actual signals/widths and terminates simulation."""
    result = _simulate(compile_rdl, tmp_path, protocol, **{f"{endpoint}_{kind}_width": actual})
    assert result.returncode != 0, f"Mismatched widths unexpectedly ran successfully:\n{result.stdout}"
    assert "Verilog $finish" not in result.stdout, result.stdout

    bus = _PROTOCOLS[protocol][1]
    port = f"s_{bus}" if endpoint == "upstream" else f"m_{bus}_a"
    if kind == "address":
        required = (16 if endpoint == "upstream" else 10) if protocol == "ahblite" else 11
        signals = ("AWADDR", "ARADDR") if protocol == "axi4lite" else (
            "HADDR" if protocol == "ahblite" else "PADDR",
        )
        policy = "exactly" if protocol == "ahblite" else "at least"
    else:
        required = 32
        signals = ("HWDATA", "HRDATA") if protocol == "ahblite" else (
            "WDATA" if protocol == "axi4lite" else "PWDATA",
        )
        policy = "exactly"
    actual_widths = " and ".join(f"{port}.{signal} is {actual} bits" for signal in signals)
    expected = f"{actual_widths}; expected {policy} {required} bits"
    if len(signals) > 1:
        expected += " each"
    diagnostic = (
        rf"Interface {kind} width mismatch at [^:\n]*interface_width_wrapper\.dut[^:\n]*: "
        + re.escape(expected)
    )
    assert re.search(diagnostic, result.stdout), result.stdout


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize(
    ("protocol", "address_width"),
    [
        pytest.param("apb3", 11, id="apb3-minimum-address"),
        pytest.param("apb3", 16, id="apb3-wider-address"),
        pytest.param("apb4", 11, id="apb4-minimum-address"),
        pytest.param("apb4", 16, id="apb4-wider-address"),
        pytest.param("axi4lite", 11, id="axi4lite-minimum-address"),
        pytest.param("axi4lite", 16, id="axi4lite-wider-address"),
        pytest.param("ahblite", 16, id="ahblite-exact-address"),
    ],
)
def test_correct_interface_widths_are_silent(
    compile_rdl: Callable[..., AddrmapNode],
    tmp_path: Path,
    protocol: str,
    address_width: int,
) -> None:
    """Valid interfaces emit no runtime text beyond Verilator's standard finish/report."""
    result = _simulate(compile_rdl, tmp_path, protocol, upstream_address_width=address_width)
    assert result.returncode == 0, f"Correct widths failed simulation:\n{result.stdout}"
    assert "Verilog $finish" in result.stdout, result.stdout
    unexpected = [
        line for line in result.stdout.splitlines()
        if line.strip() and _SIMULATOR_BANNER.fullmatch(line.strip()) is None
    ]
    assert not unexpected, f"Unexpected runtime output for correct widths:\n{result.stdout}"
