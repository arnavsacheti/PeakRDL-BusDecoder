from collections.abc import Callable
from pathlib import Path

import pytest
from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif


class TestAPB4Interface:
    """Test APB4 CPU interface generation."""

    def test_apb4_port_declaration(self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path) -> None:
        """Test that APB4 interface ports are generated."""
        rdl_source = """
        addrmap apb_test {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="apb_test")

        exporter = BusDecoderExporter()
        output_dir = str(tmp_path)
        exporter.export(top, output_dir, cpuif_cls=APB4Cpuif)

        module_file = tmp_path / "apb_test.sv"
        module_content = module_file.read_text()

        # Check for APB4 signals
        assert "PSEL" in module_content or "psel" in module_content
        assert "PENABLE" in module_content or "penable" in module_content
        assert "PWRITE" in module_content or "pwrite" in module_content
        assert "PADDR" in module_content or "paddr" in module_content
        assert "PWDATA" in module_content or "pwdata" in module_content
        assert "PRDATA" in module_content or "prdata" in module_content
        assert "PREADY" in module_content or "pready" in module_content

    def test_apb4_read_write_logic(self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path) -> None:
        """Test that APB4 read/write logic is generated."""
        rdl_source = """
        addrmap apb_rw {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="apb_rw")

        exporter = BusDecoderExporter()
        output_dir = str(tmp_path)
        exporter.export(top, output_dir, cpuif_cls=APB4Cpuif)

        module_file = tmp_path / "apb_rw.sv"
        module_content = module_file.read_text()

        # Basic sanity checks for logic generation
        assert "always" in module_content or "assign" in module_content
        assert "my_reg" in module_content

    def test_nested_addrmap_with_array_stride(self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path) -> None:
        """Test that nested addrmaps with arrays use correct stride values."""
        rdl_source = """
        addrmap inner_block {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } inner_reg @ 0x0;
        };
        
        addrmap outer_block {
            inner_block inner[4] @ 0x0 += 0x100;
            
            reg {
                field {
                    sw=rw;
                    hw=r;
                } outer_data[31:0];
            } outer_reg @ 0x400;
        };
        """
        top = compile_rdl(rdl_source, top="outer_block")

        exporter = BusDecoderExporter()
        output_dir = str(tmp_path)
        exporter.export(top, output_dir, cpuif_cls=APB4Cpuif)

        module_file = tmp_path / "outer_block.sv"
        module_content = module_file.read_text()

        # Check that the generated code uses the correct stride (0x100 = 256)
        # not the array dimension (4)
        # The decode logic should contain something like: i0)*11'h100 or i0)*256
        assert "i0)*11'h100" in module_content or "i0)*'h100" in module_content, (
            "Array stride should be 0x100 (256), not the dimension value (4)"
        )

        # Ensure it's NOT using the incorrect dimension value
        assert "i0)*11'h4" not in module_content and "i0)*4" not in module_content, (
            "Should not use array dimension (4) as stride"
        )

    @pytest.mark.skip(reason="Known issue with multidimensional array stride calculation")
    def test_multidimensional_array_strides(self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path) -> None:
        """Test that multidimensional arrays calculate correct strides for each dimension."""
        rdl_source = """
        addrmap test_block {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } my_reg[2][3] @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="test_block")

        exporter = BusDecoderExporter()
        output_dir = str(tmp_path)
        exporter.export(top, output_dir, cpuif_cls=APB4Cpuif)

        module_file = tmp_path / "test_block.sv"
        module_content = module_file.read_text()

        # For a [2][3] array where each register is 4 bytes:
        # i0 (leftmost/slowest) should have stride = 3 * 4 = 12 (0xc)
        # i1 (rightmost/fastest) should have stride = 4 (0x4)
        assert "i0)*5'hc" in module_content or "i0)*12" in module_content, (
            "i0 should use stride 12 (0xc) for [2][3] array"
        )
        assert "i1)*5'h4" in module_content or "i1)*4" in module_content, (
            "i1 should use stride 4 for [2][3] array"
        )
