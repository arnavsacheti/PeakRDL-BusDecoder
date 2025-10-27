from collections.abc import Callable

from systemrdl.node import AddrmapNode

from peakrdl_busdecoder.design_state import DesignState
from peakrdl_busdecoder.struct_gen import StructGenerator


class TestStructGenerator:
    """Test the StructGenerator."""

    def test_simple_struct_generation(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
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

    def test_nested_struct_generation(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
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

    def test_array_struct_generation(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
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
        # Should use unpacked array syntax (name[size]), not packed bit-vector ([size:0]name)
        assert "my_regs[4]" in result
        # Should NOT use packed bit-vector syntax
        assert "[3:0]my_regs" not in result
        # Should be unpacked struct, not packed
        assert "typedef struct {" in result
        assert "typedef struct packed" not in result
