"""Tests for error/edge-case paths in the validator, design state, and exporter.

These tests exercise conditions that should be rejected or produce warnings:
malformed inputs, unsupported configurations, alignment violations, etc.
"""

from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from systemrdl import RDLCompileError
from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb3 import APB3Cpuif
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif
from peakrdl_busdecoder.design_state import DesignState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _export(top: AddrmapNode, **kwargs) -> None:
    """Export via APB4 into a throwaway directory; raises on validation errors."""
    cpuif_cls = kwargs.pop("cpuif_cls", APB4Cpuif)
    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=cpuif_cls, **kwargs)


# ===========================================================================
# 1. Unaligned register address offset
# ===========================================================================
class TestUnalignedRegisters:
    """Registers with address offsets not aligned to data_width_bytes must be rejected."""

    def test_unaligned_offset_rejected(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """A register at offset 0x5 on a 32-bit (4-byte aligned) bus must fail."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t reg_a @ 0x0;
            my_reg_t reg_b @ 0x5;
        };
        """
        top = compile_rdl(rdl, top="test")
        with pytest.raises(RDLCompileError, match="Unable to export"):
            _export(top)

    def test_unaligned_offset_odd_byte(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """A register at offset 0x1 must fail alignment check."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t reg_a @ 0x0;
            my_reg_t reg_b @ 0x1;
        };
        """
        # The RDL compiler may reject this due to overlap; if it compiles,
        # the exporter should reject it.
        try:
            top = compile_rdl(rdl, top="test")
        except RDLCompileError:
            pytest.skip("RDL compiler rejected overlapping registers")
        with pytest.raises(RDLCompileError):
            _export(top)

    def test_unaligned_offset_half_word(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """A register at offset 0x2 (half-word aligned but not word-aligned) must fail."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t reg_a @ 0x0;
            my_reg_t reg_b @ 0x6;
        };
        """
        top = compile_rdl(rdl, top="test")
        with pytest.raises(RDLCompileError, match="Unable to export"):
            _export(top)

    def test_aligned_offset_passes(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Properly word-aligned offsets should pass validation."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t reg_a @ 0x0;
            my_reg_t reg_b @ 0x4;
            my_reg_t reg_c @ 0x8;
        };
        """
        top = compile_rdl(rdl, top="test")
        _export(top)  # Should not raise


# ===========================================================================
# 2. Unaligned array stride
# ===========================================================================
class TestUnalignedArrayStride:
    """Arrays whose stride is not a multiple of data_width_bytes must be rejected."""

    def test_unaligned_stride_rejected(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """An array stride of 0x5 (not a multiple of 4) must fail."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_regs[4] @ 0x0 += 0x5;
        };
        """
        top = compile_rdl(rdl, top="test")
        with pytest.raises(RDLCompileError, match="Unable to export"):
            _export(top)

    def test_unaligned_stride_6_rejected(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """An array stride of 0x6 (not a multiple of 4) must fail."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_regs[2] @ 0x0 += 0x6;
        };
        """
        top = compile_rdl(rdl, top="test")
        with pytest.raises(RDLCompileError, match="Unable to export"):
            _export(top)

    def test_aligned_stride_passes(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """A stride that is a multiple of 4 bytes should pass."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_regs[4] @ 0x0 += 0x8;
        };
        """
        top = compile_rdl(rdl, top="test")
        _export(top)  # Should not raise

    def test_unaligned_stride_64bit_bus(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """On a 64-bit bus, stride of 12 (not a multiple of 8) must fail."""
        rdl = """
        addrmap test {
            reg wide_reg_t {
                regwidth = 64;
                accesswidth = 64;
                field { sw=rw; hw=r; } data[63:0];
            };
            wide_reg_t my_regs[2] @ 0x0 += 0xC;
        };
        """
        # stride = 12 but data_width_bytes = 8
        top = compile_rdl(rdl, top="test")
        with pytest.raises(RDLCompileError, match="Unable to export"):
            _export(top)


# ===========================================================================
# 3. Multi-word register with mismatched accesswidth
# ===========================================================================
class TestMultiWordRegisterMismatch:
    """Wide registers whose accesswidth differs from the CPU bus width must be rejected."""

    def test_mismatched_accesswidth_rejected(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """A wide reg with accesswidth=32 on a 64-bit bus must fail."""
        rdl = """
        addrmap test {
            reg wide_reg_t {
                regwidth = 64;
                accesswidth = 32;
                field { sw=rw; hw=r; } lo[31:0];
                field { sw=rw; hw=r; } hi[63:32];
            };
            reg normal_reg_t {
                regwidth = 64;
                accesswidth = 64;
                field { sw=rw; hw=r; } data[63:0];
            };
            normal_reg_t reg_a @ 0x0;
            wide_reg_t reg_b @ 0x8;
        };
        """
        top = compile_rdl(rdl, top="test")
        with pytest.raises(RDLCompileError, match="Unable to export"):
            _export(top)

    def test_consistent_accesswidth_passes(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """A wide register whose accesswidth matches the bus width should pass."""
        rdl = """
        addrmap test {
            reg wide_reg_t {
                regwidth = 64;
                accesswidth = 32;
                field { sw=rw; hw=r; } lo[31:0];
                field { sw=rw; hw=r; } hi[63:32];
            };
            wide_reg_t reg_a @ 0x0;
        };
        """
        # Here the bus width is inferred as 32 (from accesswidth=32),
        # and the wide register also has accesswidth=32 → consistent.
        top = compile_rdl(rdl, top="test")
        _export(top)  # Should not raise

    def test_all_wide_same_accesswidth_passes(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Multiple wide registers with matching accesswidth should pass."""
        rdl = """
        addrmap test {
            reg wide_reg_t {
                regwidth = 64;
                accesswidth = 32;
                field { sw=rw; hw=r; } lo[31:0];
                field { sw=rw; hw=r; } hi[63:32];
            };
            wide_reg_t reg_a @ 0x0;
            wide_reg_t reg_b @ 0x8;
        };
        """
        top = compile_rdl(rdl, top="test")
        _export(top)  # Should not raise


