"""Mathematical oracle properties and exhaustive APB4-flat RTL conformance.

The differential tests materialize expected decode tables from the independent
SystemRDL model, then compare every byte address and both transaction directions
in Verilator. Child responses vary independently of DUT outputs so stalls,
errors, readback muxing, and unselected response isolation are all exercised.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest
from systemrdl import RDLCompiler
from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb4 import APB4CpuifFlat
from tests.formal.reference_model import Direction, FormalBusDecoderModel, TargetElement

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "cocotb_lib" / "rdl"
VARIABLE_DEPTH_RDL = Path(__file__).resolve().parents[1] / "cocotb_lib" / "variable_depth.rdl"

NESTED_SUBMAP_RDL = """
reg word_t {
    field { sw=rw; hw=r; } payload[31:0];
};
addrmap outer_system {
    word_t outside @ 0x0;
    addrmap {
        word_t control @ 0x4;
        regfile {
            word_t words[3] @ 0x0 += 0x4;
        } odd_window @ 0x14;
        word_t trailing @ 0x30;
    } peripheral @ 0x100;
};
"""

WIDE_INTERNAL_RDL = """
addrmap wide_internal {
    reg {
        regwidth = 64;
        accesswidth = 32;
        field {
            sw = rw;
            hw = rw;
            onread = rclr;
        } payload[63:0];
    } wide @ 0x8;
    reg {
        field { sw=rw; hw=r; } payload[31:0];
    } trailing @ 0x18;
};
"""

REGISTER_TYPES_RDL = """
reg read_register_t {
    field { sw=r; hw=w; } payload[31:0];
};
reg write_register_t {
    field { sw=w; hw=r; } payload[31:0];
};
"""


def _register_permissions_rdl(write_first: bool) -> str:
    overlapping = ["read_register_t read_view @ 0x8;", "write_register_t write_view @ 0x8;"]
    if write_first:
        overlapping.reverse()
    return REGISTER_TYPES_RDL + """
        addrmap register_permissions {
    """ + "\n".join(overlapping) + """
            read_register_t status_only @ 0x10;
            write_register_t command_only @ 0x18;
        };
    """


ARRAY_REGISTER_PERMISSIONS_RDL = REGISTER_TYPES_RDL + """
addrmap register_array_permissions {
    read_register_t status[3] @ 0x8 += 0x8;
    write_register_t command[2] @ 0x28 += 0x10;
};
"""


def _compile_top(path: Path) -> AddrmapNode:
    compiler = RDLCompiler()
    compiler.compile_file(str(path))
    return compiler.elaborate().top


def _rdl_path(source: Path | str, tmp_path: Path) -> Path:
    if isinstance(source, Path):
        return source
    path = tmp_path / "scenario.rdl"
    path.write_text(dedent(source))
    return path


def compile_rdl(path: Path) -> FormalBusDecoderModel:
    return FormalBusDecoderModel(_compile_top(path))


class TestFormalModelAxioms:
    """Check interval, hierarchy, width, and direction semantics of the oracle."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            "simple.rdl",
            "multiple_reg.rdl",
            "deep_hierarchy.rdl",
            "wide_status.rdl",
            "asymmetric_bus.rdl",
            "array_only.rdl",
        ],
    )
    def test_disjointness_property(self, fixture_name: str) -> None:
        model = compile_rdl(FIXTURE_DIR / fixture_name)
        for direction in Direction:
            assert not model.check_disjointness(direction), (
                f"{direction.name} target conflicts in {fixture_name}"
            )

    @pytest.mark.parametrize("fixture_name", ["simple.rdl", "multiple_reg.rdl", "deep_hierarchy.rdl"])
    def test_completeness_and_boundary_property(self, fixture_name: str) -> None:
        """Every permitted byte in a target span hits it with a local offset."""
        model = compile_rdl(FIXTURE_DIR / fixture_name)
        for target in model.targets:
            for direction in Direction:
                if not target.permits(direction):
                    continue
                for address in range(target.rel_start, target.rel_end):
                    result = model.decode(address, direction)
                    assert result.hit == target
                    assert not result.is_error
                    assert result.local_offset == address - target.rel_start
                if target.rel_start > 0:
                    assert model.decode(target.rel_start - 1, direction).hit != target
                if target.rel_end < model.address_space_size:
                    assert model.decode(target.rel_end, direction).hit != target

    def test_variable_depth_monotonicity(self) -> None:
        top = _compile_top(VARIABLE_DEPTH_RDL)
        assert len(FormalBusDecoderModel(top, max_decode_depth=1).targets) == 1
        assert len(FormalBusDecoderModel(top, max_decode_depth=2).targets) == 2
        assert len(FormalBusDecoderModel(top, max_decode_depth=0).targets) == 3

    @pytest.mark.parametrize("internal_width,expected_width", [(None, 32), (16, 16), (64, 64)])
    def test_data_width_stops_at_external_boundary(
        self, tmp_path: Path, internal_width: int | None, expected_width: int
    ) -> None:
        internal_register = ""
        if internal_width is not None:
            internal_register = f"""
                reg {{
                    regwidth = {internal_width};
                    accesswidth = {internal_width};
                    field {{ sw=rw; hw=r; }} payload[{internal_width - 1}:0];
                }} visible @ 0x0;
            """
        source = f"""
            addrmap remote_map {{
                reg {{
                    regwidth = 128;
                    accesswidth = 128;
                    field {{ sw=rw; hw=r; }} payload[127:0];
                }} hidden @ 0x0;
            }};
            addrmap width_scope {{
                {internal_register}
                external remote_map opaque @ 0x100;
            }};
        """
        model = compile_rdl(_rdl_path(source, tmp_path))
        assert model.data_width == expected_width

    @pytest.mark.parametrize("write_first", [False, True], ids=["read-first", "write-first"])
    def test_register_permissions_and_legal_overlap(self, tmp_path: Path, write_first: bool) -> None:
        model = compile_rdl(_rdl_path(_register_permissions_rdl(write_first), tmp_path))
        for direction, target_name in ((Direction.READ, "read_view"), (Direction.WRITE, "write_view")):
            assert not model.check_disjointness(direction)
            for address in range(0x8, 0xC):
                result = model.decode(address, direction)
                assert result.hit is not None
                assert result.hit.target_name == target_name
                assert not result.is_error
                assert not result.competing_hits
                assert result.local_offset == address - 0x8
        for start, permitted, denied, target_name in (
            (0x10, Direction.READ, Direction.WRITE, "status_only"),
            (0x18, Direction.WRITE, Direction.READ, "command_only"),
        ):
            for address in range(start, start + 4):
                allowed = model.decode(address, permitted)
                assert allowed.hit is not None
                assert allowed.hit.target_name == target_name
                rejected = model.decode(address, denied)
                assert rejected.hit is None
                assert rejected.is_error
                assert rejected.local_offset is None


