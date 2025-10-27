from collections.abc import Callable
from pathlib import Path

from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif


class TestBusDecoderExporter:
    """Test the top-level BusDecoderExporter."""

    def test_simple_register_export(self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path) -> None:
        """Test exporting a simple register."""
        rdl_source = """
        addrmap simple_reg {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="simple_reg")

        exporter = BusDecoderExporter()
        output_dir = str(tmp_path)
        exporter.export(top, output_dir, cpuif_cls=APB4Cpuif)

        # Check that output files are created
        module_file = tmp_path / "simple_reg.sv"
        package_file = tmp_path / "simple_reg_pkg.sv"

        assert module_file.exists()
        assert package_file.exists()

        # Check basic content
        module_content = module_file.read_text()
        assert "module simple_reg" in module_content
        assert "my_reg" in module_content

        package_content = package_file.read_text()
        assert "package simple_reg_pkg" in package_content

    def test_register_array_export(self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path) -> None:
        """Test exporting a register array."""
        rdl_source = """
        addrmap reg_array {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } my_regs[4] @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="reg_array")

        exporter = BusDecoderExporter()
        output_dir = str(tmp_path)
        exporter.export(top, output_dir, cpuif_cls=APB4Cpuif)

        # Check that output files are created
        module_file = tmp_path / "reg_array.sv"
        assert module_file.exists()

        module_content = module_file.read_text()
        assert "module reg_array" in module_content
        assert "my_regs" in module_content

    def test_nested_addrmap_export(self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path) -> None:
        """Test exporting nested addrmaps."""
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
            inner_block inner @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="outer_block")

        exporter = BusDecoderExporter()
        output_dir = str(tmp_path)
        exporter.export(top, output_dir, cpuif_cls=APB4Cpuif)

        # Check that output files are created
        module_file = tmp_path / "outer_block.sv"
        assert module_file.exists()

        module_content = module_file.read_text()
        assert "module outer_block" in module_content
        assert "inner" in module_content
        assert "inner_reg" in module_content

    def test_custom_module_name(self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path) -> None:
        """Test exporting with custom module name."""
        rdl_source = """
        addrmap my_addrmap {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="my_addrmap")

        exporter = BusDecoderExporter()
        output_dir = str(tmp_path)
        exporter.export(top, output_dir, module_name="custom_module", cpuif_cls=APB4Cpuif)

        # Check that output files use custom name
        module_file = tmp_path / "custom_module.sv"
        package_file = tmp_path / "custom_module_pkg.sv"

        assert module_file.exists()
        assert package_file.exists()

        module_content = module_file.read_text()
        assert "module custom_module" in module_content

    def test_custom_package_name(self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path) -> None:
        """Test exporting with custom package name."""
        rdl_source = """
        addrmap my_addrmap {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="my_addrmap")

        exporter = BusDecoderExporter()
        output_dir = str(tmp_path)
        exporter.export(top, output_dir, package_name="custom_pkg", cpuif_cls=APB4Cpuif)

        # Check that output files use custom package name
        package_file = tmp_path / "custom_pkg.sv"
        assert package_file.exists()

        package_content = package_file.read_text()
        assert "package custom_pkg" in package_content

    def test_multiple_registers(self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path) -> None:
        """Test exporting multiple registers."""
        rdl_source = """
        addrmap multi_reg {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } reg1 @ 0x0;
            
            reg {
                field {
                    sw=r;
                    hw=w;
                } status[15:0];
            } reg2 @ 0x4;
            
            reg {
                field {
                    sw=rw;
                    hw=r;
                } control[7:0];
            } reg3 @ 0x8;
        };
        """
        top = compile_rdl(rdl_source, top="multi_reg")

        exporter = BusDecoderExporter()
        output_dir = str(tmp_path)
        exporter.export(top, output_dir, cpuif_cls=APB4Cpuif)

        module_file = tmp_path / "multi_reg.sv"
        assert module_file.exists()

        module_content = module_file.read_text()
        assert "module multi_reg" in module_content
        assert "reg1" in module_content
        assert "reg2" in module_content
        assert "reg3" in module_content

    def test_master_address_widths_export(
        self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
    ) -> None:
        """Test exporting master address width parameters for child addrmaps."""
        rdl_source = """
        addrmap child1 {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } reg1 @ 0x0;
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } reg2 @ 0x4;
        };
        
        addrmap child2 {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[15:0];
            } reg2 @ 0x0;
        };
        
        addrmap parent {
            external child1 c1 @ 0x0000;
            external child2 c2 @ 0x1000;
        };
        """
        top = compile_rdl(rdl_source, top="parent")

        exporter = BusDecoderExporter()
        output_dir = str(tmp_path)
        exporter.export(top, output_dir, cpuif_cls=APB4Cpuif)

        package_file = tmp_path / "parent_pkg.sv"
        assert package_file.exists()

        package_content = package_file.read_text()
        assert "package parent_pkg" in package_content
        # Check for master address width parameters
        assert "localparam PARENT_C1_ADDR_WIDTH = 3" in package_content
        assert "localparam PARENT_C2_ADDR_WIDTH = 2" in package_content

    def test_master_address_widths_with_arrays(
        self, compile_rdl: Callable[..., AddrmapNode], tmp_path: Path
    ) -> None:
        """Test exporting master address width parameters for arrayed child addrmaps."""
        rdl_source = """
        addrmap child {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } reg1 @ 0x0;
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } reg2 @ 0x4;
        };
        
        addrmap parent {
            external child children[4] @ 0x0 += 0x100;
        };
        """
        top = compile_rdl(rdl_source, top="parent")

        exporter = BusDecoderExporter()
        output_dir = str(tmp_path)
        exporter.export(top, output_dir, cpuif_cls=APB4Cpuif)

        package_file = tmp_path / "parent_pkg.sv"
        assert package_file.exists()

        package_content = package_file.read_text()
        assert "package parent_pkg" in package_content
        # Check for master address width parameter - array should have a single parameter
        assert "localparam PARENT_CHILDREN_ADDR_WIDTH = 3" in package_content
