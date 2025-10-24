"""
Integration tests for cocotb testbench infrastructure.

These tests validate that the code generation and testbench setup works correctly
without requiring an actual HDL simulator. They check:
- RDL compilation and SystemVerilog generation
- Generated code contains expected elements
- Testbench utilities work correctly
"""

import tempfile
from pathlib import Path

import pytest

from peakrdl_busdecoder.cpuif.apb3 import APB3Cpuif
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif
from peakrdl_busdecoder.cpuif.axi4lite import AXI4LiteCpuif

from ..common.utils import compile_rdl_and_export, get_verilog_sources


class TestCodeGeneration:
    """Test code generation for different CPU interfaces."""

    def test_apb4_simple_register(self):
        """Test APB4 code generation for simple register."""
        rdl_source = """
        addrmap simple_test {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } test_reg @ 0x0;
        };
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            module_path, package_path = compile_rdl_and_export(
                rdl_source, "simple_test", tmpdir, APB4Cpuif
            )

            # Verify files exist
            assert module_path.exists()
            assert package_path.exists()

            # Verify module content
            module_content = module_path.read_text()
            assert "module simple_test" in module_content
            assert "apb4_intf.slave s_apb" in module_content
            assert "test_reg" in module_content

            # Verify package content
            package_content = package_path.read_text()
            assert "package simple_test_pkg" in package_content

    def test_apb3_multiple_registers(self):
        """Test APB3 code generation for multiple registers."""
        rdl_source = """
        addrmap multi_reg {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x0;
            reg { field { sw=r; hw=w; } status[15:0]; } reg2 @ 0x4;
            reg { field { sw=rw; hw=r; } control[7:0]; } reg3 @ 0x8;
        };
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            module_path, package_path = compile_rdl_and_export(
                rdl_source, "multi_reg", tmpdir, APB3Cpuif
            )

            assert module_path.exists()
            assert package_path.exists()

            module_content = module_path.read_text()
            assert "module multi_reg" in module_content
            assert "apb3_intf.slave s_apb" in module_content
            assert "reg1" in module_content
            assert "reg2" in module_content
            assert "reg3" in module_content

    def test_axi4lite_nested_addrmap(self):
        """Test AXI4-Lite code generation for nested address map."""
        rdl_source = """
        addrmap inner_block {
            reg { field { sw=rw; hw=r; } data[31:0]; } inner_reg @ 0x0;
        };
        
        addrmap outer_block {
            inner_block inner @ 0x0;
            reg { field { sw=rw; hw=r; } outer_data[31:0]; } outer_reg @ 0x100;
        };
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            module_path, package_path = compile_rdl_and_export(
                rdl_source, "outer_block", tmpdir, AXI4LiteCpuif
            )

            assert module_path.exists()
            assert package_path.exists()

            module_content = module_path.read_text()
            assert "module outer_block" in module_content
            assert "axi4lite_intf.slave s_axi" in module_content
            assert "inner" in module_content
            assert "outer_reg" in module_content

    def test_register_array(self):
        """Test code generation with register arrays."""
        rdl_source = """
        addrmap array_test {
            reg { field { sw=rw; hw=r; } data[31:0]; } regs[4] @ 0x0 += 0x4;
        };
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            module_path, package_path = compile_rdl_and_export(
                rdl_source, "array_test", tmpdir, APB4Cpuif
            )

            assert module_path.exists()
            assert package_path.exists()

            module_content = module_path.read_text()
            assert "module array_test" in module_content
            assert "regs" in module_content


class TestUtilityFunctions:
    """Test utility functions for testbench setup."""

    def test_get_verilog_sources(self):
        """Test that get_verilog_sources returns correct file list."""
        hdl_src_dir = Path(__file__).parent.parent.parent.parent / "hdl-src"

        module_path = Path("/tmp/test_module.sv")
        package_path = Path("/tmp/test_pkg.sv")
        intf_files = [
            hdl_src_dir / "apb4_intf.sv",
            hdl_src_dir / "apb3_intf.sv",
        ]

        sources = get_verilog_sources(module_path, package_path, intf_files)

        # Verify order: interfaces first, then package, then module
        assert len(sources) == 4
        assert str(intf_files[0]) in sources[0]
        assert str(intf_files[1]) in sources[1]
        assert str(package_path) in sources[2]
        assert str(module_path) in sources[3]

    def test_compile_rdl_and_export_with_custom_names(self):
        """Test code generation with custom module and package names."""
        rdl_source = """
        addrmap test_map {
            reg { field { sw=rw; hw=r; } data[31:0]; } test_reg @ 0x0;
        };
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            module_path, package_path = compile_rdl_and_export(
                rdl_source,
                "test_map",
                tmpdir,
                APB4Cpuif,
                module_name="custom_module",
                package_name="custom_pkg",
            )

            # Verify custom names
            assert module_path.name == "custom_module.sv"
            assert package_path.name == "custom_pkg.sv"

            # Verify content uses custom names
            module_content = module_path.read_text()
            assert "module custom_module" in module_content

            package_content = package_path.read_text()
            assert "package custom_pkg" in package_content


class TestMultipleCpuInterfaces:
    """Test that all CPU interfaces generate valid code."""

    @pytest.mark.parametrize(
        "cpuif_cls,intf_name",
        [
            (APB3Cpuif, "apb3_intf"),
            (APB4Cpuif, "apb4_intf"),
            (AXI4LiteCpuif, "axi4lite_intf"),
        ],
    )
    def test_cpuif_generation(self, cpuif_cls, intf_name):
        """Test code generation for each CPU interface type."""
        rdl_source = """
        addrmap test_block {
            reg {
                field { sw=rw; hw=r; } data[31:0];
            } test_reg @ 0x0;
        };
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            module_path, package_path = compile_rdl_and_export(
                rdl_source, "test_block", tmpdir, cpuif_cls
            )

            assert module_path.exists()
            assert package_path.exists()

            module_content = module_path.read_text()
            assert "module test_block" in module_content
            assert intf_name in module_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
