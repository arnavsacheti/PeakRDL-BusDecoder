"""Test max_decode_depth parameter behavior."""

from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from systemrdl.node import AddrmapNode, RegNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb3 import APB3Cpuif
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif
from peakrdl_busdecoder.cpuif.axi4lite import AXI4LiteCpuif
from peakrdl_busdecoder.design_state import DesignState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _export_and_read(
    top: AddrmapNode,
    *,
    max_decode_depth: int = 1,
    cpuif_cls: type = APB4Cpuif,
    **kwargs,
) -> str:
    """Export via given cpuif into a temp dir and return the module .sv content."""
    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(
            top, tmpdir, cpuif_cls=cpuif_cls, max_decode_depth=max_decode_depth, **kwargs
        )
        module_file = Path(tmpdir) / f"{top.inst_name}.sv"
        return module_file.read_text()


# ===========================================================================
# 1. Basic depth tests (existing coverage, kept for regression)
# ===========================================================================
def test_depth_1_generates_top_level_interface_only(compile_rdl: Callable[..., AddrmapNode]) -> None:
    """Test that depth=1 generates interface only for top-level children."""
    rdl_source = """
    addrmap level1 {
        reg {
            field { sw=rw; hw=r; } data1[31:0];
        } reg1 @ 0x0;
    };

    addrmap level0 {
        level1 inner1 @ 0x0;
    };
    """
    top = compile_rdl(rdl_source, top="level0")
    content = _export_and_read(top, max_decode_depth=1)

    # Should have interface for inner1 only
    assert "m_apb_inner1" in content
    # Should NOT have interface for reg1
    assert "m_apb_reg1" not in content

    # Struct should have inner1 but not nested structure
    assert "logic inner1;" in content


def test_depth_2_generates_second_level_interfaces(compile_rdl: Callable[..., AddrmapNode]) -> None:
    """Test that depth=2 generates interfaces for second-level children."""
    rdl_source = """
    addrmap level2 {
        reg {
            field { sw=rw; hw=r; } data2[31:0];
        } reg2 @ 0x0;
    };

    addrmap level1 {
        reg {
            field { sw=rw; hw=r; } data1[31:0];
        } reg1 @ 0x0;

        level2 inner2 @ 0x10;
    };

    addrmap level0 {
        level1 inner1 @ 0x0;
    };
    """
    top = compile_rdl(rdl_source, top="level0")
    content = _export_and_read(top, max_decode_depth=2)

    # Should have interfaces for reg1 and inner2
    assert "m_apb_reg1" in content
    assert "m_apb_inner2" in content
    # Should NOT have interface for inner1 or reg2
    assert "m_apb_inner1" not in content
    assert "m_apb_reg2" not in content

    # Struct should be hierarchical with inner1.reg1 and inner1.inner2
    assert "cpuif_sel_inner1_t" in content
    assert "logic reg1;" in content
    assert "logic inner2;" in content


def test_depth_0_decodes_all_levels(compile_rdl: Callable[..., AddrmapNode]) -> None:
    """Test that depth=0 decodes all the way down to registers."""
    rdl_source = """
    addrmap level2 {
        reg {
            field { sw=rw; hw=r; } data2[31:0];
        } reg2 @ 0x0;

        reg {
            field { sw=rw; hw=r; } data2b[31:0];
        } reg2b @ 0x4;
    };

    addrmap level1 {
        reg {
            field { sw=rw; hw=r; } data1[31:0];
        } reg1 @ 0x0;

        level2 inner2 @ 0x10;
    };

    addrmap level0 {
        level1 inner1 @ 0x0;
    };
    """
    top = compile_rdl(rdl_source, top="level0")
    content = _export_and_read(top, max_decode_depth=0)

    # Should have interfaces for all leaf registers
    assert "m_apb_reg1" in content
    assert "m_apb_reg2" in content
    assert "m_apb_reg2b" in content
    # Should NOT have interfaces for addrmaps
    assert "m_apb_inner1" not in content
    assert "m_apb_inner2" not in content

    # Struct should be fully hierarchical
    assert "cpuif_sel_inner1_t" in content
    assert "cpuif_sel_inner2_t" in content


