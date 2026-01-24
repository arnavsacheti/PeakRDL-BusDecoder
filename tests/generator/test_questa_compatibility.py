"""Test Questa simulator compatibility for instance arrays."""

from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif


def test_instance_array_questa_compatibility(compile_rdl: Callable[..., AddrmapNode]) -> None:
    """Test that instance arrays generate Questa-compatible code.

    This test ensures that:
    - Struct members for arrays use unpacked array syntax (name[dim])
    - NOT packed bit-vector syntax ([dim-1:0]name)
    - Struct is unpacked (not packed)
    - Array indexing with loop variables works correctly

    This fixes the error: "Nonconstant index into instance array"
    """
    rdl_source = """
    addrmap test_map {
        reg {
            field {
                sw=rw;
                hw=r;
            } data[31:0];
        } my_reg[4] @ 0x0 += 0x10;
    };
    """
    top = compile_rdl(rdl_source, top="test_map")

    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif)

        # Read the generated module
        module_file = Path(tmpdir) / "test_map.sv"
        content = module_file.read_text()

        # Should use unpacked struct
        assert "typedef struct {" in content
        assert "typedef struct packed" not in content
        # Should use unpacked array syntax for array members (parameterized)
        assert "logic my_reg[N_MY_REGS];" in content

        # Should NOT use packed bit-vector syntax
        assert "[3:0]my_reg" not in content

        # Should have proper array indexing in decode logic
        assert "cpuif_wr_sel.my_reg[i0] = 1'b1;" in content
        assert "cpuif_rd_sel.my_reg[i0] = 1'b1;" in content

        # Should have proper array indexing in fanout/fanin logic
        assert "cpuif_wr_sel.my_reg[gi0]" in content or "cpuif_rd_sel.my_reg[gi0]" in content
        assert "cpuif_wr_sel.my_reg[i0]" in content or "cpuif_rd_sel.my_reg[i0]" in content


def test_multidimensional_array_questa_compatibility(compile_rdl: Callable[..., AddrmapNode]) -> None:
    """Test that multidimensional instance arrays generate Questa-compatible code."""
    rdl_source = """
    addrmap test_map {
        reg {
            field {
                sw=rw;
                hw=r;
            } data[31:0];
        } my_reg[2][3] @ 0x0 += 0x10;
    };
    """
    top = compile_rdl(rdl_source, top="test_map")

    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif)

        # Read the generated module
        module_file = Path(tmpdir) / "test_map.sv"
        content = module_file.read_text()

        # Should use unpacked struct with multidimensional array
        assert "typedef struct {" in content
        # Should use unpacked array syntax for multidimensional arrays (parameterized)
        assert "logic my_reg[N_MY_REGS_0][N_MY_REGS_1];" in content

        # Should NOT use packed bit-vector syntax
        assert "[1:0][2:0]my_reg" not in content
        assert "[5:0]my_reg" not in content


def test_nested_instance_array_questa_compatibility(compile_rdl: Callable[..., AddrmapNode]) -> None:
    """Test that nested instance arrays generate Questa-compatible code."""
    rdl_source = """
    addrmap inner_map {
        reg {
            field {
                sw=rw;
                hw=r;
            } data[31:0];
        } inner_reg[2] @ 0x0 += 0x10;
    };
    
    addrmap outer_map {
        inner_map inner[3] @ 0x0 += 0x100;
    };
    """
    top = compile_rdl(rdl_source, top="outer_map")

    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif)

        # Read the generated module
        module_file = Path(tmpdir) / "outer_map.sv"
        content = module_file.read_text()

        # Should use unpacked struct
        assert "typedef struct {" in content

        # Inner should be an array
        # The exact syntax may vary, but it should be unpacked
        # Look for the pattern of unpacked arrays, not packed bit-vectors
        assert "inner[3]" in content or "logic inner" in content

        # Should NOT use packed bit-vector syntax like [2:0]inner
        assert "[2:0]inner" not in content
