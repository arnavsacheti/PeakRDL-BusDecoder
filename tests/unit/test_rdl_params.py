"""Tests for SystemRDL parameter extraction and classification."""

from collections.abc import Callable
from pathlib import Path

from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter, ParameterUsage, RdlParameterExtractor
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif


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

    def test_direct_parameter(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """A parameter that doesn't affect array dimensions should be DIRECT."""
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
        assert len(params) == 1
        p = params[0]
        assert p.name == "RESET_VAL"
        assert p.value == 42
        assert p.usage == ParameterUsage.DIRECT
        assert p.array_enables == []

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

    def test_mixed_parameters(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """An addrmap with both direct and address-modifying parameters."""
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
        assert len(params) == 2

        by_name = {p.name: p for p in params}
        assert by_name["N_ENGINES"].usage == ParameterUsage.ADDRESS_MODIFYING
        assert by_name["N_ENGINES"].value == 3
        assert len(by_name["N_ENGINES"].array_enables) == 1

        assert by_name["DEFAULT_MODE"].usage == ParameterUsage.DIRECT
        assert by_name["DEFAULT_MODE"].value == 7


class TestRdlParameterSvProperties:
    """Tests for SV type/value rendering."""

    def test_int_param_sv_type(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        rdl = """
        addrmap sv_int #(longint unsigned VAL = 10) {
            reg { field { sw=rw; hw=r; reset=VAL; } d[31:0]; } r0 @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="sv_int")
        params = RdlParameterExtractor(top).extract()
        assert params[0].sv_type == "int"
        assert params[0].sv_value == "10"


class TestRdlParameterIntegration:
    """Tests for end-to-end parameter integration in the exporter."""

    def test_direct_param_in_module_output(
        self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
    ) -> None:
        """DIRECT parameters should appear as SV parameters on the module."""
        rdl = """
        addrmap direct_test #(longint unsigned MY_RESET = 0xFF) {
            reg { field { sw=rw; hw=r; reset=MY_RESET; } data[31:0]; } r0 @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="direct_test")
        exporter = BusDecoderExporter()
        exporter.export(top, str(tmp_path), cpuif_cls=APB4Cpuif)

        module = (tmp_path / "direct_test.sv").read_text()
        assert "parameter int MY_RESET = 255" in module

    def test_enable_param_in_module_output(
        self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
    ) -> None:
        """ADDRESS_MODIFYING parameters should appear as SV parameters with
        assertions constraining n <= N."""
        rdl = """
        addrmap enable_test #(longint unsigned N_PORTS = 4) {
            reg { field { sw=rw; hw=r; } data[31:0]; } port[N_PORTS] @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="enable_test")
        exporter = BusDecoderExporter()
        exporter.export(top, str(tmp_path), cpuif_cls=APB4Cpuif)

        module = (tmp_path / "enable_test.sv").read_text()
        assert "parameter int N_PORTS = 4" in module
        assert "N_PORTS >= 0 && N_PORTS <= 4" in module

    def test_enable_param_in_for_loop(
        self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
    ) -> None:
        """For loops in the decoder should use the parameter name as the bound."""
        rdl = """
        addrmap loop_test #(longint unsigned N_REGS = 8) {
            reg { field { sw=rw; hw=r; } data[31:0]; } regs[N_REGS] @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="loop_test")
        exporter = BusDecoderExporter()
        exporter.export(top, str(tmp_path), cpuif_cls=APB4Cpuif)

        module = (tmp_path / "loop_test.sv").read_text()
        assert "i0 < N_REGS" in module

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
        exporter.export(top, str(tmp_path), cpuif_cls=APB4Cpuif)

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
        exporter.export(top, str(tmp_path), cpuif_cls=APB4Cpuif)

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
        exporter.export(top, str(tmp_path), cpuif_cls=APB4Cpuif)

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
        exporter.export(top, str(tmp_path), cpuif_cls=APB4Cpuif)

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
        exporter.export(top, str(tmp_path), cpuif_cls=APB4Cpuif)

        module = (tmp_path / "kept_test.sv").read_text()
        assert "localparam N_REGSS = 4" in module