def test_depth_affects_decode_logic(compile_rdl: Callable[..., AddrmapNode]) -> None:
    """Test that decode logic changes based on max_decode_depth."""
    rdl_source = """
    addrmap level1 {
        reg {
            field { sw=rw; hw=r; } data1[31:0];
        } reg1 @ 0x0;
    };

    addrmap level0 {
        level1 inner1 @ 0x0;
    };
    """
    top = compile_rdl(rdl_source, top="level0")

    # Test depth=1: should set cpuif_wr_sel.inner1
    content = _export_and_read(top, max_decode_depth=1)
    assert "cpuif_wr_sel.inner1 = 1'b1;" in content
    assert "cpuif_wr_sel.inner1.reg1" not in content

    # Test depth=2: should set cpuif_wr_sel.inner1.reg1
    content = _export_and_read(top, max_decode_depth=2)
    assert "cpuif_wr_sel.inner1.reg1 = 1'b1;" in content
    assert "cpuif_wr_sel.inner1 = 1'b1;" not in content


def test_depth_affects_fanout_fanin(compile_rdl: Callable[..., AddrmapNode]) -> None:
    """Test that fanout/fanin logic changes based on max_decode_depth."""
    rdl_source = """
    addrmap level1 {
        reg {
            field { sw=rw; hw=r; } data1[31:0];
        } reg1 @ 0x0;
    };

    addrmap level0 {
        level1 inner1 @ 0x0;
    };
    """
    top = compile_rdl(rdl_source, top="level0")

    # Test depth=1: should have fanout for inner1
    content = _export_and_read(top, max_decode_depth=1)
    assert "m_apb_inner1.PSEL" in content
    assert "m_apb_reg1.PSEL" not in content

    # Test depth=2: should have fanout for reg1
    content = _export_and_read(top, max_decode_depth=2)
    assert "m_apb_reg1.PSEL" in content
    assert "m_apb_inner1.PSEL" not in content


def test_depth_3_with_deep_hierarchy(compile_rdl: Callable[..., AddrmapNode]) -> None:
    """Test depth=3 with a 4-level deep hierarchy."""
    rdl_source = """
    addrmap level3 {
        reg {
            field { sw=rw; hw=r; } data3[31:0];
        } reg3 @ 0x0;
    };

    addrmap level2 {
        reg {
            field { sw=rw; hw=r; } data2[31:0];
        } reg2 @ 0x0;

        level3 inner3 @ 0x10;
    };

    addrmap level1 {
        reg {
            field { sw=rw; hw=r; } data1[31:0];
        } reg1 @ 0x0;

        level2 inner2 @ 0x10;
    };

    addrmap level0 {
        level1 inner1 @ 0x0;
    };
    """
    top = compile_rdl(rdl_source, top="level0")
    content = _export_and_read(top, max_decode_depth=3)

    # Should have interfaces at depth 3: reg2, inner3
    # (reg1 is at depth 2, not 3)
    assert "m_apb_reg2" in content
    assert "m_apb_inner3" in content
    # Should NOT have interfaces at other depths
    assert "m_apb_inner1" not in content
    assert "m_apb_inner2" not in content
    assert "m_apb_reg1" not in content
    assert "m_apb_reg3" not in content


