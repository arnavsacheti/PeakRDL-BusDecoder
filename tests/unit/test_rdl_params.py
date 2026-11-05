"""Parameter extraction/public-layout contracts and finite generated-RTL behavior."""

from collections.abc import Callable
from pathlib import Path
import shutil
import subprocess

import pytest

from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter, ParameterUsage, RdlParameterExtractor
from peakrdl_busdecoder.cpuif.apb.apb_cpuif import APB4Cpuif, APB4CpuifFlat


class TestRdlParameterExtractor:
    """Tests for RdlParameterExtractor.extract()."""

    def test_no_parameters(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """An addrmap with no parameters should produce an empty list."""
        rdl = """
        addrmap no_params {
            reg { field { sw=rw; hw=r; } data[31:0]; } r0 @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="no_params")
        extractor = RdlParameterExtractor(top)
        params = extractor.extract()
        assert params == []

    def test_non_address_parameter_ignored(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """A parameter that doesn't affect array dimensions is ignored."""
        rdl = """
        addrmap direct_param #(longint unsigned RESET_VAL = 42) {
            reg {
                field { sw=rw; hw=r; reset=RESET_VAL; } data[31:0];
            } r0 @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="direct_param")
        extractor = RdlParameterExtractor(top)
        params = extractor.extract()
        assert params == []

    def test_address_modifying_parameter(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """A parameter used as an array dimension should be ADDRESS_MODIFYING."""
        rdl = """
        addrmap array_param #(longint unsigned N_CHANNELS = 4) {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } channel[N_CHANNELS] @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="array_param")
        extractor = RdlParameterExtractor(top)
        params = extractor.extract()
        assert len(params) == 1
        p = params[0]
        assert p.name == "N_CHANNELS"
        assert p.value == 4
        assert p.usage == ParameterUsage.ADDRESS_MODIFYING
        assert len(p.array_enables) == 1
        ae = p.array_enables[0]
        assert ae.max_elements == 4
        assert ae.dimension_index == 0

    def test_mixed_parameters_only_address_modifying(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """Only address-modifying params are extracted; others are ignored."""
        rdl = """
        addrmap mixed_params #(
            longint unsigned N_ENGINES = 3,
            longint unsigned DEFAULT_MODE = 7
        ) {
            reg {
                field { sw=rw; hw=r; reset=DEFAULT_MODE; } mode[7:0];
            } engine_ctrl[N_ENGINES] @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="mixed_params")
        extractor = RdlParameterExtractor(top)
        params = extractor.extract()
        assert len(params) == 1

        p = params[0]
        assert p.name == "N_ENGINES"
        assert p.usage == ParameterUsage.ADDRESS_MODIFYING
        assert p.value == 3
        assert len(p.array_enables) == 1

    def test_same_value_non_array_param_not_misclassified(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """A non-array parameter sharing the same value must stay DIRECT."""
        rdl = """
        addrmap collision_params #(
            longint unsigned N_UNUSED = 4,
            longint unsigned N_REAL = 4
        ) {
            reg {
                field { sw=rw; hw=r; reset=N_UNUSED; } cfg[31:0];
            } cfg @ 0x0;

            reg {
                field { sw=rw; hw=r; } data[31:0];
            } regs[N_REAL] @ 0x10;
        };
        """
        top = compile_rdl(rdl, top="collision_params")
        params = RdlParameterExtractor(top).extract()

        assert len(params) == 1
        assert params[0].name == "N_REAL"

    def test_expression_dimension_not_matched(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """A parameter used in an expression (N*2) for an array dimension
        is not matched because the elaborated dim (8) != param value (4).
        This documents a known limitation of value-based matching."""
        rdl = """
        addrmap expr_dim #(longint unsigned N = 4) {
            reg { field { sw=rw; hw=r; } data[31:0]; } regs[N * 2] @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="expr_dim")
        extractor = RdlParameterExtractor(top)
        params = extractor.extract()
        # N=4, dim=8 (N*2): value match fails, so no ADDRESS_MODIFYING param found
        assert params == []

    def test_one_param_controls_two_arrays(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """A single parameter driving two separate arrays should produce
        one RdlParameter with two ArrayEnableInfo entries."""
        rdl = """
        addrmap multi_array #(longint unsigned N = 4) {
            reg { field { sw=rw; hw=r; } d1[31:0]; } regs[N] @ 0x0;
            reg { field { sw=rw; hw=r; } d2[31:0]; } data[N] @ 0x100;
        };
        """
        top = compile_rdl(rdl, top="multi_array")
        extractor = RdlParameterExtractor(top)
        params = extractor.extract()
        assert len(params) == 1
        p = params[0]
        assert p.name == "N"
        assert len(p.array_enables) == 2
        paths = {ae.node_path for ae in p.array_enables}
        assert "regs[]" in paths
        assert "data[]" in paths


class TestRdlParameterSvProperties:
    """Tests for SV type/value rendering."""

    def test_int_param_sv_type(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        rdl = """
        addrmap sv_int #(longint unsigned N = 10) {
            reg { field { sw=rw; hw=r; } d[31:0]; } regs[N] @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="sv_int")
        params = RdlParameterExtractor(top).extract()
        assert len(params) == 1
        assert params[0].sv_type == "int"
        assert params[0].sv_value == "10"


class TestRdlParameterIntegration:
    """Tests for end-to-end parameter integration in the exporter."""

    def test_non_address_param_not_in_module(
        self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
    ) -> None:
        """Non-address parameters should NOT appear in the generated module."""
        rdl = """
        addrmap direct_test #(longint unsigned MY_RESET = 0xFF) {
            reg { field { sw=rw; hw=r; reset=MY_RESET; } data[31:0]; } r0 @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="direct_test")
        exporter = BusDecoderExporter()
        exporter.export(top, str(tmp_path), cpuif_cls=APB4Cpuif, parametrize=True)

        module = (tmp_path / "direct_test.sv").read_text()
        assert "MY_RESET" not in module


    def test_enable_param_max_in_package(
        self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
    ) -> None:
        """Package should contain the MAX constant for enable parameters."""
        rdl = """
        addrmap pkg_test #(longint unsigned N_CH = 6) {
            reg { field { sw=rw; hw=r; } data[31:0]; } ch[N_CH] @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="pkg_test")
        exporter = BusDecoderExporter()
        exporter.export(top, str(tmp_path), cpuif_cls=APB4Cpuif, parametrize=True)

        package = (tmp_path / "pkg_test_pkg.sv").read_text()
        assert "PKG_TEST_MAX_N_CH = 6" in package

    def test_no_params_unchanged(
        self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
    ) -> None:
        """Designs without parameters should generate unchanged output."""
        rdl = """
        addrmap no_param {
            reg { field { sw=rw; hw=r; } data[31:0]; } r0 @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="no_param")
        exporter = BusDecoderExporter()
        exporter.export(top, str(tmp_path), cpuif_cls=APB4Cpuif, parametrize=True)

        module = (tmp_path / "no_param.sv").read_text()
        assert "module no_param" in module
        # No parameter constraints section
        assert "Parameter constraints" not in module

    def test_struct_uses_max_dimension(
        self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
    ) -> None:
        """The struct should use the static max N for array dimensions,
        not the parameter name, since struct sizes must be static."""
        rdl = """
        addrmap struct_test #(longint unsigned N_ITEMS = 5) {
            reg { field { sw=rw; hw=r; } data[31:0]; } items[N_ITEMS] @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="struct_test")
        exporter = BusDecoderExporter()
        exporter.export(top, str(tmp_path), cpuif_cls=APB4Cpuif, parametrize=True)

        module = (tmp_path / "struct_test.sv").read_text()
        # The struct member should use the static max dimension
        assert "items[5]" in module

    def test_enable_param_replaces_localparam(
        self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
    ) -> None:
        """When an RDL enable parameter covers an array, the redundant
        localparam N_<NAME>S is replaced by the proper SV parameter."""
        rdl = """
        addrmap replaced_test #(longint unsigned N_CH = 4) {
            reg { field { sw=rw; hw=r; } data[31:0]; } ch[N_CH] @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="replaced_test")
        exporter = BusDecoderExporter()
        exporter.export(top, str(tmp_path), cpuif_cls=APB4Cpuif, parametrize=True)

        module = (tmp_path / "replaced_test.sv").read_text()
        # The RDL parameter replaces the auto-generated localparam
        assert "parameter int N_CH = 4" in module
        assert "localparam N_CHS = 4" not in module

    def test_non_param_array_keeps_localparam(
        self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
    ) -> None:
        """Arrays NOT driven by an RDL parameter should still get the
        auto-generated localparam N_<NAME>S."""
        rdl = """
        addrmap kept_test {
            reg { field { sw=rw; hw=r; } data[31:0]; } regs[4] @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="kept_test")
        exporter = BusDecoderExporter()
        exporter.export(top, str(tmp_path), cpuif_cls=APB4Cpuif, parametrize=True)

        module = (tmp_path / "kept_test.sv").read_text()
        assert "localparam N_REGSS = 4" in module


    def test_parametrize_off_produces_static_output(
        self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
    ) -> None:
        """When parametrize=False (default), RDL params are ignored; output is static."""
        rdl = """
        addrmap static_test #(longint unsigned N_CH = 4) {
            reg { field { sw=rw; hw=r; } data[31:0]; } ch[N_CH] @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="static_test")
        exporter = BusDecoderExporter()
        exporter.export(top, str(tmp_path), cpuif_cls=APB4Cpuif)

        module = (tmp_path / "static_test.sv").read_text()
        assert "parameter int N_CH" not in module
        assert "N_CH >= 0" not in module
        package = (tmp_path / "static_test_pkg.sv").read_text()
        assert "MAX_N_CH" not in package


