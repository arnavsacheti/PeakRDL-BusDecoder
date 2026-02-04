from collections.abc import Callable

from systemrdl.node import AddrmapNode

from peakrdl_busdecoder.design_state import DesignState


class TestDesignState:
    """Test the DesignState class."""

    def test_design_state_basic(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Test basic DesignState initialization."""
        rdl_source = """
        addrmap test {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="test")

        ds = DesignState(top, {})

        assert ds.top_node == top
        assert ds.module_name == "test"
        assert ds.package_name == "test_pkg"
        assert ds.cpuif_data_width == 32  # Should infer from 32-bit field
        assert ds.addr_width > 0

    def test_design_state_custom_module_name(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Test DesignState with custom module name."""
        rdl_source = """
        addrmap test {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="test")

        ds = DesignState(top, {"module_name": "custom_module"})

        assert ds.module_name == "custom_module"
        assert ds.package_name == "custom_module_pkg"

    def test_design_state_custom_package_name(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Test DesignState with custom package name."""
        rdl_source = """
        addrmap test {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="test")

        ds = DesignState(top, {"package_name": "custom_pkg"})

        assert ds.package_name == "custom_pkg"

    def test_design_state_custom_address_width(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Test DesignState with custom address width."""
        rdl_source = """
        addrmap test {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="test")

        ds = DesignState(top, {"address_width": 16})

        assert ds.addr_width == 16

    def test_design_state_unroll_arrays(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Test DesignState with cpuif_unroll option."""
        rdl_source = """
        addrmap test {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } my_regs[4] @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="test")

        ds = DesignState(top, {"cpuif_unroll": True})

        assert ds.cpuif_unroll is True

    def test_design_state_64bit_registers(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Test DesignState with wider data width."""
        rdl_source = """
        addrmap test {
            reg {
                regwidth = 32;
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="test")

        ds = DesignState(top, {})

        # Should infer 32-bit data width from field
        assert ds.cpuif_data_width == 32

    def test_design_state_accesswidth_64(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Test DesignState with explicit 64-bit access width."""
        rdl_source = """
        addrmap test {
            reg {
                regwidth = 64;
                accesswidth = 64;
                field {
                    sw=rw;
                    hw=r;
                } data[63:0];
            } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="test")

        ds = DesignState(top, {})

        assert ds.cpuif_data_width == 64

    def test_design_state_accesswidth_128(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Test DesignState with explicit 128-bit access width."""
        rdl_source = """
        addrmap test {
            reg {
                regwidth = 128;
                accesswidth = 128;
                field {
                    sw=rw;
                    hw=r;
                } data[127:0];
            } my_reg @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="test")

        ds = DesignState(top, {})

        assert ds.cpuif_data_width == 128