# ===========================================================================
# 4. sharedextbus property rejection
# ===========================================================================
class TestSharedExtBus:
    """The sharedextbus property is not yet supported and must be rejected."""

    def test_sharedextbus_on_addrmap_rejected(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """An addrmap with sharedextbus must fail."""
        rdl = """
        addrmap test {
            sharedextbus;
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="test")
        with pytest.raises(RDLCompileError, match="Unable to export"):
            _export(top)

    def test_sharedextbus_on_child_addrmap_rejected(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """A child addrmap with sharedextbus (that is not external) must fail."""
        rdl = """
        addrmap inner {
            sharedextbus;
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_reg @ 0x0;
        };
        addrmap outer {
            inner child @ 0x0;
        };
        """
        # inner is external by default when nested, so the validator skips
        # its internals. But the sharedextbus check fires on enter_Addrmap,
        # which happens before SkipDescendants.
        top = compile_rdl(rdl, top="outer")
        with pytest.raises(RDLCompileError, match="Unable to export"):
            _export(top)

    def test_no_sharedextbus_passes(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """An addrmap without sharedextbus should pass."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="test")
        _export(top)  # Should not raise


# ===========================================================================
# 5. Address width too small
# ===========================================================================
class TestAddressWidthTooSmall:
    """User-specified address width smaller than the minimum must be rejected."""

    def test_address_width_too_small_fatal(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """address_width=1 on a design requiring >= 3 bits must fail."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t reg_a @ 0x0;
            my_reg_t reg_b @ 0x4;
        };
        """
        top = compile_rdl(rdl, top="test")
        with pytest.raises(RDLCompileError, match="address width"):
            DesignState(top, {"address_width": 1})

    def test_address_width_too_small_by_one(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """address_width one less than minimum must fail."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t reg_a @ 0x0;
            my_reg_t reg_b @ 0x4;
        };
        """
        top = compile_rdl(rdl, top="test")
        ds = DesignState(top, {})
        min_width = ds.addr_width

        with pytest.raises(RDLCompileError, match="address width"):
            DesignState(top, {"address_width": min_width - 1})

    def test_address_width_exact_minimum_passes(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """address_width equal to the minimum should pass."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t reg_a @ 0x0;
            my_reg_t reg_b @ 0x4;
        };
        """
        top = compile_rdl(rdl, top="test")
        ds_auto = DesignState(top, {})
        min_width = ds_auto.addr_width

        ds_explicit = DesignState(top, {"address_width": min_width})
        assert ds_explicit.addr_width == min_width

    def test_address_width_larger_than_minimum_passes(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """address_width larger than the minimum should pass and be honored."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t reg_a @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="test")
        ds = DesignState(top, {"address_width": 32})
        assert ds.addr_width == 32


# ===========================================================================
# 6. External-only design (no internal registers) → warning + assumed 32-bit
# ===========================================================================
class TestExternalOnlyDesign:
    """When a design has no internal registers, the bus width cannot be inferred."""

    def test_external_only_defaults_to_32bit(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """An addrmap with only external components should default to 32-bit bus."""
        rdl = """
        mem my_mem_t {
            mementries = 256;
            memwidth = 32;
        };
        addrmap test {
            external my_mem_t ext_mem @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="test")
        ds = DesignState(top, {})
        assert ds.cpuif_data_width == 32

    def test_external_only_still_exports(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """An external-only design should still export successfully."""
        rdl = """
        mem my_mem_t {
            mementries = 256;
            memwidth = 32;
        };
        addrmap test {
            external my_mem_t ext_mem @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="test")
        _export(top)  # Should not raise


# ===========================================================================
# 7. Exporter TypeError on stray keyword arguments
# ===========================================================================
class TestExporterStrayKwargs:
    """Unrecognized keyword arguments must raise TypeError."""

    def test_constructor_stray_kwarg(self) -> None:
        """BusDecoderExporter() with unknown kwargs must raise TypeError."""
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            BusDecoderExporter(bad_option=True)

    def test_export_stray_kwarg(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """export() with unknown kwargs must raise TypeError."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="test")
        exporter = BusDecoderExporter()
        with TemporaryDirectory() as tmpdir:
            with pytest.raises(TypeError, match="unexpected keyword argument"):
                exporter.export(top, tmpdir, bogus_option=42)

    def test_constructor_multiple_stray_kwargs(self) -> None:
        """Multiple stray kwargs should still raise TypeError (reports the first)."""
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            BusDecoderExporter(foo="bar", baz=123)

    def test_export_stray_kwarg_alongside_valid(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """A mix of valid and invalid kwargs must raise TypeError for the invalid one."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="test")
        exporter = BusDecoderExporter()
        with TemporaryDirectory() as tmpdir:
            with pytest.raises(TypeError, match="unexpected keyword argument"):
                exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif, not_a_real_option=True)


# ===========================================================================
# 8. IfBody internal state errors
# ===========================================================================
class TestIfBodyStateErrors:
    """IfBody should raise RuntimeError on invalid branch operations."""

    def test_branch_after_else_raises(self) -> None:
        """Adding a conditional branch after an else must fail."""
        from peakrdl_busdecoder.body import IfBody

        body = IfBody()
        body["condition1"]  # if
        body[None]  # else
        with pytest.raises(RuntimeError, match="Cannot add branches after"):
            body["condition2"]

    def test_double_else_raises(self) -> None:
        """Adding two else branches must fail."""
        from peakrdl_busdecoder.body import IfBody

        body = IfBody()
        body["condition1"]  # if
        body[None]  # else
        with pytest.raises(RuntimeError, match="Cannot add branches after"):
            body[None]

    def test_ior_conditional_after_else_raises(self) -> None:
        """Using |= to add a conditional branch after else must fail."""
        from peakrdl_busdecoder.body import Body, IfBody

        ifb = IfBody()
        ifb["cond1"]
        ifb[None]  # else
        with pytest.raises(RuntimeError, match="Cannot add branches after"):
            ifb |= ("cond2", Body())

    def test_ior_else_after_else_raises(self) -> None:
        """Using |= to add a Body (else) after else must fail."""
        from peakrdl_busdecoder.body import Body, IfBody

        ifb = IfBody()
        ifb["cond1"]
        ifb[None]  # else
        with pytest.raises(RuntimeError, match="Only one 'else' branch is allowed"):
            ifb |= Body()

    def test_cm_after_else_raises(self) -> None:
        """Using the context manager to add a branch after else must fail."""
        from peakrdl_busdecoder.body import IfBody

        body = IfBody()
        with body.cm("cond1"):
            pass
        with body.cm(None):  # else
            pass
        with pytest.raises(RuntimeError, match="Cannot add branches after"):
            with body.cm("cond2"):
                pass

    def test_ellipsis_as_else(self) -> None:
        """Using Ellipsis (...) as the condition should produce an else branch."""
        from peakrdl_busdecoder.body import IfBody

        body = IfBody()
        body["cond1"]
        body[...]  # else via Ellipsis
        with pytest.raises(RuntimeError, match="Cannot add branches after"):
            body["cond2"]


# ===========================================================================
# 9. Multiple CPU interface protocols
# ===========================================================================
class TestMultipleCpuifProtocols:
    """Verify that error paths trigger consistently across different cpuif classes."""

    def test_unaligned_rejected_apb3(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Unaligned registers should be rejected under APB3 as well."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t reg_a @ 0x0;
            my_reg_t reg_b @ 0x5;
        };
        """
        top = compile_rdl(rdl, top="test")
        with pytest.raises(RDLCompileError, match="Unable to export"):
            _export(top, cpuif_cls=APB3Cpuif)

    def test_sharedextbus_rejected_apb3(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """sharedextbus should be rejected under APB3."""
        rdl = """
        addrmap test {
            sharedextbus;
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="test")
        with pytest.raises(RDLCompileError, match="Unable to export"):
            _export(top, cpuif_cls=APB3Cpuif)


# ===========================================================================
# 10. Edge-case alignment scenarios
# ===========================================================================
class TestEdgeCaseAlignments:
    """Boundary conditions and edge cases for alignment validation."""

    def test_single_register_at_zero_passes(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """A single register at offset 0 is always aligned."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="test")
        _export(top)

    def test_large_aligned_offset_passes(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """A register at a large but properly aligned offset should pass."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t reg_a @ 0x0;
            my_reg_t reg_b @ 0x1000;
        };
        """
        top = compile_rdl(rdl, top="test")
        _export(top)

    def test_64bit_bus_alignment(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """On a 64-bit bus, offset 0xC (only 4-byte aligned, not 8) must fail."""
        rdl = """
        addrmap test {
            reg wide_reg_t {
                regwidth = 64;
                accesswidth = 64;
                field { sw=rw; hw=r; } data[63:0];
            };
            wide_reg_t reg_a @ 0x0;
            wide_reg_t reg_b @ 0xC;
        };
        """
        top = compile_rdl(rdl, top="test")
        with pytest.raises(RDLCompileError, match="Unable to export"):
            _export(top)

    def test_64bit_bus_proper_alignment_passes(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """On a 64-bit bus, offset 0x8 (8-byte aligned) should pass."""
        rdl = """
        addrmap test {
            reg wide_reg_t {
                regwidth = 64;
                accesswidth = 64;
                field { sw=rw; hw=r; } data[63:0];
            };
            wide_reg_t reg_a @ 0x0;
            wide_reg_t reg_b @ 0x8;
        };
        """
        top = compile_rdl(rdl, top="test")
        _export(top)

    def test_multiple_alignment_errors_still_fatal(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Multiple unaligned registers should all be reported, then a fatal is raised."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t reg_a @ 0x0;
            my_reg_t reg_b @ 0x5;
            my_reg_t reg_c @ 0x9;
        };
        """
        top = compile_rdl(rdl, top="test")
        with pytest.raises(RDLCompileError, match="Unable to export"):
            _export(top)


# ===========================================================================
# 11. Design state inference edge cases
# ===========================================================================
class TestDesignStateEdgeCases:
    """Edge cases in DesignState initialization and bus width inference."""

    def test_mixed_accesswidths_takes_max(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """When registers have different accesswidths, the max should be used."""
        rdl = """
        addrmap test {
            reg narrow_reg_t {
                regwidth = 32;
                accesswidth = 32;
                field { sw=rw; hw=r; } data[31:0];
            };
            reg wide_reg_t {
                regwidth = 64;
                accesswidth = 64;
                field { sw=rw; hw=r; } data[63:0];
            };
            narrow_reg_t narrow @ 0x0;
            wide_reg_t wide @ 0x8;
        };
        """
        top = compile_rdl(rdl, top="test")
        ds = DesignState(top, {})
        assert ds.cpuif_data_width == 64

    def test_default_module_name_from_addrmap(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Module name should default to the addrmap name."""
        rdl = """
        addrmap my_custom_name {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="my_custom_name")
        ds = DesignState(top, {})
        assert ds.module_name == "my_custom_name"
        assert ds.package_name == "my_custom_name_pkg"

    def test_address_width_zero_design(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """A minimal design should still compute a valid address width > 0."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="test")
        ds = DesignState(top, {})
        assert ds.addr_width > 0

    def test_max_decode_depth_default(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Default max_decode_depth should be 1."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="test")
        ds = DesignState(top, {})
        assert ds.max_decode_depth == 1

    def test_max_decode_depth_zero(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """max_decode_depth=0 means decode all levels."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="test")
        ds = DesignState(top, {"max_decode_depth": 0})
        assert ds.max_decode_depth == 0

    def test_reuse_hwif_typedefs_default(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Default reuse_hwif_typedefs should be True."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="test")
        ds = DesignState(top, {})
        assert ds.reuse_hwif_typedefs is True


# ===========================================================================
# 12. RootNode vs AddrmapNode input
# ===========================================================================
class TestRootNodeHandling:
    """The exporter should handle both RootNode and AddrmapNode inputs."""

    def test_export_with_root_node(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Passing a RootNode (parent of top addrmap) should still work."""
        rdl = """
        addrmap test {
            reg my_reg_t {
                field { sw=rw; hw=r; } data[31:0];
            };
            my_reg_t my_reg @ 0x0;
        };
        """
        from tempfile import NamedTemporaryFile

        from systemrdl import RDLCompiler

        compiler = RDLCompiler()
        with NamedTemporaryFile("w", suffix=".rdl", delete=False) as f:
            f.write(rdl)
            f.flush()
            compiler.compile_file(f.name)

        root = compiler.elaborate(top_def_name="test")
        # Pass the RootNode directly (not root.top)
        with TemporaryDirectory() as tmpdir:
            exporter = BusDecoderExporter()
            exporter.export(root, tmpdir, cpuif_cls=APB4Cpuif)
            assert (Path(tmpdir) / "test.sv").exists()
