"""Compile and exercise public target identifiers without inspecting generated HDL.

The depth-two fixture's ctrl targets sit two levels below the exported addrmap.
Additional leaves force flattened-path collisions, case-insensitive collisions,
and a collision with a reserved unique legacy name. The depth-zero fixture mixes
external memory with internal register leaves. Every expected public identifier
below is fixed by the naming contract, not obtained from the exporter.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from systemrdl import RDLCompiler

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb3 import APB3Cpuif, APB3CpuifFlat
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif, APB4CpuifFlat
from peakrdl_busdecoder.cpuif.axi4lite import AXI4LiteCpuif, AXI4LiteCpuifFlat

HDL_DIR = Path(__file__).resolve().parents[2] / "hdl-src"

# Declaration/address order deliberately differs from sorted relative-path order.
# reserve.a_b_slot retains its unique leaf before any collided path is assigned:
# A.B_SLOT, a.b_slot, and a_b.slot must therefore get suffixes 2, 3, and 4.
TARGETS = (
    ("blk_a_ctrl", 0x100),
    ("blk_b_ctrl", 0x200),
    ("a_b_slot__4", 0x300),
    ("a_b_slot__3", 0x400),
    ("z_SLOT", 0x500),
    ("A_B_SLOT__2", 0x600),
    ("a_b_slot", 0x700),
)

# A single 32-bit memory entry and both registers have four-byte local windows.
MEMORY_TARGETS = (
    ("storage", 0x100),
    ("ctrl", 0x200),
    ("status", 0x300),
)

EXPORTS = (
    pytest.param("apb3", False, APB3CpuifFlat, id="apb3-flat"),
    pytest.param("apb3", True, APB3Cpuif, id="apb3-interface"),
    pytest.param("apb4", False, APB4CpuifFlat, id="apb4-flat"),
    pytest.param("apb4", True, APB4Cpuif, id="apb4-interface"),
    pytest.param("axi4lite", False, AXI4LiteCpuifFlat, id="axil-flat"),
    pytest.param("axi4lite", True, AXI4LiteCpuif, id="axil-interface"),
)


def _rdl_source(rolled: bool) -> str:
    array = "[2]" if rolled else ""
    stride = " += 0x4" if rolled else ""
    return f"""
reg word_t {{
    field {{ sw = rw; hw = r; }} value[31:0];
}};
addrmap ctrl_block_t {{
    word_t ctrl{array} @ 0x0{stride};
}};
addrmap flat_block_t {{
    word_t slot{array} @ 0x0{stride};
}};
addrmap nested_block_t {{
    word_t b_slot{array} @ 0x0{stride};
}};
addrmap case_leaf_block_t {{
    word_t SLOT{array} @ 0x0{stride};
}};
addrmap case_path_block_t {{
    word_t B_SLOT{array} @ 0x0{stride};
}};
addrmap reserved_block_t {{
    word_t a_b_slot{array} @ 0x0{stride};
}};
addrmap target_naming {{
    ctrl_block_t blk_a @ 0x100;
    ctrl_block_t blk_b @ 0x200;
    flat_block_t a_b @ 0x300;
    nested_block_t a @ 0x400;
    case_leaf_block_t z @ 0x500;
    case_path_block_t A @ 0x600;
    reserved_block_t reserve @ 0x700;
}};
"""


def _memory_rdl_source() -> str:
    return """
