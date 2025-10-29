"""Test max_decode_depth parameter behavior."""

from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif


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

    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif, max_decode_depth=1)

        module_file = Path(tmpdir) / "level0.sv"
        content = module_file.read_text()

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

    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif, max_decode_depth=2)

        module_file = Path(tmpdir) / "level0.sv"
        content = module_file.read_text()

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

    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif, max_decode_depth=0)

        module_file = Path(tmpdir) / "level0.sv"
        content = module_file.read_text()

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
    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif, max_decode_depth=1)

        module_file = Path(tmpdir) / "level0.sv"
        content = module_file.read_text()

        assert "cpuif_wr_sel.inner1 = 1'b1;" in content
        assert "cpuif_wr_sel.inner1.reg1" not in content

    # Test depth=2: should set cpuif_wr_sel.inner1.reg1
    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif, max_decode_depth=2)

        module_file = Path(tmpdir) / "level0.sv"
        content = module_file.read_text()

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
    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif, max_decode_depth=1)

        module_file = Path(tmpdir) / "level0.sv"
        content = module_file.read_text()

        assert "m_apb_inner1.PSEL" in content
        assert "m_apb_reg1.PSEL" not in content

    # Test depth=2: should have fanout for reg1
    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif, max_decode_depth=2)

        module_file = Path(tmpdir) / "level0.sv"
        content = module_file.read_text()

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

    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif, max_decode_depth=3)

        module_file = Path(tmpdir) / "level0.sv"
        content = module_file.read_text()

        # Should have interfaces at depth 3: reg2, inner3
        # (reg1 is at depth 2, not 3)
        assert "m_apb_reg2" in content
        assert "m_apb_inner3" in content
        # Should NOT have interfaces at other depths
        assert "m_apb_inner1" not in content
        assert "m_apb_inner2" not in content
        assert "m_apb_reg1" not in content
        assert "m_apb_reg3" not in content
