"""Finite, edge-counted APB3/APB4 transaction coverage against generated RTL.

The literal two-child map and autonomous RTL peripherals are independent of
exporter metadata. This is a bounded behavioral regression, not a formal proof.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb.apb_cpuif import APB3Cpuif, APB3CpuifFlat, APB4Cpuif, APB4CpuifFlat

try:
    from cocotb.runner import get_runner
except ImportError:
    from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parents[2]
CHILDREN = ("first", "second")
RDL = """
reg word_t {
    field { sw = rw; hw = r; } value[31:0];
};
addrmap peripheral_t {
    word_t words[4] @ 0x0 += 0x4;
};
addrmap apb_back_to_back {
    peripheral_t first @ 0x20;
    peripheral_t second @ 0x40;
};
"""


def _wrapper(protocol: str, interface: bool) -> str:
    """Supply the child-model clock externally, never add a decoder clock port."""
    signals = [
        ("PSEL", 1, True), ("PENABLE", 1, True), ("PWRITE", 1, True),
        ("PADDR", 8, True), ("PWDATA", 32, True),
        ("PRDATA", 32, False), ("PREADY", 1, False), ("PSLVERR", 1, False),
    ]
    if protocol == "apb4":
        signals += [("PPROT", 3, True), ("PSTRB", 4, True)]

    def declaration(direction: str, name: str, width: int) -> str:
        bits = "" if width == 1 else f"[{width - 1}:0] "
        return f"    {direction} logic {bits}{name}"

    ports = ["    input logic clk", "    input logic resetn"]
    for name, width, request in signals:
        ports.append(declaration("input" if request else "output", f"s_apb_{name}", width))
    counters = ("completions", "errors", "read_effects", "write_effects", "memory0", "memory1")
    for child in range(2):
        for name, width, _request in signals:
            ports.append(declaration("output", f"child{child}_{name}", 4 if name == "PADDR" else width))
        for name in counters:
            ports.append(declaration("output", f"child{child}_{name}", 32))
    ports += ["    output logic [31:0] accepted", "    output logic [31:0] returned_errors"]
    lines = ["module apb_b2b_tb (", ",\n".join(ports), ");"]
    connections = []
    if interface:
        for bus, width in (("upstream", 8), ("downstream0", 4), ("downstream1", 4)):
            lines += [
                f"    {protocol}_intf #(.ADDR_WIDTH({width}), .DATA_WIDTH(32)) {bus}();",
                f"    assign {bus}.PCLK = clk;",
                f"    assign {bus}.PRESETn = resetn;",
            ]
        for name, _width, request in signals:
            lhs, rhs = (f"upstream.{name}", f"s_apb_{name}")
            if not request:
                lhs, rhs = rhs, lhs
            lines.append(f"    assign {lhs} = {rhs};")
            for child in range(2):
                lhs, rhs = (f"child{child}_{name}", f"downstream{child}.{name}")
                if not request:
                    lhs, rhs = rhs, lhs
                lines.append(f"    assign {lhs} = {rhs};")
        connections = [".s_apb(upstream)"] + [
            f".m_apb_{name}(downstream{child})" for child, name in enumerate(CHILDREN)
        ]
    else:
        connections = [f".s_apb_{name}(s_apb_{name})" for name, _width, _request in signals]
        connections += [
            f".m_apb_{target}_{name}(child{child}_{name})"
            for child, target in enumerate(CHILDREN)
            for name, _width, _request in signals
        ]
    lines += ["    apb_back_to_back dut (", "        " + ",\n        ".join(connections), "    );"]
    for child in range(2):
        model_signals = [name for name, _width, _request in signals if name != "PPROT"]
        connections = [".clk(clk)", ".resetn(resetn)"]
        connections += [f".{name}(child{child}_{name})" for name in (*model_signals, *counters)]
        if protocol == "apb3":
            connections.append(".PSTRB(4'hf)")
        lines += [
            f"    apb_stateful_child #(.ID({child})) peripheral{child} (",
            "        " + ",\n        ".join(connections),
            "    );",
        ]
    lines += [
        "    always_ff @(posedge clk) begin",
        "        if (!resetn) begin",
        "            accepted <= 0;",
        "            returned_errors <= 0;",
        "        end else if (s_apb_PSEL && s_apb_PENABLE && s_apb_PREADY) begin",
        "            accepted <= accepted + 1'b1;",
        "            if (s_apb_PSLVERR) returned_errors <= returned_errors + 1'b1;",
        "        end",
        "    end",
        "endmodule",
        "",
    ]
    return "\n".join(lines)


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize(
    "protocol,interface,cpuif_cls",
    [
        pytest.param("apb3", False, APB3CpuifFlat, id="apb3-flat"),
        pytest.param("apb3", True, APB3Cpuif, id="apb3-interface"),
        pytest.param("apb4", False, APB4CpuifFlat, id="apb4-flat"),
        pytest.param("apb4", True, APB4Cpuif, id="apb4-interface"),
    ],
)
def test_apb_back_to_back(tmp_path, compile_rdl, protocol, interface, cpuif_cls) -> None:
    """Keep PSEL high across real SETUP/ACCESS transfers and child handshakes."""
    if shutil.which("verilator") is None:
        pytest.skip("Verilator is required for the stateful APB regression")
    top = compile_rdl(RDL)
    BusDecoderExporter().export(
        top, str(tmp_path), cpuif_cls=cpuif_cls, max_decode_depth=1,
        address_width=8, cpuif_unroll=False,
    )
    wrapper = tmp_path / "apb_b2b_tb.sv"
    wrapper.write_text(_wrapper(protocol, interface))
    sources = [tmp_path / "apb_back_to_back_pkg.sv", tmp_path / "apb_back_to_back.sv"]
    if interface:
        sources.insert(0, ROOT / "hdl-src" / f"{protocol}_intf.sv")
    sources += [ROOT / "tests" / "cocotb_lib" / "apb_stateful_child.sv", wrapper]
    runner = get_runner("verilator")
    build_dir = tmp_path / "sim_build"
    try:
        runner.build(
            sources=[str(path) for path in sources], hdl_toplevel="apb_b2b_tb",
            build_dir=build_dir,
            build_args=["-Wno-DECLFILENAME", "-Wno-UNUSEDPARAM", "-Wno-UNUSEDSIGNAL", "-Wno-GENUNNAMED"],
            log_file=str(tmp_path / "build.log"),
        )
        runner.test(
            hdl_toplevel="apb_b2b_tb", test_module="tests.cocotb_lib.apb_back_to_back",
            build_dir=build_dir, extra_env={"APB_TEST_PROTOCOL": protocol},
            log_file=str(tmp_path / "simulation.log"),
        )
    except SystemExit:
        for name in ("build.log", "simulation.log"):
            path = tmp_path / name
            if path.exists():
                print(path.read_text())
        raise