def _cpp_testbench(module_name: str, model: FormalBusDecoderModel) -> str:
    """Generate a driver for safe-named, depth-one, 32-bit APB4-flat targets."""
    assert model.max_decode_depth == 1
    assert model.data_width == 32
    target_indices = {target: index for index, target in enumerate(model.targets)}
    tables = []
    for direction in (Direction.READ, Direction.WRITE):
        rows = []
        for address in range(model.address_space_size):
            result = model.decode(address, direction)
            assert not result.competing_hits, f"Ambiguous oracle decode: {result}"
            child = -1 if result.hit is None else target_indices[result.hit]
            offset = 0 if result.local_offset is None else result.local_offset
            rows.append(f"        {{{child}, {offset}, {str(result.is_error).lower()}}}")
        tables.append("    {\n" + ",\n".join(rows) + "\n    }")
    expected_table = ",\n".join(tables)

    def signal(target: TargetElement, name: str) -> str:
        indices = "".join(f"[{index}]" for index in target.indices)
        return f"dut.m_apb_{target.target_name}_{name}{indices}"

    child_inputs = "\n".join(
        f"                    {signal(target, name)} = {values}[{index}];"
        for index, target in enumerate(model.targets)
        for name, values in (("PREADY", "child_ready"), ("PSLVERR", "child_error"), ("PRDATA", "child_data"))
    )
    selections = ", ".join(signal(target, "PSEL") for target in model.targets)
    enables = ", ".join(signal(target, "PENABLE") for target in model.targets)
    addresses = ", ".join(signal(target, "PADDR") for target in model.targets)
    return f"""
#include <cstdint>
#include <iostream>
#include "V{module_name}.h"
#include "verilated.h"

struct Expected {{
    int child;
    std::uint32_t local_address;
    bool error;
}};

static constexpr unsigned kAddressCount = {model.address_space_size};
static constexpr unsigned kChildCount = {len(model.targets)};
static constexpr Expected expected[2][kAddressCount] = {{
{expected_table}
}};

struct Phase {{
    const char* name;
    bool selected;
    bool enabled;
}};
static constexpr Phase phases[] = {{
    {{"idle", false, false}},
    {{"idle-enabled", false, true}},
    {{"setup", true, false}},
    {{"access", true, true}},
}};

static bool matches(const char* signal, std::uint32_t actual, std::uint32_t wanted,
                    unsigned address, unsigned direction, const char* phase,
                    unsigned profile, int child = -1) {{
    if (actual == wanted) return true;
    std::cerr << signal << " mismatch: address=0x" << std::hex << address
              << std::dec << " direction=" << (direction ? "write" : "read")
              << " phase=" << phase << " profile=" << profile << " child=" << child
              << " actual=0x" << std::hex << actual << " expected=0x" << wanted
              << std::dec << std::endl;
    return false;
}}

int main(int argc, char** argv) {{
    Verilated::commandArgs(argc, argv);
    V{module_name} dut;
    std::uint32_t child_ready[kChildCount];
    std::uint32_t child_error[kChildCount];
    std::uint32_t child_data[kChildCount];
    std::uint64_t vectors = 0;

    for (unsigned address = 0; address < kAddressCount; ++address) {{
        for (unsigned direction = 0; direction < 2; ++direction) {{
            const Expected& oracle = expected[direction][address];
            dut.s_apb_PADDR = address;
            dut.s_apb_PWRITE = direction;
            dut.s_apb_PWDATA = 0x13579BDFu ^ address;
            dut.s_apb_PSTRB = 0xFu;
            dut.s_apb_PPROT = 0;
            for (const Phase& phase : phases) {{
                dut.s_apb_PSEL = phase.selected;
                dut.s_apb_PENABLE = phase.enabled;
                for (unsigned profile = 0; profile < 4; ++profile) {{
                    // Every child sees all four ready/error combinations. Other
                    // children deliberately respond even while unselected.
                    for (unsigned child = 0; child < kChildCount; ++child) {{
                        const unsigned state = (profile + child) & 3u;
                        child_ready[child] = state >> 1;
                        child_error[child] = state & 1u;
                        child_data[child] = (0x9E3779B9u * (child + 1u))
                            ^ (address * 0x01010101u) ^ (profile * 0x00102041u);
                    }}
{child_inputs}
                    dut.eval();
                    const std::uint32_t selected[] = {{{selections}}};
                    const std::uint32_t enabled[] = {{{enables}}};
                    const std::uint32_t local_address[] = {{{addresses}}};
                    const int selected_child = phase.selected ? oracle.child : -1;
                    for (unsigned child = 0; child < kChildCount; ++child) {{
                        const bool hit = static_cast<int>(child) == selected_child;
                        if (!matches("child PSEL", selected[child], hit,
                                     address, direction, phase.name, profile, child)
                            || !matches("child PENABLE", enabled[child], hit && phase.enabled,
                                        address, direction, phase.name, profile, child)) return 1;
                        // Unselected addresses are unspecified; selected addresses
                        // must be local offsets, including non-power-of-two spans.
                        if (hit && !matches("child PADDR", local_address[child], oracle.local_address,
                                            address, direction, phase.name, profile, child)) return 1;
                    }}

                    std::uint32_t ready = 0;
                    std::uint32_t error = 0;
                    std::uint32_t data = 0;
                    if (phase.selected) {{
                        if (oracle.error) {{
                            // Only locally generated errors are access-gated.
                            ready = phase.enabled;
                            error = phase.enabled;
                        }} else {{
                            // Mapped responses pass through even during setup or
                            // a child stall; do not infer them from DUT selects.
                            ready = child_ready[oracle.child];
                            error = child_error[oracle.child];
                            if (direction == 0) data = child_data[oracle.child];
                        }}
                    }}
                    if (!matches("slave PREADY", dut.s_apb_PREADY, ready,
                                 address, direction, phase.name, profile)
                        || !matches("slave PSLVERR", dut.s_apb_PSLVERR, error,
                                    address, direction, phase.name, profile)
                        || !matches("slave PRDATA", dut.s_apb_PRDATA, data,
                                    address, direction, phase.name, profile)) return 1;
                    ++vectors;
                }}
            }}
        }}
    }}
    dut.final();
    std::cout << "ORACLE_SWEEP_OK " << vectors << std::endl;
    return 0;
}}
"""