reg word_t {
    field { sw = rw; hw = r; } value[31:0];
};
mem storage_t {
    mementries = 1;
    memwidth = 32;
    sw = rw;
};
addrmap nested_t {
    word_t ctrl @ 0x0;
};
addrmap target_naming {
    external storage_t storage @ 0x100;
    nested_t nested @ 0x200;
    word_t status @ 0x300;
};
"""


def _signal_width(signal: str, address_width: str) -> str:
    if signal in {"PADDR", "AWADDR", "ARADDR"}:
        return f"[{address_width}-1:0] "
    if signal in {"PWDATA", "PRDATA", "WDATA", "RDATA"}:
        return "[31:0] "
    if signal in {"PSTRB", "WSTRB"}:
        return "[3:0] "
    if signal in {"PPROT", "AWPROT", "ARPROT"}:
        return "[2:0] "
    if signal in {"BRESP", "RRESP"}:
        return "[1:0] "
    return ""


def _wrapper_source(
    protocol: str,
    interface: bool,
    rolled: bool,
    targets: tuple[tuple[str, int], ...] = TARGETS,
) -> str:
    """Flatten interface objects behind a common standalone C++ testbench port set.

    Like the cocotb interface wrappers, all interface-array references here use
    constant indices. The DUT itself still exports rolled arrays and must use
    its intermediate fanin signals to select responses at runtime.
    """
    count = 2 if rolled else 1
    endpoints = len(targets) * count
    apb = protocol != "axi4lite"
    slave = "s_apb" if apb else "s_axil"
    master = "m_apb_" if apb else "m_axil_"
    intf_type = f"{protocol}_intf"

    if apb:
        signals = [
            "PSEL", "PENABLE", "PWRITE", "PADDR", "PWDATA", "PRDATA", "PREADY", "PSLVERR"
        ]
        slave_drive = {
            "PSEL": "request",
            "PENABLE": "enable",
            "PWRITE": "write",
            "PADDR": "address",
            "PWDATA": "32'h12345678",
        }
        if protocol == "apb4":
            signals += ["PPROT", "PSTRB"]
            slave_drive.update(PPROT="3'b101", PSTRB="4'b1010")
        clock, reset = "PCLK", "PRESETn"
    else:
        signals = [
            "AWVALID", "AWREADY", "AWADDR", "AWPROT",
            "WVALID", "WREADY", "WDATA", "WSTRB",
            "BVALID", "BREADY", "BRESP",
            "ARVALID", "ARREADY", "ARADDR", "ARPROT",
            "RVALID", "RREADY", "RDATA", "RRESP",
        ]
        slave_drive = {
            "AWVALID": "request & write",
            "AWADDR": "address",
            "AWPROT": "3'b101",
            "WVALID": "request & write",
            "WDATA": "32'h12345678",
            "WSTRB": "4'b1010",
            "BREADY": "1'b1",
            "ARVALID": "request & ~write",
            "ARADDR": "address",
            "ARPROT": "3'b010",
            "RREADY": "1'b1",
        }
        clock, reset = "ACLK", "ARESETn"

    lines = [f"""module target_naming_wrapper (
    input logic request,
    input logic write,
    input logic enable,
    input logic [10:0] address,
    input logic [{endpoints - 1}:0] target_ready,
    input logic [{endpoints - 1}:0] target_error,
    input logic [31:0] target_data [{endpoints}],
    output logic [{endpoints - 1}:0] selected,
    output logic [{endpoints - 1}:0] access,
    output logic [{endpoints - 1}:0] writing,
    output logic [{endpoints - 1}:0] reading,
    output logic [1:0] write_addr [{endpoints}],
    output logic [1:0] read_addr [{endpoints}],
    output logic response_ready,
    output logic response_error,
    output logic [31:0] response_data,
    output logic package_ok,
    output logic counts_ok
);
    import target_naming_pkg::*;"""]
    connections: list[str] = []

    if interface:
        lines += [
            f"    {intf_type} #(.DATA_WIDTH(TARGET_NAMING_DATA_WIDTH), "
            f".ADDR_WIDTH(TARGET_NAMING_MIN_ADDR_WIDTH)) {slave}_intf();",
            f"    assign {slave}_intf.{clock} = 1'b0;",
            f"    assign {slave}_intf.{reset} = 1'b1;",
        ]
        connections.append(f".{slave}({slave}_intf)")
    else:
        for signal in signals:
            width = _signal_width(signal, "TARGET_NAMING_MIN_ADDR_WIDTH")
            lines.append(f"    logic {width}{slave}_{signal};")
            connections.append(f".{slave}_{signal}({slave}_{signal})")

    def slave_signal(signal: str) -> str:
        separator = "_intf." if interface else "_"
        return f"{slave}{separator}{signal}"

    for signal, value in slave_drive.items():
        lines.append(f"    assign {slave_signal(signal)} = {value};")
    if apb:
        responses = {
            "response_ready": slave_signal("PREADY"),
            "response_error": slave_signal("PSLVERR"),
            "response_data": slave_signal("PRDATA"),
        }
    else:
        responses = {
            "response_ready": f"write ? {slave_signal('BVALID')} : {slave_signal('RVALID')}",
            "response_error": f"write ? {slave_signal('BRESP')}[1] : {slave_signal('RRESP')}[1]",
            "response_data": slave_signal("RDATA"),
        }
    for output, value in responses.items():
        lines.append(f"    assign {output} = {value};")

    package_checks = [
        "TARGET_NAMING_DATA_WIDTH == 32",
        "TARGET_NAMING_MIN_ADDR_WIDTH == 11",
    ]
    count_checks = []
    for target_index, (name, _base) in enumerate(targets):
        port = f"{master}{name}"
        address_width = f"TARGET_NAMING_{name.upper()}_ADDR_WIDTH"
        package_checks.append(f"{address_width} == 2")
        dimensions = " [2]" if rolled else ""
        if rolled:
            count_checks.append(f"dut.N_{name.upper()}S == 2")

        if interface:
            lines.append(
                f"    {intf_type} #(.DATA_WIDTH(TARGET_NAMING_DATA_WIDTH), "
                f".ADDR_WIDTH({address_width})) {port}_intf{dimensions}();"
            )
            connections.append(f".{port}({port}_intf)")
        else:
            for signal in signals:
                width = _signal_width(signal, address_width)
                lines.append(f"    logic {width}{port}_{signal}{dimensions};")
                connections.append(f".{port}_{signal}({port}_{signal})")

        for element in range(count):
            endpoint = target_index * count + element
            index = f"[{element}]" if rolled else ""

            def target_signal(signal: str, port: str = port, index: str = index) -> str:
                if interface:
                    return f"{port}_intf{index}.{signal}"
                return f"{port}_{signal}{index}"

            if interface:
                lines += [
                    f"    assign {target_signal(clock)} = 1'b0;",
                    f"    assign {target_signal(reset)} = 1'b1;",
                ]
            if apb:
                target_drive = {
                    "PREADY": f"target_ready[{endpoint}]",
                    "PSLVERR": f"target_error[{endpoint}]",
                    "PRDATA": f"target_data[{endpoint}]",
                }
                target_observe = {
                    "selected": target_signal("PSEL"),
                    "access": target_signal("PENABLE"),
                    "writing": target_signal("PWRITE"),
                    "reading": f"{target_signal('PSEL')} & ~{target_signal('PWRITE')}",
                    "write_addr": target_signal("PADDR"),
                    "read_addr": target_signal("PADDR"),
                }
            else:
                target_drive = {
                    "AWREADY": "1'b1",
                    "WREADY": "1'b1",
                    "BVALID": f"target_ready[{endpoint}]",
                    "BRESP": f"{{target_error[{endpoint}], 1'b0}}",
                    "ARREADY": "1'b1",
                    "RVALID": f"target_ready[{endpoint}]",
                    "RRESP": f"{{target_error[{endpoint}], 1'b0}}",
                    "RDATA": f"target_data[{endpoint}]",
                }
                target_observe = {
                    "selected": f"{target_signal('AWVALID')} | {target_signal('ARVALID')}",
                    "access": target_signal("WVALID"),
                    "writing": target_signal("AWVALID"),
                    "reading": target_signal("ARVALID"),
                    "write_addr": target_signal("AWADDR"),
                    "read_addr": target_signal("ARADDR"),
                }
            for signal, value in target_drive.items():
                lines.append(f"    assign {target_signal(signal)} = {value};")
            for output, value in target_observe.items():
                lines.append(f"    assign {output}[{endpoint}] = {value};")

    lines += [
        "    assign package_ok = " + " && ".join(f"({check})" for check in package_checks) + ";",
        "    assign counts_ok = "
        + (" && ".join(f"({check})" for check in count_checks) if rolled else "1'b1")
        + ";",
        "    target_naming dut (",
        "        " + ",\n        ".join(connections),
        "    );",
        "endmodule",
        "",
    ]
    return "\n".join(lines)


def _cpp_source(
    protocol: str,
    rolled: bool,
    targets: tuple[tuple[str, int], ...] = TARGETS,
) -> str:
    count = 2 if rolled else 1
    bases = [base + 4 * element for _name, base in targets for element in range(count)]
    names = [
        f'"{name}[{element}]"' if rolled else f'"{name}"'
        for name, _base in targets
        for element in range(count)
    ]
    return r"""