# ===========================================================================
# 2. Multiple siblings at the decode boundary
# ===========================================================================
class TestMultipleSiblings:
    """Verify correct generation when multiple children exist at the same depth."""

    def test_depth_1_multiple_top_level_children(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=1 with three top-level addrmaps generates three interfaces."""
        rdl_source = """
        addrmap child {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } reg1 @ 0x0;
        };

        addrmap top {
            child block_a @ 0x0;
            child block_b @ 0x100;
            child block_c @ 0x200;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=1)

        assert "m_apb_block_a" in content
        assert "m_apb_block_b" in content
        assert "m_apb_block_c" in content
        # No per-register interfaces
        assert "m_apb_reg1" not in content

    def test_depth_1_mixed_registers_and_addrmaps(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=1 with registers and addrmaps at top level."""
        rdl_source = """
        addrmap child {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } inner_reg @ 0x0;
        };

        addrmap top {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } top_reg @ 0x0;
            child sub_block @ 0x100;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=1)

        # Both the register and child addrmap are at depth 1
        assert "m_apb_top_reg" in content
        assert "m_apb_sub_block" in content
        # Inner register should not appear
        assert "m_apb_inner_reg" not in content

    def test_depth_2_multiple_siblings_at_second_level(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=2 with three children inside a parent addrmap."""
        rdl_source = """
        addrmap inner {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg_a @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg_b @ 0x4;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg_c @ 0x8;
        };

        addrmap top {
            inner block @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=2)

        # All three registers at depth 2 should have interfaces
        assert "m_apb_reg_a" in content
        assert "m_apb_reg_b" in content
        assert "m_apb_reg_c" in content
        # Parent addrmap should not have its own interface
        assert "m_apb_block" not in content


# ===========================================================================
# 3. Depth exceeding actual hierarchy
# ===========================================================================
class TestDepthExceedsHierarchy:
    """When max_decode_depth is deeper than the hierarchy, the decoder should
    still work correctly. Nodes above the depth boundary are traversed but
    not decoded, while registers at the boundary or below are decoded.
    When depth exceeds all hierarchy levels, no child interfaces are generated."""

    def test_depth_exceeding_hierarchy_still_exports(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=5 on a 2-level hierarchy should still export without error."""
        rdl_source = """
        addrmap child {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } reg1 @ 0x0;
        };

        addrmap top {
            child block @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        # Should not raise an error
        content = _export_and_read(top, max_decode_depth=5)

        # Module should still be generated
        assert "module top" in content
        # cpuif_err should always be present
        assert "cpuif_err" in content

    def test_depth_1_on_flat_design(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=1 on a flat design (just registers at top) generates register interfaces."""
        rdl_source = """
        addrmap top {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg_a @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg_b @ 0x4;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=1)

        # Registers are at depth 1, which is the limit
        assert "m_apb_reg_a" in content
        assert "m_apb_reg_b" in content

    def test_depth_exact_match_generates_interfaces(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """Nodes exactly at the depth boundary get decoded."""
        rdl_source = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
        };

        addrmap top {
            child block @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")

        # block at depth 1, reg1 at depth 2
        # depth=1: block is at boundary
        content = _export_and_read(top, max_decode_depth=1)
        assert "m_apb_block" in content
        assert "m_apb_reg1" not in content

        # depth=2: reg1 is at boundary
        content = _export_and_read(top, max_decode_depth=2)
        assert "m_apb_reg1" in content
        assert "m_apb_block" not in content


# ===========================================================================
# 4. Arrayed components with depth control
# ===========================================================================
class TestArrayedComponentsWithDepth:
    """Verify that arrayed addressable components interact correctly with depth."""

    def test_depth_1_with_arrayed_addrmap(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=1 with an arrayed addrmap generates an arrayed interface."""
        rdl_source = """
        addrmap child {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } reg1 @ 0x0;
        };

        addrmap top {
            child blocks[4] @ 0x0 += 0x100;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=1)

        # Arrayed interface
        assert "m_apb_blocks" in content
        # Should not expand to individual register interfaces
        assert "m_apb_reg1" not in content

    def test_depth_1_arrayed_addrmap_decode_logic(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=1 with arrayed addrmaps generates for-loop decode logic."""
        rdl_source = """
        addrmap child {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } reg1 @ 0x0;
        };

        addrmap top {
            child blocks[4] @ 0x0 += 0x100;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=1)

        # Should have for loop for arrayed decode
        assert "blocks[i0]" in content or "blocks" in content
        # Array select signal
        assert "logic blocks[4];" in content

    def test_depth_2_descends_into_arrayed_addrmap(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=2 descends into arrayed addrmaps to expose child registers."""
        rdl_source = """
        addrmap child {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } reg1 @ 0x0;
        };

        addrmap top {
            child blocks[4] @ 0x0 += 0x100;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=2)

        # Should generate interfaces for registers inside the array
        assert "m_apb_reg1" in content
        # The array itself should not have its own interface
        assert "m_apb_blocks" not in content

    def test_depth_0_with_arrayed_addrmap(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=0 with arrayed addrmaps descends all the way to registers."""
        rdl_source = """
        addrmap child {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } reg1 @ 0x0;
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } reg2 @ 0x4;
        };

        addrmap top {
            child blocks[4] @ 0x0 += 0x100;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=0)

        # All leaf registers should have interfaces
        assert "m_apb_reg1" in content
        assert "m_apb_reg2" in content
        assert "m_apb_blocks" not in content

    def test_depth_1_with_arrayed_registers(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=1 with arrayed registers at top level."""
        rdl_source = """
        addrmap top {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } my_regs[8] @ 0x0 += 0x4;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=1)

        # Arrayed register should be present
        assert "my_regs" in content


# ===========================================================================
# 5. Regfile components with depth control
# ===========================================================================
class TestRegfileWithDepth:
    """Verify depth behavior with regfile (addressable but not addrmap) nesting."""

    def test_depth_1_with_regfile(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=1 with a regfile generates interface for the regfile."""
        rdl_source = """
        regfile my_rf {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } reg1 @ 0x0;
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } reg2 @ 0x4;
        };

        addrmap top {
            my_rf rf_block @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=1)

        # Should have interface for regfile
        assert "m_apb_rf_block" in content
        # Should not expose individual registers
        assert "m_apb_reg1" not in content
        assert "m_apb_reg2" not in content

    def test_depth_2_descends_into_regfile(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=2 descends into a regfile to expose individual registers."""
        rdl_source = """
        regfile my_rf {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } reg1 @ 0x0;
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } reg2 @ 0x4;
        };

        addrmap top {
            my_rf rf_block @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=2)

        # Should expose individual registers
        assert "m_apb_reg1" in content
        assert "m_apb_reg2" in content
        # Should not have interface for the regfile itself
        assert "m_apb_rf_block" not in content

    def test_depth_0_with_nested_regfile_in_addrmap(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=0 descends fully through addrmap containing regfile."""
        rdl_source = """
        regfile my_rf {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } rf_reg @ 0x0;
        };

        addrmap child {
            my_rf rf_inst @ 0x0;
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } child_reg @ 0x100;
        };

        addrmap top {
            child sub @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=0)

        # All leaf registers visible
        assert "m_apb_rf_reg" in content
        assert "m_apb_child_reg" in content
        # No intermediate component interfaces
        assert "m_apb_sub" not in content
        assert "m_apb_rf_inst" not in content