_PARAMETER_RDL = """
reg parameter_word_t {
    field { sw=rw; hw=r; } data[31:0];
};
addrmap parameter_child_t {
    parameter_word_t words[3] @ 0x0 += 0x4;
};
addrmap rdl_params_t #(
    longint unsigned N_ROWS = 2,
    longint unsigned N_COLS = 3
) {
    parameter_child_t grid[N_ROWS][N_COLS] @ 0x0 += 0x20;
    parameter_child_t shared[N_ROWS] @ 0x100 += 0x20;
    parameter_child_t tail @ 0x180;
};
"""


@pytest.fixture
def parameter_rtl(
    compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
) -> Path:
    """Elaborate only the maximum RDL layout, never a reduced RDL instance."""
    top = compile_rdl(_PARAMETER_RDL, top="rdl_params_t")
    BusDecoderExporter().export(
        top,
        str(tmp_path),
        cpuif_cls=APB4CpuifFlat,
        parametrize=True,
        max_decode_depth=1,
        address_width=9,
        cpuif_unroll=False,
        clk_src="design",
        gate_signals=True,
    )
    return tmp_path


def _compile_parameter_simulation(generated: Path, rows: int, columns: int) -> Path:
    verilator = shutil.which("verilator")
    assert verilator is not None, "Executable parameter regressions require Verilator"
    helpers = Path(__file__).parent
    command = [
        verilator,
        "--cc",
        "--exe",
        "--build",
        "--assert",
        # Invalid overrides can also produce array-index/undriven-port warnings.
        # They must compile so the generated time-zero bounds assertion runs.
        "-Wno-fatal",
        "--top-module",
        "rdl_params_wrapper",
        f"-GN_ROWS={rows}",
        f"-GN_COLS={columns}",
        "-Mdir",
        str(generated / "obj_dir"),
        "-o",
        "sim",
        str(generated / "rdl_params_t_pkg.sv"),
        str(generated / "rdl_params_t.sv"),
        str(helpers / "rdl_params_wrapper.sv"),
        str(helpers / "rdl_params_scoreboard.cpp"),
    ]
    compile_result = subprocess.run(
        command, cwd=generated, capture_output=True, text=True, timeout=240
    )
    assert compile_result.returncode == 0, (
        "Verilator compilation failed; no runtime parameter behavior was exercised:\n"
        f"{compile_result.stdout}\n{compile_result.stderr}"
    )
    return generated / "obj_dir" / "sim"


