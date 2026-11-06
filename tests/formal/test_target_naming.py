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
from peakrdl_busdecoder.cpuif.apb.apb_cpuif import (
    APB3Cpuif, APB3CpuifFlat, APB4Cpuif, APB4CpuifFlat,
)
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
    ("MIN__2", 0x780),
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
    word_t MIN{array} @ 0x780{stride};
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
    The harness keeps its test clock/reset in every case, but only AXI4-Lite's
    default design-clocked DUT connects generic clk/rst ports. APB defaults to
    clockless decoding; its interface clocks remain driven for bus timing.
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
            slave_drive.update(PPROT="3'b101", PSTRB="write ? 4'b1010 : 4'b0000")
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
            "BREADY": "response_accept",
            "ARVALID": "request & ~write",
            "ARADDR": "address",
            "ARPROT": "3'b010",
            "RREADY": "response_accept",
        }
        clock, reset = "ACLK", "ARESETn"

    lines = [f"""module target_naming_wrapper (
    input logic clk,
    input logic rst,
    input logic response_accept,
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
    output logic request_ready,
    output logic response_ready,
    output logic response_error,
    output logic [1:0] response_code,
    output logic [31:0] response_data,
    output logic package_ok,
    output logic counts_ok
);
    import target_naming_pkg::*;"""]
    connections: list[str] = [] if apb else [".clk(clk)", ".rst(rst)"]

    if interface:
        lines += [
            f"    {intf_type} #(.DATA_WIDTH(TARGET_NAMING_DATA_WIDTH), "
            f".ADDR_WIDTH(TARGET_NAMING_MIN_ADDR_WIDTH)) {slave}_intf();",
            f"    assign {slave}_intf.{clock} = clk;",
            f"    assign {slave}_intf.{reset} = ~rst;",
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
            "request_ready": "1'b1",
            "response_code": f"{{{slave_signal('PSLVERR')}, 1'b0}}",
        }
    else:
        responses = {
            "response_ready": f"write ? {slave_signal('BVALID')} : {slave_signal('RVALID')}",
            "response_error": f"write ? {slave_signal('BRESP')}[1] : {slave_signal('RRESP')}[1]",
            "response_data": slave_signal("RDATA"),
            "response_code": f"write ? {slave_signal('BRESP')} : {slave_signal('RRESP')}",
            "request_ready": (
                f"write ? ({slave_signal('AWREADY')} & {slave_signal('WREADY')})"
                f" : {slave_signal('ARREADY')}"
            ),
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
                    f"    assign {target_signal(clock)} = clk;",
                    f"    assign {target_signal(reset)} = ~rst;",
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
                    "writing": f"{target_signal('PSEL')} & {target_signal('PWRITE')}",
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
    permissions: tuple[tuple[bool, bool], ...] | None = None,
) -> str:
    count = 2 if rolled else 1
    bases = [base + 4 * element for _name, base in targets for element in range(count)]
    names = [
        f'"{name}[{element}]"' if rolled else f'"{name}"'
        for name, _base in targets
        for element in range(count)
    ]
    permissions = permissions or ((True, True),) * len(targets)
    readable = [read for read, _write in permissions for _ in range(count)]
    writable = [write for _read, write in permissions for _ in range(count)]
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
    constexpr bool readable[] = {READABLE};
    constexpr bool writable[] = {WRITABLE};
    constexpr int targets = sizeof(bases) / sizeof(bases[0]);
    constexpr uint32_t all_targets = (1u << targets) - 1u;
    constexpr bool axil = IS_AXIL;
    int selected = -1, responder = -1, write = 0, offset = 0;
    auto tick = [&]() {
        dut.clk = 0; dut.eval();
        dut.clk = 1; dut.eval();
        dut.clk = 0; dut.eval();
    };

    dut.clk = 0;
    dut.rst = 1;
    dut.request = 0;
    dut.response_accept = 0;
    dut.enable = 1;
    dut.write = 0;
    dut.address = bases[0];
    dut.target_ready = 0;
    dut.target_error = 0;
    for (int i = 0; i < targets; ++i) dut.target_data[i] = 0;
    tick();
    dut.rst = 0;
    dut.eval();
    REQUIRE(dut.package_ok == 1);
    REQUIRE(dut.counts_ok == 1);

    for (selected = 0; selected < targets; ++selected) {
        for (write = 0; write <= 1; ++write) {
            for (offset = 0; offset < 4; ++offset) {
                const unsigned address = bases[selected] + offset;
                int destination = -1;
                for (int candidate = 0; candidate < targets; ++candidate) {
                    if (address >= bases[candidate] && address < bases[candidate] + 4
                        && (write ? writable[candidate] : readable[candidate])) {
                        REQUIRE(destination == -1);
                        destination = candidate;
                    }
                }
                const uint32_t selected_bit = destination < 0 ? 0u : 1u << destination;
                dut.write = write;
                dut.address = address;
                dut.request = 1;
                dut.response_accept = 0;
                dut.target_ready = 0;
                dut.target_error = 0;
                for (int i = 0; i < targets; ++i)
                    dut.target_data[i] = 0x51000000u + 0x101u * (i + 1);
                dut.eval();

                if (axil) {
                    REQUIRE(dut.request_ready == 1);
                    tick();  // Accept independent upstream channels.
                    dut.request = 0;
                    dut.eval();
                    if (destination >= 0) {
                        for (int cycle = 0; cycle < 8 && dut.selected == 0; ++cycle)
                            tick();
                    } else {
                        for (int cycle = 0; cycle < 8 && !dut.response_ready; ++cycle) {
                            REQUIRE(dut.selected == 0);
                            REQUIRE(dut.access == 0);
                            tick();
                        }
                    }
                }

                // Every scalar/array element has an independent, direction-
                // permitted select, including legal RO/WO address aliases.
                REQUIRE(dut.selected == selected_bit);
                REQUIRE(dut.access == ((!axil || write) ? selected_bit : 0u));
                REQUIRE(dut.writing == (write ? selected_bit : 0u));
                REQUIRE(dut.reading == (write ? 0u : selected_bit));
                if (destination >= 0) {
                    if (write) REQUIRE(dut.write_addr[destination] == address - bases[destination]);
                    else REQUIRE(dut.read_addr[destination] == address - bases[destination]);
                    REQUIRE(dut.response_ready == 0);
                    REQUIRE(dut.response_error == 0);
                }
                if (axil && destination >= 0) {
                    tick();  // The selected child's address/data handshake.
                    REQUIRE(dut.selected == 0);
                    REQUIRE(dut.access == 0);
                }

                if (destination < 0) {
                    // Local permission misses never need a child response and
                    // must retain their error while upstream is backpressured.
                    for (int cycle = 0; cycle < 3; ++cycle) {
                        REQUIRE(dut.response_ready == 1);
                        REQUIRE(dut.response_error == 1);
                        REQUIRE(dut.response_data == 0);
                        REQUIRE(dut.response_code == (axil ? 0b11 : 0b10));
                        if (axil) tick();
                    }
                } else {
                    // Probe each response source without retiring the head.
                    // A shared/collided fanin reference cannot pass this sweep.
                    for (responder = 0; responder < targets; ++responder) {
                        dut.target_ready = 1u << responder;
                        dut.eval();
                        REQUIRE(dut.response_ready == (responder == destination));
                        REQUIRE(dut.response_error == 0);
                        REQUIRE(dut.response_code == 0);
                        if (!write)
                            REQUIRE(dut.response_data == 0x51000000u + 0x101u * (destination + 1));
                    }

                    dut.target_ready = all_targets;
                    for (responder = 0; responder < targets; ++responder) {
                        dut.target_error = 1u << responder;
                        dut.eval();
                        REQUIRE(dut.response_ready == 1);
                        REQUIRE(dut.response_error == (responder == destination));
                        REQUIRE(dut.response_code == (responder == destination ? 0b10 : 0));
                        if (!write)
                            REQUIRE(dut.response_data == 0x51000000u + 0x101u * (destination + 1));
                    }

                    dut.target_error = 0;
                    if (!write) {
                        for (responder = 0; responder < targets; ++responder) {
                            for (int i = 0; i < targets; ++i) dut.target_data[i] = 0;
                            const uint32_t data = 0xa5000000u + 0x1001u * (responder + 1);
                            dut.target_data[responder] = data;
                            dut.eval();
                            REQUIRE(dut.response_ready == 1);
                            REQUIRE(dut.response_error == 0);
                            REQUIRE(dut.response_data == (responder == destination ? data : 0u));
                        }
                    }
                }

                if (axil) {
                    dut.response_accept = 1;
                    tick();
                }
                dut.request = 0;
                dut.response_accept = 0;
                dut.target_ready = 0;
                dut.target_error = 0;
                dut.eval();
                REQUIRE(dut.selected == 0);
                REQUIRE(dut.response_ready == 0);
                REQUIRE(dut.response_error == 0);
                REQUIRE(dut.response_data == 0);
            }
        }
    }
    dut.final();
    std::cout << "TARGET_NAMING_SUCCESS\n";
    return 0;
}
""".replace("BASES", ", ".join(hex(base) for base in bases)).replace(
        "NAMES", ", ".join(names)
    ).replace(
        "READABLE", ", ".join("true" if allowed else "false" for allowed in readable)
    ).replace(
        "WRITABLE", ", ".join("true" if allowed else "false" for allowed in writable)
    ).replace("IS_AXIL", "true" if protocol == "axi4lite" else "false")


def _compile_and_run(
    tmp_path: Path,
    verilator: str,
    protocol: str,
    interface: bool,
    rolled: bool,
    targets: tuple[tuple[str, int], ...] = TARGETS,
    permissions: tuple[tuple[bool, bool], ...] | None = None,
) -> None:
    wrapper_path = tmp_path / "target_naming_wrapper.sv"
    wrapper_path.write_text(_wrapper_source(protocol, interface, rolled, targets))
    cpp_path = tmp_path / "main.cpp"
    cpp_path.write_text(_cpp_source(protocol, rolled, targets, permissions))
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



@pytest.mark.verilator
@pytest.mark.parametrize("protocol,interface,cpuif_cls", EXPORTS[4:])
@pytest.mark.parametrize("rolled", [False, True], ids=["scalar", "rolled-array"])
def test_axi4lite_direction_permissions_and_aliases(
    tmp_path: Path, protocol: str, interface: bool, cpuif_cls: type, rolled: bool
) -> None:
    """Local direction misses and legal RO/WO aliases survive clocked queues."""
    verilator = shutil.which("verilator")
    assert verilator is not None, "These behavioral regressions require Verilator"
    array = "[2]" if rolled else ""
    stride = " += 0x4" if rolled else ""
    rdl_path = tmp_path / "target_naming.rdl"
    rdl_path.write_text(f"""
        reg read_t {{ field {{ sw=r; hw=w; }} payload[31:0]; }};
        reg write_t {{ field {{ sw=w; hw=r; }} payload[31:0]; }};
        reg ordinary_t {{ field {{ sw=rw; hw=r; }} payload[31:0]; }};
        addrmap target_naming {{
            read_t status{array} @ 0x100{stride};
            write_t command{array} @ 0x200{stride};
            read_t read_view{array} @ 0x300{stride};
            write_t write_view{array} @ 0x300{stride};
            ordinary_t ordinary{array} @ 0x400{stride};
        }};
    """)
    compiler = RDLCompiler()
    compiler.compile_file(str(rdl_path))
    root = compiler.elaborate()
    BusDecoderExporter().export(
        root, str(tmp_path), cpuif_cls=cpuif_cls, max_decode_depth=1,
        cpuif_unroll=False, address_width=11,
    )
    targets = (
        ("status", 0x100), ("command", 0x200),
        ("read_view", 0x300), ("write_view", 0x300), ("ordinary", 0x400),
    )
    permissions = ((True, False), (False, True), (True, False), (False, True), (True, True))
    _compile_and_run(tmp_path, verilator, protocol, interface, rolled, targets, permissions)