@pytest.mark.simulation
@pytest.mark.verilator
class TestRtlFormalEquivalence:
    """One differential harness, with all expected address decisions from decode()."""

    @pytest.mark.parametrize(
        "source,export_child",
        [
            pytest.param(FIXTURE_DIR / "simple.rdl", None, id="simple"),
            pytest.param(FIXTURE_DIR / "multiple_reg.rdl", None, id="multiple-registers"),
            pytest.param(FIXTURE_DIR / "array_only.rdl", None, id="array-stride-gaps"),
            pytest.param(NESTED_SUBMAP_RDL, "peripheral", id="nested-export-nonpower-two"),
            pytest.param(WIDE_INTERNAL_RDL, None, id="wide-internal-side-effects"),
            pytest.param(_register_permissions_rdl(False), None, id="register-overlap-read-first"),
            pytest.param(_register_permissions_rdl(True), None, id="register-overlap-write-first"),
            pytest.param(ARRAY_REGISTER_PERMISSIONS_RDL, None, id="array-register-permissions"),
        ],
    )
    def test_verilator_oracle_sweep(
        self, tmp_path: Path, source: Path | str, export_child: str | None
    ) -> None:
        verilator = shutil.which("verilator")
        if verilator is None:
            pytest.skip("Verilator is required for RTL/oracle conformance")

        top = _compile_top(_rdl_path(source, tmp_path))
        if export_child is not None:
            child = top.get_child_by_name(export_child)
            assert isinstance(child, AddrmapNode)
            top = child
        model = FormalBusDecoderModel(top, max_decode_depth=1)
        BusDecoderExporter().export(
            top, str(tmp_path), cpuif_cls=APB4CpuifFlat, max_decode_depth=1, cpuif_unroll=False
        )
        module_name = top.inst_name
        cpp_path = tmp_path / "main.cpp"
        cpp_path.write_text(_cpp_testbench(module_name, model))
        build = subprocess.run(
            [
                verilator, "--cc", "--exe", "--build",
                "-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSEDPARAM", "-Wno-UNUSEDSIGNAL", "-Wno-GENUNNAMED",
                "--top-module", module_name,
                "-Mdir", str(tmp_path / "obj_dir"),
                "-o", "sim",
                str(tmp_path / f"{module_name}_pkg.sv"),
                str(tmp_path / f"{module_name}.sv"),
                str(cpp_path),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert build.returncode == 0, f"Verilator compilation failed:\n{build.stdout}\n{build.stderr}"
        simulation = subprocess.run(
            [str(tmp_path / "obj_dir" / "sim")], capture_output=True, text=True, timeout=60
        )
        assert simulation.returncode == 0, (
            f"RTL/oracle mismatch in {module_name}:\n{simulation.stdout}\n{simulation.stderr}"
        )
        assert f"ORACLE_SWEEP_OK {model.address_space_size * 2 * 4 * 4}" in simulation.stdout