def _run_parameter_simulation(
    executable: Path, rows: int, columns: int
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(executable), str(rows), str(columns)],
        cwd=executable.parent,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize(
    "rows,columns",
    [
        pytest.param(0, 0, id="zero"),
        pytest.param(0, 3, id="zero-shared"),
        pytest.param(2, 0, id="zero-columns"),
        pytest.param(1, 2, id="reduced-both"),
        pytest.param(2, 2, id="reduced-columns"),
        pytest.param(2, 3, id="maximum"),
    ],
)
def test_parameter_overrides_execute_fixed_layout(
    parameter_rtl: Path, rows: int, columns: int
) -> None:
    """Only SV parameters change; reads/writes retain the compiled maximum map."""
    executable = _compile_parameter_simulation(parameter_rtl, rows, columns)
    runtime_result = _run_parameter_simulation(executable, rows, columns)
    output = f"{runtime_result.stdout}\n{runtime_result.stderr}"
    assert runtime_result.returncode == 0, f"Parameter simulation failed:\n{output}"
    assert "RDL_PARAMS_SUCCESS" in runtime_result.stdout, output


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize(
    "rows,columns,parameter,maximum",
    [
        pytest.param(-1, 3, "N_ROWS", 2, id="rows-negative"),
        pytest.param(3, 3, "N_ROWS", 2, id="rows-above-maximum"),
        pytest.param(2, -1, "N_COLS", 3, id="columns-negative"),
        pytest.param(2, 4, "N_COLS", 3, id="columns-above-maximum"),
    ],
)
def test_parameter_override_bounds_fail_at_runtime(
    parameter_rtl: Path, rows: int, columns: int, parameter: str, maximum: int
) -> None:
    """Reject invalid SV overrides via the intended generated bounds assertion."""
    executable = _compile_parameter_simulation(parameter_rtl, rows, columns)
    runtime_result = _run_parameter_simulation(executable, rows, columns)
    output = f"{runtime_result.stdout}\n{runtime_result.stderr}"
    assert runtime_result.returncode != 0, f"Invalid override was accepted:\n{output}"
    assert "RDL_PARAMS_STARTED" in runtime_result.stdout, output
    assert f"{parameter} must be in range [0, {maximum}]" in output, (
        f"Runtime failed without the intended {parameter} bounds assertion:\n{output}"
    )
    assert "RDL_PARAMS_SUCCESS" not in output, output