#include <cstdint>
#include <iostream>
#include "Vtarget_naming_wrapper.h"
#include "verilated.h"

#define REQUIRE(condition) do { \
    if (!(condition)) { \
        std::cerr << "line " << __LINE__ << ": " << #condition \
                  << "; selected=" << selected << "; responder=" << responder \
                  << "; write=" << write << "; offset=" << offset << '\n'; \
        if (selected >= 0) std::cerr << names[selected] << '\n'; \
        return 1; \
    } \
} while (false)

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    Vtarget_naming_wrapper dut;
    constexpr unsigned bases[] = {BASES};
    const char* names[] = {NAMES};
    constexpr int targets = sizeof(bases) / sizeof(bases[0]);
    constexpr uint32_t all_targets = (1u << targets) - 1u;
    constexpr bool axil = IS_AXIL;
    int selected = -1, responder = -1, write = 0, offset = 0;

    dut.request = 1;
    dut.enable = 1;
    dut.write = 0;
    dut.address = bases[0];
    dut.target_ready = 0;
    dut.target_error = 0;
    for (int i = 0; i < targets; ++i) dut.target_data[i] = 0;
    dut.eval();
    REQUIRE(dut.package_ok == 1);
    REQUIRE(dut.counts_ok == 1);

    for (selected = 0; selected < targets; ++selected) {
        const uint32_t selected_bit = 1u << selected;
        for (write = 0; write <= 1; ++write) {
            for (offset = 0; offset < 4; ++offset) {
                dut.write = write;
                dut.address = bases[selected] + offset;
                dut.target_ready = 0;
                dut.target_error = 0;
                for (int i = 0; i < targets; ++i)
                    dut.target_data[i] = 0x51000000u + 0x101u * (i + 1);
                dut.eval();

                // Every scalar/array element must have an independent select.
                REQUIRE(dut.selected == selected_bit);
                REQUIRE(dut.access == ((!axil || write) ? selected_bit : 0u));
                REQUIRE(dut.writing == (write ? selected_bit : 0u));
                REQUIRE(dut.reading == (write ? 0u : selected_bit));
                if (write) REQUIRE(dut.write_addr[selected] == offset);
                else REQUIRE(dut.read_addr[selected] == offset);
                REQUIRE(dut.response_ready == 0);
                REQUIRE(dut.response_error == 0);

                // Change each ready input independently, including all unselected
                // targets. An accidentally shared fanin reference cannot pass.
                for (responder = 0; responder < targets; ++responder) {
                    dut.target_ready = 1u << responder;
                    dut.eval();
                    REQUIRE(dut.response_ready == (responder == selected));
                    REQUIRE(dut.response_error == 0);
                    if (!write)
                        REQUIRE(dut.response_data == 0x51000000u + 0x101u * (selected + 1));
                }

                // Keep every target ready, then change only one error input.
                dut.target_ready = all_targets;
                for (responder = 0; responder < targets; ++responder) {
                    dut.target_error = 1u << responder;
                    dut.eval();
                    REQUIRE(dut.response_ready == 1);
                    REQUIRE(dut.response_error == (responder == selected));
                    if (!write)
                        REQUIRE(dut.response_data == 0x51000000u + 0x101u * (selected + 1));
                }

                // Finally change only one target's data, independently of ready
                // and error. This also exercises every interface-array fanin.
                dut.target_error = 0;
                if (!write) {
                    for (responder = 0; responder < targets; ++responder) {
                        for (int i = 0; i < targets; ++i) dut.target_data[i] = 0;
                        const uint32_t data = 0xa5000000u + 0x1001u * (responder + 1);
                        dut.target_data[responder] = data;
                        dut.eval();
                        REQUIRE(dut.response_ready == 1);
                        REQUIRE(dut.response_error == 0);
                        REQUIRE(dut.response_data == (responder == selected ? data : 0u));
                    }
                }
            }
        }
    }
    dut.final();
    std::cout << "TARGET_NAMING_SUCCESS\n";
    return 0;
}
""".replace("BASES", ", ".join(hex(base) for base in bases)).replace(
        "NAMES", ", ".join(names)
    ).replace("IS_AXIL", "true" if protocol == "axi4lite" else "false")


def _compile_and_run(
    tmp_path: Path,
    verilator: str,
    protocol: str,
    interface: bool,
    rolled: bool,
    targets: tuple[tuple[str, int], ...] = TARGETS,
) -> None:
    wrapper_path = tmp_path / "target_naming_wrapper.sv"
    wrapper_path.write_text(_wrapper_source(protocol, interface, rolled, targets))
    cpp_path = tmp_path / "main.cpp"
    cpp_path.write_text(_cpp_source(protocol, rolled, targets))
    sources = [tmp_path / "target_naming_pkg.sv"]
    if interface:
        sources.append(HDL_DIR / f"{protocol}_intf.sv")
    sources += [tmp_path / "target_naming.sv", wrapper_path]
    command = [
        verilator, "--cc", "--exe", "--build",
        "-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSEDPARAM", "-Wno-UNUSEDSIGNAL", "-Wno-GENUNNAMED",
        "--top-module", "target_naming_wrapper",
        "-Mdir", str(tmp_path / "obj_dir"),
        "-o", "sim",
        *(str(source) for source in sources),
        str(cpp_path),
    ]
    compilation = subprocess.run(command, capture_output=True, text=True)
    assert compilation.returncode == 0, (
        f"Verilator compilation failed ({protocol}, interface={interface}, rolled={rolled}):\n"
        f"{compilation.stdout}\n{compilation.stderr}"
    )
    simulation = subprocess.run([str(tmp_path / "obj_dir" / "sim")], capture_output=True, text=True)
    assert simulation.returncode == 0, f"Simulation failed:\n{simulation.stdout}\n{simulation.stderr}"
    assert "TARGET_NAMING_SUCCESS" in simulation.stdout


@pytest.mark.verilator
@pytest.mark.parametrize("protocol,interface,cpuif_cls", EXPORTS)
@pytest.mark.parametrize("rolled", [False, True], ids=["scalar", "rolled-array"])
def test_depth_two_target_names(
    tmp_path: Path, protocol: str, interface: bool, cpuif_cls: type, rolled: bool
) -> None:
    """Public names, package constants, array params, fanout, and fanin agree."""
    verilator = shutil.which("verilator")
    assert verilator is not None, "These behavioral regressions require Verilator"

    rdl_path = tmp_path / "target_naming.rdl"
    rdl_path.write_text(_rdl_source(rolled))
    compiler = RDLCompiler()
    compiler.compile_file(str(rdl_path))
    root = compiler.elaborate()
    BusDecoderExporter().export(
        root,
        str(tmp_path),
        cpuif_cls=cpuif_cls,
        max_decode_depth=2,
        cpuif_unroll=False,
        address_width=11,
    )
    _compile_and_run(tmp_path, verilator, protocol, interface, rolled)


@pytest.mark.verilator
@pytest.mark.parametrize("protocol,interface,cpuif_cls", EXPORTS)
def test_depth_zero_external_memory_targets(
    tmp_path: Path, protocol: str, interface: bool, cpuif_cls: type
) -> None:
    """Memory and internal leaves share declared names, local decode, and muxing."""
    verilator = shutil.which("verilator")
    assert verilator is not None, "These behavioral regressions require Verilator"

    rdl_path = tmp_path / "target_naming.rdl"
    rdl_path.write_text(_memory_rdl_source())
    compiler = RDLCompiler()
    compiler.compile_file(str(rdl_path))
    root = compiler.elaborate()
    BusDecoderExporter().export(
        root,
        str(tmp_path),
        cpuif_cls=cpuif_cls,
        max_decode_depth=0,
        cpuif_unroll=False,
        address_width=11,
    )
    _compile_and_run(tmp_path, verilator, protocol, interface, False, MEMORY_TARGETS)

