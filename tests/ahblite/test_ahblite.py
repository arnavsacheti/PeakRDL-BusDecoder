"""Executable AHB-Lite contract tests, independent of generated selector logic.

Run with ``PYTHONPATH=src python -m pytest tests/ahblite -v``.  The simulation
matrix compiles the exported RTL with Verilator and runs a C++ cycle scoreboard;
it does not search generated source for implementation-shaped assertions.

Both port forms and array modes run against 32-bit memory targets and 64-bit
block targets exported from a nonzero-address submap, plus nested multidimensional
arrays, a dense array filling its minimum-width address space, and overlapping
read-only/write-only register apertures. The scoreboard covers pipeline overlap,
byte lanes, stalls, bubbles, misses, permissions, errors and reset.
These are finite behavioral checks, not a formal proof or AHB certification.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from systemrdl import RDLCompileError
from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.ahblite import AHBLiteCpuif, AHBLiteCpuifFlat

_REPO = Path(__file__).resolve().parents[2]
_SCOREBOARD = Path(__file__).with_name("ahblite_scoreboard.cpp")

# Independent public bus description, not extracted from the exporter or RTL.
# (name, width, input at the router's subordinate port)
_SIGNALS = (
    ("HSEL", 1, True),
    ("HREADY", 1, True),
    ("HADDR", 16, True),
    ("HTRANS", 2, True),
    ("HWRITE", 1, True),
    ("HSIZE", 3, True),
    ("HBURST", 3, True),
    ("HPROT", 4, True),
    ("HMASTLOCK", 1, True),
    ("HWDATA", "data", True),
    ("HRDATA", "data", False),
    ("HREADYOUT", 1, False),
    ("HRESP", 1, False),
)


def _range(width: int) -> str:
    return "" if width == 1 else f"[{width - 1}:0] "


def _fixture_rdl(
    *, local_submap: bool, data_width: int, nested: bool = False, dense: bool = False,
    register_overlap: bool = False, colliding: bool = False, reserved_min: bool = False,
) -> str:
    if register_overlap:
        # An 8192-bit register is exactly 1 KiB; its narrow present field allows
        # legal RO/WO aliasing while accesswidth remains a 32-bit AHB bus.
        return """
        reg read_t {
            regwidth=8192; accesswidth=32;
            field { sw=r; hw=w; } data[31:0];
        };
        reg write_t {
            regwidth=8192; accesswidth=32;
            field { sw=w; hw=r; } data[31:0];
        };
        addrmap ahb_cycle_map {
            read_t a @ 0;
            write_t b @ 0;
            read_t bank[2] @ 0x1000 += 0x800;
        };
        """
    if data_width == 32 and not nested and not colliding:
        target = """
        mem target_t {
            mementries = 256;
            memwidth = 32;
        };
        """
        external = "external "
    else:
        # Its last register makes the block exactly 1 KiB, not an implicitly
        # widened small map. Regfiles are internal by default, unlike child
        # addrmaps: the scanner must see these registers and depth-two leaves.
        target = f"""
        regfile target_t {{
            reg {{
                regwidth = {data_width};
                accesswidth = {data_width};
                field {{ sw = rw; hw = r; }} data[{data_width - 1}:0];
            }} last_word @ {0x400 - data_width // 8};
        }};
        """
        external = ""
    if colliding:
        source = target + """
        regfile parent_t { target_t leaf @ 0; };
        addrmap ahb_cycle_map {
            parent_t left @ 0;
            parent_t right @ 0x800;
            parent_t bank[2] @ 0x1000 += 0x800;
        };
        """
    elif dense:
        source = target + f"""
        addrmap ahb_cycle_map {{
            {external}target_t bank[4] @ 0 += 0x400;
        }};
        """
    elif nested:
        source = target + f"""
        regfile outer_t {{
            {external}target_t leaf[2][1] @ 0 += 0x800;
        }};
        addrmap ahb_cycle_map {{
            outer_t cluster[2] @ 0 += 0x1000;
        }};
        """
    else:
        source = target + f"""
        addrmap ahb_cycle_map {{
            {external}target_t {"MIN" if reserved_min else "a"} @ 0x0000;
            {external}target_t b @ 0x0800;
            {external}target_t bank[2] @ 0x1000 += 0x800;
        }};
        """
    if local_submap:
        source += "addrmap enclosing_map { ahb_cycle_map peripheral @ 0x4000; };"
    return source


def _wrapper(
    *, interface: bool, unroll: bool, data_width: int, nested: bool,
    dense: bool, address_width: int, colliding: bool = False, reserved_min: bool = False,
    upstream_address_width: int | None = None, upstream_data_width: int | None = None,
    child_address_width: int = 10, child_data_width: int | None = None,
) -> str:
    """Adapt only public port syntax to one fixed, independently defined DUT ABI."""
    ports = ["input logic HCLK", "input logic HRESETn"]
    for signal, raw_width, subordinate_input in _SIGNALS:
        width = data_width if raw_width == "data" else raw_width
        if signal == "HADDR":
            width = address_width
        direction = "input" if subordinate_input else "output"
        ports.append(f"{direction} logic {_range(width)}{signal}")
    for signal, raw_width, subordinate_input in _SIGNALS:
        width = data_width if raw_width == "data" else raw_width
        if signal == "HADDR":
            width = 10  # Every target fixture has an exact 0x400-byte aperture.
        direction = "output" if subordinate_input else "input"
        ports.append(f"{direction} logic {_range(width)}child_{signal} [4]")

    declarations: list[str] = []
    wiring: list[str] = []
    connections: list[str] = []
    if interface:
        declarations.append(
            f"ahblite_intf #(.ADDR_WIDTH({upstream_address_width or address_width}), "
            f".DATA_WIDTH({upstream_data_width or data_width})) "
            "upstream (.HCLK(HCLK), .HRESETn(HRESETn));"
        )
        connections.append(".s_ahb(upstream)")
        for signal, _, subordinate_input in _SIGNALS:
            lhs, rhs = (f"upstream.{signal}", signal) if subordinate_input else (
                signal, f"upstream.{signal}"
            )
            wiring.append(f"assign {lhs} = {rhs};")
    else:
        connections.extend((".s_ahb_HCLK(HCLK)", ".s_ahb_HRESETn(HRESETn)"))
        connections.extend(f".s_ahb_{signal}({signal})" for signal, _, _ in _SIGNALS)

    # All fixture shapes have four exact 1-KiB apertures. Connectivity is
    # explicit and never obtained by traversing exporter-generated targets.
    if dense:
        groups = [("bank", (4,), [((index,), index) for index in range(4)])]
    elif nested:
        groups = [(
            "leaf", (2, 2, 1),
            [((outer, inner, 0), outer * 2 + inner) for outer in range(2) for inner in range(2)],
        )]
    elif colliding:
        groups = [
            ("left_leaf", (), [((), 0)]),
            ("right_leaf", (), [((), 1)]),
            ("bank_leaf", (2,), [((0,), 2), ((1,), 3)]),
        ]
    else:
        groups = [
            ("MIN__2" if reserved_min else "a", (), [((), 0)]),
            ("b", (), [((), 1)]),
            ("bank", (2,), [((0,), 2), ((1,), 3)]),
        ]
    port_groups = []
    for name, dimensions, locations in groups:
        if unroll and dimensions:
            for index, endpoint_id in locations:
                suffix = "_" + "_".join(map(str, index))
                port_groups.append((name, suffix, (), [((), endpoint_id)]))
        else:
            port_groups.append((name, "", dimensions, locations))

    for name, suffix, dimensions, locations in port_groups:
        variable = f"bus_{name}{suffix}"
        dimension = "".join(f" [{size}]" for size in dimensions)
        if interface:
            declarations.append(
                f"ahblite_intf #(.ADDR_WIDTH({child_address_width}), "
                f".DATA_WIDTH({child_data_width or data_width})) "
                f"{variable}{dimension} (.HCLK(HCLK), .HRESETn(HRESETn));"
            )
            connections.append(f".m_ahb_{name}{suffix}({variable})")
        for signal, raw_width, subordinate_input in _SIGNALS:
            width = data_width if raw_width == "data" else raw_width
            if signal == "HADDR":
                width = 10
            if not interface:
                declarations.append(f"wire {_range(width)}{variable}_{signal}{dimension};")
                connections.append(f".m_ahb_{name}_{signal}{suffix}({variable}_{signal})")
            for indices, endpoint_id in locations:
                index = "".join(f"[{element}]" for element in indices)
                bus_signal = (
                    f"{variable}{index}.{signal}" if interface
                    else f"{variable}_{signal}{index}"
                )
                child_signal = f"child_{signal}[{endpoint_id}]"
                lhs, rhs = (child_signal, bus_signal) if subordinate_input else (
                    bus_signal, child_signal
                )
                wiring.append(f"assign {lhs} = {rhs};")

    return (
        "module ahb_scoreboard_wrapper (\n    " + ",\n    ".join(ports) + "\n);\n"
        + "\n".join(declarations) + "\n" + "\n".join(wiring)
        + "\nahb_router dut (\n    " + ",\n    ".join(connections) + "\n);\nendmodule\n"
    )


def _run(command: list[str], *, cwd: Path, timeout: int) -> str:
    result = subprocess.run(
        command, cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=timeout, check=False,
    )
    assert result.returncode == 0, f"Command failed: {' '.join(command)}\n{result.stdout}"
    return result.stdout


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize("interface", [False, True], ids=["flat", "interface"])
@pytest.mark.parametrize("unroll", [False, True], ids=["rolled", "unrolled"])
@pytest.mark.parametrize(
    "fixture",
    ["memory-root32", "block-submap64", "nested-multidim32",
     "minimum-width-array32", "register-overlap32", "depth-zero-memory32",
     "colliding-block-names32", "reserved-min-name32"],
)
def test_generated_ahblite_cycle_scoreboard(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path,
    interface: bool, unroll: bool, fixture: str,
) -> None:
    verilator = shutil.which("verilator")
    if verilator is None:
        pytest.skip("Verilator is required for the AHB-Lite behavioral RTL tests")
    local_submap = fixture == "block-submap64"
    data_width = 64 if local_submap else 32
    nested = fixture == "nested-multidim32"
    dense = fixture == "minimum-width-array32"
    register_overlap = fixture == "register-overlap32"
    colliding = fixture == "colliding-block-names32"
    reserved_min = fixture == "reserved-min-name32"
    depth = 0 if fixture == "depth-zero-memory32" else 2 if nested or colliding else 1
    top = compile_rdl(
        _fixture_rdl(
            local_submap=local_submap, data_width=data_width, nested=nested, dense=dense,
            register_overlap=register_overlap, colliding=colliding, reserved_min=reserved_min,
        ),
        top="enclosing_map" if local_submap else "ahb_cycle_map",
    )
    if local_submap:
        top = top.find_by_path("peripheral")
        assert isinstance(top, AddrmapNode)
    address_width = 12 if dense else 16
    BusDecoderExporter().export(
        top, str(tmp_path),
        cpuif_cls=AHBLiteCpuif if interface else AHBLiteCpuifFlat,
        cpuif_unroll=unroll, address_width=address_width, max_decode_depth=depth,
        module_name="ahb_router", package_name="ahb_router_pkg",
    )
    wrapper = tmp_path / "ahb_scoreboard_wrapper.sv"
    wrapper.write_text(_wrapper(
        interface=interface, unroll=unroll, data_width=data_width, nested=nested,
        dense=dense, address_width=address_width, colliding=colliding, reserved_min=reserved_min,
    ))
    sources = [tmp_path / "ahb_router_pkg.sv", tmp_path / "ahb_router.sv", wrapper]
    if interface:
        sources.insert(0, _REPO / "hdl-src" / "ahblite_intf.sv")
    obj_dir = tmp_path / "obj_dir"
    command = [
        verilator, "--cc", "--exe", "--build", "--assert",
        "--top-module", "ahb_scoreboard_wrapper",
        "--Mdir", str(obj_dir), "-o", "ahblite_scoreboard", "-j", "1",
        "-Wall", "-Wno-fatal", "-Wno-DECLFILENAME", "-Wno-UNUSEDPARAM",
        "-Wno-UNUSEDSIGNAL", "-Wno-GENUNNAMED",
        "-CFLAGS", (
            f"-std=c++17 -DTEST_DATA_WIDTH={data_width} -DTEST_DENSE_ARRAY={int(dense)} "
            f"-DTEST_REGISTER_OVERLAP={int(register_overlap)}"
        ),
        *(str(path) for path in sources), str(_SCOREBOARD),
    ]
    _run(command, cwd=tmp_path, timeout=240)
    output = _run([str(obj_dir / "ahblite_scoreboard")], cwd=tmp_path, timeout=30)
    assert "AHB-Lite independent cycle scoreboard PASS" in output


_INVALID_APERTURES = [
    pytest.param(
        "mem target_t { mementries=128; memwidth=32; }; "
        "addrmap invalid_map { external target_t a @ 0; };", 1,
        id="half-kib-size",
    ),
    pytest.param(
        "mem target_t { mementries=384; memwidth=32; }; "
        "addrmap invalid_map { external target_t a @ 0; };", 1,
        id="non-kib-multiple-size",
    ),
    pytest.param(
        "mem target_t { mementries=256; memwidth=32; }; "
        "addrmap invalid_map { external target_t a @ 0x200; };", 1,
        id="misaligned-base",
    ),
    pytest.param(
        "mem target_t { mementries=256; memwidth=32; }; "
        "addrmap invalid_map { external target_t bank[2] @ 0 += 0x600; };", 1,
        id="misaligned-array-stride",
    ),
    pytest.param(
        "regfile leaf_t { reg { field { sw=rw; hw=r; } data[31:0]; } last @ 0x3fc; }; "
        "regfile outer_t { leaf_t leaf[2][1] @ 0 += 0x800; }; "
        "addrmap invalid_map { outer_t cluster[2] @ 0 += 0x1200; };", 2,
        id="misaligned-ancestor-array-stride",
    ),
    pytest.param(
        "regfile target_t { reg { field { sw=rw; hw=r; } value[31:0]; } last @ 0x3fc; }; "
        "addrmap invalid_map { target_t a @ 0; };", 0,
        id="leaf-register-depth",
    ),
]


@pytest.mark.parametrize("cpuif_cls", [AHBLiteCpuifFlat, AHBLiteCpuif], ids=["flat", "interface"])
@pytest.mark.parametrize(("rdl", "depth"), _INVALID_APERTURES)
def test_ahblite_rejects_non_kib_targets_with_diagnostics(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path,
    capsys: pytest.CaptureFixture[str], cpuif_cls: type, rdl: str, depth: int,
) -> None:
    top = compile_rdl(rdl, top="invalid_map")
    with pytest.raises(RDLCompileError) as error:
        BusDecoderExporter().export(
            top, str(tmp_path), cpuif_cls=cpuif_cls, max_decode_depth=depth,
        )
    captured = capsys.readouterr()
    diagnostic = f"{error.value}\n{captured.out}\n{captured.err}"
    assert "AHB" in diagnostic
    assert any(text in diagnostic.lower() for text in ("1kib", "1 kib", "1024", "0x400"))


@pytest.mark.parametrize("cpuif_cls", [AHBLiteCpuifFlat, AHBLiteCpuif], ids=["flat", "interface"])
def test_ahblite_accepts_explicit_kib_and_larger_blocks(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path, cpuif_cls: type,
) -> None:
    top = compile_rdl("""
        regfile block_t {
            reg { field { sw=rw; hw=r; } data[31:0]; } last @ 0x3fc;
        };
        mem large_t { mementries=512; memwidth=32; };
        addrmap valid_map {
            block_t a @ 0;
            external large_t b @ 0x800;
        };
    """, top="valid_map")
    BusDecoderExporter().export(top, str(tmp_path), cpuif_cls=cpuif_cls)


@pytest.mark.parametrize("cpuif_cls", [AHBLiteCpuifFlat, AHBLiteCpuif], ids=["flat", "interface"])
def test_ahblite_rejects_narrow_data_width(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path, cpuif_cls: type,
    capsys: pytest.CaptureFixture[str],
) -> None:
    top = compile_rdl("""
        regfile block_t {
            reg {
                regwidth=16; accesswidth=16;
                field { sw=rw; hw=r; } data[15:0];
            } last @ 0x3fe;
        };
        addrmap narrow_map { block_t a @ 0; };
    """, top="narrow_map")
    with pytest.raises(RDLCompileError) as error:
        BusDecoderExporter().export(top, str(tmp_path), cpuif_cls=cpuif_cls)
    captured = capsys.readouterr()
    diagnostic = f"{error.value}\n{captured.out}\n{captured.err}"
    assert "AHB" in diagnostic and "32" in diagnostic


@pytest.mark.parametrize("cpuif_cls", [AHBLiteCpuifFlat, AHBLiteCpuif], ids=["flat", "interface"])
def test_ahblite_rejects_address_width_that_cannot_represent_apertures(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path, cpuif_cls: type,
) -> None:
    top = compile_rdl(_fixture_rdl(local_submap=False, data_width=32), top="ahb_cycle_map")
    with pytest.raises(RDLCompileError, match="address width"):
        BusDecoderExporter().export(top, str(tmp_path), cpuif_cls=cpuif_cls, address_width=12)


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize(
    ("endpoint", "signal", "width"),
    [
        ("upstream", "address", 15),
        ("upstream", "data", 64),
        ("child", "address", 9),
        ("child", "data", 64),
    ],
)
def test_ahblite_interface_width_contract_is_enforced(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path,
    endpoint: str, signal: str, width: int,
) -> None:
    """Wrong real SV-interface widths must fail at runtime, not silently truncate."""
    verilator = shutil.which("verilator")
    if verilator is None:
        pytest.skip("Verilator is required for the AHB-Lite behavioral RTL tests")
    top = compile_rdl(_fixture_rdl(local_submap=False, data_width=32), top="ahb_cycle_map")
    BusDecoderExporter().export(
        top, str(tmp_path), cpuif_cls=AHBLiteCpuif, address_width=16,
        module_name="ahb_router", package_name="ahb_router_pkg",
    )
    override = {f"{endpoint}_{signal}_width": width}
    wrapper = tmp_path / "ahb_scoreboard_wrapper.sv"
    wrapper.write_text(_wrapper(
        interface=True, unroll=False, data_width=32, nested=False,
        dense=False, address_width=16, **override,
    ))
    obj_dir = tmp_path / "obj_dir"
    _run([
        verilator, "--binary", "--assert", "--top-module", "ahb_scoreboard_wrapper",
        "--Mdir", str(obj_dir), "-o", "ahb_width_contract", "-j", "1",
        "-Wall", "-Wno-fatal", "-Wno-DECLFILENAME", "-Wno-UNUSEDPARAM",
        "-Wno-UNUSEDSIGNAL", "-Wno-GENUNNAMED",
        str(_REPO / "hdl-src" / "ahblite_intf.sv"),
        str(tmp_path / "ahb_router_pkg.sv"), str(tmp_path / "ahb_router.sv"), str(wrapper),
    ], cwd=tmp_path, timeout=240)
    result = subprocess.run(
        [str(obj_dir / "ahb_width_contract")], cwd=tmp_path, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30, check=False,
    )
    assert result.returncode != 0, "Mismatched interface widths unexpectedly ran successfully"
    assert "incompatible address/data widths" in result.stdout
    assert ("s_ahb" if endpoint == "upstream" else "m_ahb_") in result.stdout


@pytest.mark.parametrize("cpuif_cls", [AHBLiteCpuifFlat, AHBLiteCpuif], ids=["flat", "interface"])
def test_ahblite_rejects_ambiguous_unrolled_public_ports(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path,
    capsys: pytest.CaptureFixture[str], cpuif_cls: type,
) -> None:
    """An array index suffix must not silently alias a literal target name."""
    top = compile_rdl("""
        mem target_t { mementries=256; memwidth=32; };
        addrmap ambiguous_ports {
            external target_t bank[2] @ 0 += 0x400;
            external target_t bank_0 @ 0x800;
        };
    """, top="ambiguous_ports")
    with pytest.raises(RDLCompileError) as error:
        BusDecoderExporter().export(
            top, str(tmp_path), cpuif_cls=cpuif_cls, cpuif_unroll=True,
        )
    captured = capsys.readouterr()
    diagnostic = f"{error.value}\n{captured.out}\n{captured.err}"
    assert "collide" in diagnostic
    assert "m_ahb_bank_0" in diagnostic