# ===========================================================================
# 6. External component interaction with depth
# ===========================================================================
class TestExternalWithDepth:
    """External components should remain as decode boundaries regardless of depth."""

    def test_depth_0_does_not_descend_into_external(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """Even with depth=0 (all levels), external memories should not be descended into."""
        rdl_source = """
        mem my_mem {
            mementries = 256;
            memwidth = 32;
        };

        addrmap top {
            external my_mem ext_mem @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } my_reg @ 0x1000;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=0)

        # External memory should have an interface
        assert "ext_mem" in content
        # Internal register should also be reachable
        assert "my_reg" in content

    def test_depth_1_with_mixed_external_and_internal(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=1 with both external and internal components at top level."""
        rdl_source = """
        mem my_mem {
            mementries = 256;
            memwidth = 32;
        };

        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } inner_reg @ 0x0;
        };

        addrmap top {
            external my_mem ext_mem @ 0x0;
            child internal_block @ 0x1000;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=1)

        # Both external and internal should have interfaces at depth 1
        assert "ext_mem" in content
        assert "internal_block" in content
        # Internal child's register should not be exposed
        assert "m_apb_inner_reg" not in content

    def test_depth_0_external_alongside_non_external(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=0: external child stays as boundary, non-external registers get decoded."""
        rdl_source = """
        mem my_mem {
            mementries = 256;
            memwidth = 32;
        };

        addrmap inner {
            reg { field { sw=rw; hw=r; } data[31:0]; } deep_reg @ 0x0;
        };

        addrmap top {
            external my_mem ext_mem @ 0x0;
            inner blk @ 0x1000;
            reg { field { sw=rw; hw=r; } data[31:0]; } top_reg @ 0x2000;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=0)

        # External stays as-is
        assert "ext_mem" in content
        # Non-external registers get decoded all the way
        assert "deep_reg" in content
        assert "top_reg" in content


# ===========================================================================
# 7. DesignState.get_addressable_children_at_depth()
# ===========================================================================
class TestGetAddressableChildrenAtDepth:
    """Unit tests for the DesignState helper method."""

    def test_depth_1_returns_top_children(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        rdl_source = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
        };

        addrmap top {
            child block_a @ 0x0;
            child block_b @ 0x100;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        ds = DesignState(top, {"max_decode_depth": 1})
        nodes = ds.get_addressable_children_at_depth()
        names = [n.inst_name for n in nodes]

        assert names == ["block_a", "block_b"]

    def test_depth_2_returns_second_level_children(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        rdl_source = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg2 @ 0x4;
        };

        addrmap top {
            child block @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        ds = DesignState(top, {"max_decode_depth": 2})
        nodes = ds.get_addressable_children_at_depth()
        names = [n.inst_name for n in nodes]

        assert names == ["reg1", "reg2"]

    def test_depth_0_returns_all_leaf_registers(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        rdl_source = """
        addrmap level2 {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg2 @ 0x0;
        };

        addrmap level1 {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
            level2 inner2 @ 0x10;
        };

        addrmap top {
            level1 inner1 @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        ds = DesignState(top, {"max_decode_depth": 0})
        nodes = ds.get_addressable_children_at_depth()
        names = [n.inst_name for n in nodes]

        assert "reg1" in names
        assert "reg2" in names
        # All returned nodes should be register nodes
        for node in nodes:
            assert isinstance(node, RegNode)

    def test_depth_0_flat_design(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=0 on a flat design returns the top-level registers."""
        rdl_source = """
        addrmap top {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg_a @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg_b @ 0x4;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        ds = DesignState(top, {"max_decode_depth": 0})
        nodes = ds.get_addressable_children_at_depth()
        names = [n.inst_name for n in nodes]

        assert names == ["reg_a", "reg_b"]

    def test_depth_1_with_multiple_child_types(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=1 returns children that are a mix of registers and addrmaps."""
        rdl_source = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } inner_reg @ 0x0;
        };

        addrmap top {
            reg { field { sw=rw; hw=r; } data[31:0]; } top_reg @ 0x0;
            child sub @ 0x100;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        ds = DesignState(top, {"max_decode_depth": 1})
        nodes = ds.get_addressable_children_at_depth()
        names = [n.inst_name for n in nodes]

        assert "top_reg" in names
        assert "sub" in names


# ===========================================================================
# 8. Struct generation at different depths
# ===========================================================================
class TestStructGeneration:
    """Verify that generated select signal structs are correct at each depth."""

    def test_depth_1_flat_struct(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=1 should generate a flat cpuif_sel_t struct."""
        rdl_source = """
        addrmap child_a {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
        };

        addrmap child_b {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
        };

        addrmap top {
            child_a ca @ 0x0;
            child_b cb @ 0x100;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=1)

        # Struct should be flat: logic ca; logic cb;
        assert "logic ca;" in content
        assert "logic cb;" in content
        # No nested struct types
        assert "cpuif_sel_ca_t" not in content
        assert "cpuif_sel_cb_t" not in content

    def test_depth_2_nested_struct(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=2 should generate nested struct types for intermediate addrmaps."""
        rdl_source = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } r1 @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } r2 @ 0x4;
        };

        addrmap top {
            child block @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=2)

        # Nested struct type for the intermediate addrmap
        assert "cpuif_sel_block_t" in content
        assert "logic r1;" in content
        assert "logic r2;" in content

    def test_depth_0_deeply_nested_struct(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=0 on multi-level hierarchy generates nested struct types.

        Each intermediate addrmap must have at least one non-external register
        to prevent the 'all external children' skip logic from triggering.
        """
        rdl_source = """
        addrmap level2 {
            reg { field { sw=rw; hw=r; } data[31:0]; } deep_reg @ 0x0;
        };

        addrmap level1 {
            reg { field { sw=rw; hw=r; } data[31:0]; } mid_reg @ 0x0;
            level2 sub @ 0x10;
        };

        addrmap top {
            level1 outer @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=0)

        # Should have nested struct types at each level
        assert "cpuif_sel_outer_t" in content
        assert "cpuif_sel_sub_t" in content
        # Leaf registers should have interfaces
        assert "m_apb_deep_reg" in content
        assert "m_apb_mid_reg" in content


# ===========================================================================
# 9. Address decode logic correctness across depths
# ===========================================================================
class TestAddressDecodeCorrectness:
    """Verify address range comparisons in decode logic at different depths."""

    def test_depth_1_uses_child_total_size(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=1 should use the total_size of the child addrmap for address decode."""
        rdl_source = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } r1 @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } r2 @ 0x4;
        };

        addrmap top {
            child ca @ 0x0;
            child cb @ 0x100;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=1)

        # At depth 1, decode logic sets select for child addrmaps
        assert "cpuif_wr_sel.ca = 1'b1;" in content
        assert "cpuif_wr_sel.cb = 1'b1;" in content

    def test_depth_2_uses_register_address(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=2 should use individual register addresses for decode."""
        rdl_source = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } r1 @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } r2 @ 0x4;
        };

        addrmap top {
            child block @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=2)

        # At depth 2, individual registers should have their own select signals
        assert "cpuif_wr_sel.block.r1 = 1'b1;" in content
        assert "cpuif_wr_sel.block.r2 = 1'b1;" in content

    def test_depth_0_all_registers_in_decode(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=0 should generate decode paths for every leaf register."""
        rdl_source = """
        addrmap inner {
            reg { field { sw=rw; hw=r; } data[31:0]; } r_deep @ 0x0;
        };

        addrmap top {
            inner blk @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } r_top @ 0x100;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=0)

        # Both registers should have decode logic
        assert "cpuif_wr_sel.blk.r_deep = 1'b1;" in content
        assert "cpuif_wr_sel.r_top = 1'b1;" in content

    def test_depth_1_error_path_for_invalid_address(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """Addresses outside valid ranges should set cpuif_err."""
        rdl_source = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
        };

        addrmap top {
            child block @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=1)

        # Error path should exist in decode logic
        assert "cpuif_wr_sel.cpuif_err = 1'b1;" in content
        assert "cpuif_rd_sel.cpuif_err = 1'b1;" in content


# ===========================================================================
# 10. Protocol consistency
# ===========================================================================
class TestProtocolConsistency:
    """Verify that depth behavior is consistent across different cpuif protocols."""

    def _get_3level_rdl(self) -> str:
        return """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
        };

        addrmap top {
            child block @ 0x0;
        };
        """

    def test_apb3_depth_1(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        top = compile_rdl(self._get_3level_rdl(), top="top")
        content = _export_and_read(top, max_decode_depth=1, cpuif_cls=APB3Cpuif)
        assert "m_apb_block" in content
        assert "m_apb_reg1" not in content

    def test_apb4_depth_1(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        top = compile_rdl(self._get_3level_rdl(), top="top")
        content = _export_and_read(top, max_decode_depth=1, cpuif_cls=APB4Cpuif)
        assert "m_apb_block" in content
        assert "m_apb_reg1" not in content

    def test_axi4lite_depth_1(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        top = compile_rdl(self._get_3level_rdl(), top="top")
        content = _export_and_read(top, max_decode_depth=1, cpuif_cls=AXI4LiteCpuif)
        # AXI4-Lite uses m_axil_ prefix
        assert "m_axil_block" in content

    def test_apb3_depth_2(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        top = compile_rdl(self._get_3level_rdl(), top="top")
        content = _export_and_read(top, max_decode_depth=2, cpuif_cls=APB3Cpuif)
        assert "m_apb_reg1" in content
        assert "m_apb_block" not in content

    def test_apb4_depth_2(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        top = compile_rdl(self._get_3level_rdl(), top="top")
        content = _export_and_read(top, max_decode_depth=2, cpuif_cls=APB4Cpuif)
        assert "m_apb_reg1" in content
        assert "m_apb_block" not in content

    def test_axi4lite_depth_2(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        top = compile_rdl(self._get_3level_rdl(), top="top")
        content = _export_and_read(top, max_decode_depth=2, cpuif_cls=AXI4LiteCpuif)
        assert "m_axil_reg1" in content

    def test_all_protocols_produce_same_struct_depth_1(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """All protocols should produce the same select struct shape for depth=1."""
        rdl_source = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
        };
        addrmap top {
            child ca @ 0x0;
            child cb @ 0x100;
        };
        """
        top = compile_rdl(rdl_source, top="top")

        for cpuif_cls in (APB3Cpuif, APB4Cpuif, AXI4LiteCpuif):
            content = _export_and_read(top, max_decode_depth=1, cpuif_cls=cpuif_cls)
            # All protocols should have select struct with ca and cb
            assert "logic ca;" in content
            assert "logic cb;" in content


# ===========================================================================
# 11. Depth with cpuif_unroll interaction
# ===========================================================================
class TestDepthWithUnroll:
    """Verify that max_decode_depth interacts correctly with cpuif_unroll."""

    def test_depth_1_unrolled_array(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=1 with unrolled arrays should produce individual interfaces."""
        rdl_source = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
        };

        addrmap top {
            child blocks[4] @ 0x0 += 0x100;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=1, cpuif_unroll=True)

        # Unrolled should generate individual interfaces
        assert "blocks" in content


# ===========================================================================
# 12. Design state default and explicit values
# ===========================================================================
class TestDesignStateDepthConfig:
    """Test DesignState initialization with various depth values."""

    def test_default_depth_is_1(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        rdl = """
        addrmap top {
            reg { field { sw=rw; hw=r; } data[31:0]; } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="top")
        ds = DesignState(top, {})
        assert ds.max_decode_depth == 1

    def test_explicit_depth_0(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        rdl = """
        addrmap top {
            reg { field { sw=rw; hw=r; } data[31:0]; } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="top")
        ds = DesignState(top, {"max_decode_depth": 0})
        assert ds.max_decode_depth == 0

    def test_explicit_depth_3(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        rdl = """
        addrmap top {
            reg { field { sw=rw; hw=r; } data[31:0]; } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="top")
        ds = DesignState(top, {"max_decode_depth": 3})
        assert ds.max_decode_depth == 3

    def test_large_depth_value(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        rdl = """
        addrmap top {
            reg { field { sw=rw; hw=r; } data[31:0]; } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="top")
        ds = DesignState(top, {"max_decode_depth": 100})
        assert ds.max_decode_depth == 100


# ===========================================================================
# 13. Fanout/fanin path correctness at various depths
# ===========================================================================
class TestFanoutFaninPaths:
    """Verify that fanout and fanin use the correct hierarchical paths."""

    def test_depth_1_fanout_uses_top_level_name(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=1 fanout should reference top-level child name."""
        rdl_source = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
        };
        addrmap top {
            child blk @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=1)

        assert "m_apb_blk.PSEL" in content
        assert "cpuif_wr_sel.blk" in content
        assert "cpuif_rd_sel.blk" in content

    def test_depth_2_fanout_uses_hierarchical_path(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=2 fanout should reference hierarchical child.register path."""
        rdl_source = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
        };
        addrmap top {
            child blk @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=2)

        assert "m_apb_reg1.PSEL" in content
        assert "cpuif_wr_sel.blk.reg1" in content
        assert "cpuif_rd_sel.blk.reg1" in content

    def test_depth_0_fanin_references_all_leaves(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=0 fanin should reference all leaf register paths."""
        rdl_source = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } ra @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } rb @ 0x4;
        };
        addrmap top {
            child blk @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=0)

        # Fanin should have conditions for all leaf registers
        assert "cpuif_wr_sel.blk.ra" in content
        assert "cpuif_wr_sel.blk.rb" in content
        assert "cpuif_rd_sel.blk.ra" in content
        assert "cpuif_rd_sel.blk.rb" in content


# ===========================================================================
# 14. Complex hierarchies with multiple branches
# ===========================================================================
class TestComplexHierarchies:
    """Test depth with more complex, real-world-like hierarchies."""

    def test_depth_1_with_wide_hierarchy(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=1 with many top-level children of different types."""
        rdl_source = """
        regfile ctrl_rf {
            reg { field { sw=rw; hw=r; } data[31:0]; } ctrl_reg @ 0x0;
        };

        addrmap engine {
            reg { field { sw=rw; hw=r; } data[31:0]; } status @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } config @ 0x4;
        };

        addrmap top {
            ctrl_rf control @ 0x0;
            engine eng_a @ 0x100;
            engine eng_b @ 0x200;
            reg { field { sw=rw; hw=r; } data[31:0]; } version @ 0x300;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=1)

        # All four top-level children should have interfaces
        assert "m_apb_control" in content
        assert "m_apb_eng_a" in content
        assert "m_apb_eng_b" in content
        assert "m_apb_version" in content
        # No second-level interfaces
        assert "m_apb_ctrl_reg" not in content
        assert "m_apb_status" not in content
        assert "m_apb_config" not in content

    def test_depth_2_with_asymmetric_branches(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=2 where different branches have different depths of nesting."""
        rdl_source = """
        addrmap deep_child {
            reg { field { sw=rw; hw=r; } data[31:0]; } deep_reg @ 0x0;
        };

        addrmap shallow_child {
            reg { field { sw=rw; hw=r; } data[31:0]; } shallow_r1 @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } shallow_r2 @ 0x4;
        };

        addrmap wrapper {
            deep_child nested @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } wrapper_reg @ 0x100;
        };

        addrmap top {
            wrapper complex_blk @ 0x0;
            shallow_child simple_blk @ 0x1000;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=2)

        # Depth 2 nodes: inside complex_blk we get nested and wrapper_reg,
        # inside simple_blk we get shallow_r1 and shallow_r2
        assert "m_apb_nested" in content
        assert "m_apb_wrapper_reg" in content
        assert "m_apb_shallow_r1" in content
        assert "m_apb_shallow_r2" in content

        # Top-level addrmaps should NOT have their own interfaces
        assert "m_apb_complex_blk" not in content
        assert "m_apb_simple_blk" not in content
        # Deeper nodes should NOT be exposed
        assert "m_apb_deep_reg" not in content

    def test_depth_0_multi_branch_hierarchy(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=0 on a multi-branch hierarchy reaches all leaves.

        Each intermediate addrmap has a register to avoid the 'all external
        children' skip logic.
        """
        rdl_source = """
        addrmap leaf {
            reg { field { sw=rw; hw=r; } data[31:0]; } leaf_r @ 0x0;
        };

        addrmap mid {
            reg { field { sw=rw; hw=r; } data[31:0]; } mid_r @ 0x0;
            leaf leaf_a @ 0x10;
            leaf leaf_b @ 0x20;
        };

        addrmap top {
            mid side_a @ 0x0;
            mid side_b @ 0x100;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=0)

        # All leaf_r and mid_r instances should be referenced
        assert "m_apb_leaf_r" in content
        assert "m_apb_mid_r" in content
        # No intermediate interfaces
        assert "m_apb_side_a" not in content
        assert "m_apb_side_b" not in content
        assert "m_apb_leaf_a" not in content
        assert "m_apb_leaf_b" not in content


# ===========================================================================
# 15. Error signal generation at different depths
# ===========================================================================
class TestErrorSignalGeneration:
    """cpuif_err should always be generated in the select struct, regardless of depth."""

    def test_error_signal_in_struct_at_depth_1(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        rdl = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
        };
        addrmap top { child blk @ 0x0; };
        """
        top = compile_rdl(rdl, top="top")
        content = _export_and_read(top, max_decode_depth=1)
        assert "cpuif_err" in content

    def test_error_signal_in_struct_at_depth_0(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        rdl = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
        };
        addrmap top { child blk @ 0x0; };
        """
        top = compile_rdl(rdl, top="top")
        content = _export_and_read(top, max_decode_depth=0)
        assert "cpuif_err" in content

    def test_error_signal_in_struct_at_depth_3(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """Depth 3 on a 3-level hierarchy still has error signal."""
        rdl = """
        addrmap l2 {
            reg { field { sw=rw; hw=r; } data[31:0]; } l2_reg @ 0x0;
        };
        addrmap l1 {
            reg { field { sw=rw; hw=r; } data[31:0]; } l1_reg @ 0x0;
            l2 sub @ 0x10;
        };
        addrmap top {
            l1 blk @ 0x0;
        };
        """
        top = compile_rdl(rdl, top="top")
        content = _export_and_read(top, max_decode_depth=3)
        assert "cpuif_err" in content


# ===========================================================================
# 16. Depth with arrayed register components
# ===========================================================================
class TestDepthWithArrayedRegisters:
    """Verify correct behavior when registers themselves are arrayed."""

    def test_depth_1_arrayed_registers_at_top(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """Arrayed registers at top level with depth=1."""
        rdl_source = """
        addrmap top {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } my_regs[8] @ 0x0 += 0x4;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=1)

        # Arrayed register should be present
        assert "my_regs" in content

    def test_depth_2_arrayed_registers_inside_addrmap(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """Arrayed registers inside an addrmap with depth=2."""
        rdl_source = """
        addrmap child {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } status_regs[4] @ 0x0 += 0x4;
        };

        addrmap top {
            child block @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")
        content = _export_and_read(top, max_decode_depth=2)

        # At depth=2, we should see the arrayed register inside the addrmap
        assert "status_regs" in content
        assert "m_apb_block" not in content


# ===========================================================================
# 17. Depth comparison: same design at multiple depths
# ===========================================================================
class TestDepthComparison:
    """Compare generated output for the same design at different depth settings."""

    def test_increasing_depth_increases_interfaces(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """Increasing depth should expose more (or equal) interfaces."""
        rdl_source = """
        addrmap level2 {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg2 @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg2b @ 0x4;
        };

        addrmap level1 {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
            level2 inner2 @ 0x10;
        };

        addrmap top {
            level1 inner1 @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")

        # depth=1: 1 interface (inner1)
        c1 = _export_and_read(top, max_decode_depth=1)
        n1 = c1.count("apb4_intf.master")

        # depth=2: 2 interfaces (reg1, inner2)
        c2 = _export_and_read(top, max_decode_depth=2)
        n2 = c2.count("apb4_intf.master")

        # depth=0: 3 interfaces (reg1, reg2, reg2b)
        c0 = _export_and_read(top, max_decode_depth=0)
        n0 = c0.count("apb4_intf.master")

        assert n1 == 1
        assert n2 == 2
        assert n0 == 3

    def test_depth_1_vs_2_struct_complexity(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """depth=2 should produce more complex structs than depth=1."""
        rdl_source = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg2 @ 0x4;
        };

        addrmap top {
            child block @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")

        c1 = _export_and_read(top, max_decode_depth=1)
        c2 = _export_and_read(top, max_decode_depth=2)

        # depth=1: flat struct (no nested types)
        assert "cpuif_sel_block_t" not in c1
        assert "logic block;" in c1

        # depth=2: nested struct
        assert "cpuif_sel_block_t" in c2
        assert "logic reg1;" in c2
        assert "logic reg2;" in c2
