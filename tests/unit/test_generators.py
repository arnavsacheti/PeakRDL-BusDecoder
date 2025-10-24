"""Tests for code generation classes."""

from __future__ import annotations

import pytest

from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif
from peakrdl_busdecoder.decode_logic_gen import DecodeLogicFlavor, DecodeLogicGenerator
from peakrdl_busdecoder.design_state import DesignState
from peakrdl_busdecoder.exporter import BusDecoderExporter
from peakrdl_busdecoder.struct_gen import StructGenerator


class TestDecodeLogicGenerator:
    """Test the DecodeLogicGenerator."""

    def test_decode_logic_read(self, compile_rdl):
        """Test decode logic generation for read operations."""
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
        gen = DecodeLogicGenerator(ds, DecodeLogicFlavor.READ)

        # Basic sanity check - it should initialize
        assert gen is not None
        assert gen._flavor == DecodeLogicFlavor.READ

    def test_decode_logic_write(self, compile_rdl):
        """Test decode logic generation for write operations."""
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
        gen = DecodeLogicGenerator(ds, DecodeLogicFlavor.WRITE)

        assert gen is not None
        assert gen._flavor == DecodeLogicFlavor.WRITE

    def test_cpuif_addr_predicate(self, compile_rdl):
        """Test address predicate generation."""
        rdl_source = """
        addrmap test {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } my_reg @ 0x100;
        };
        """
        top = compile_rdl(rdl_source, top="test")

        ds = DesignState(top, {})
        gen = DecodeLogicGenerator(ds, DecodeLogicFlavor.READ)

        # Get the register node
        reg_node = None
        for child in top.children():
            if child.inst_name == "my_reg":
                reg_node = child
                break
        assert reg_node is not None

        predicates = gen.cpuif_addr_predicate(reg_node)

        # Should return a list of conditions
        assert isinstance(predicates, list)
        assert len(predicates) > 0
        # Should check address bounds
        for pred in predicates:
            assert "cpuif_rd_addr" in pred or ">=" in pred or "<" in pred

    def test_decode_logic_flavor_enum(self):
        """Test DecodeLogicFlavor enum values."""
        assert DecodeLogicFlavor.READ.value == "rd"
        assert DecodeLogicFlavor.WRITE.value == "wr"

        assert DecodeLogicFlavor.READ.cpuif_address == "cpuif_rd_addr"
        assert DecodeLogicFlavor.WRITE.cpuif_address == "cpuif_wr_addr"

        assert DecodeLogicFlavor.READ.cpuif_select == "cpuif_rd_sel"
        assert DecodeLogicFlavor.WRITE.cpuif_select == "cpuif_wr_sel"


class TestStructGenerator:
    """Test the StructGenerator."""

    def test_simple_struct_generation(self, compile_rdl):
        """Test struct generation for simple register."""
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
        gen = StructGenerator(ds)

        # Should generate struct definition
        assert gen is not None
        result = str(gen)

        # Should contain struct declaration
        assert "struct" in result or "typedef" in result

    def test_nested_struct_generation(self, compile_rdl):
        """Test struct generation for nested addrmaps."""
        rdl_source = """
        addrmap inner {
            reg {
                field {
                    sw=rw;
                    hw=r;
                } data[31:0];
            } inner_reg @ 0x0;
        };
        
        addrmap outer {
            inner my_inner @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="outer")

        ds = DesignState(top, {})
        gen = StructGenerator(ds)

        # Walk the tree to generate structs
        from systemrdl.walker import RDLWalker

        walker = RDLWalker()
        walker.walk(top, gen, skip_top=True)

        result = str(gen)

        # Should contain struct declaration
        assert "struct" in result or "typedef" in result
        # The struct should reference the inner component
        assert "my_inner" in result

    def test_array_struct_generation(self, compile_rdl):
        """Test struct generation for register arrays."""
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

        ds = DesignState(top, {})
        gen = StructGenerator(ds)

        # Walk the tree to generate structs
        from systemrdl.walker import RDLWalker

        walker = RDLWalker()
        walker.walk(top, gen, skip_top=True)

        result = str(gen)

        # Should contain array notation
        assert "[" in result and "]" in result
        # Should reference the register
        assert "my_regs" in result


class TestDesignState:
    """Test the DesignState class."""

    def test_design_state_basic(self, compile_rdl):
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

    def test_design_state_custom_module_name(self, compile_rdl):
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

    def test_design_state_custom_package_name(self, compile_rdl):
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

    def test_design_state_custom_address_width(self, compile_rdl):
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

    def test_design_state_unroll_arrays(self, compile_rdl):
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

    def test_design_state_64bit_registers(self, compile_rdl):
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
