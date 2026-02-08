from collections.abc import Callable

from systemrdl.node import AddrmapNode
from systemrdl.walker import RDLSteerableWalker

from peakrdl_busdecoder.decode_logic_gen import DecodeLogicFlavor, DecodeLogicGenerator
from peakrdl_busdecoder.design_state import DesignState


class TestDecodeLogicGenerator:
    """Test the DecodeLogicGenerator."""

    def test_decode_logic_read(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
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

    def test_decode_logic_write(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
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

    def test_cpuif_addr_predicate(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
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

    def test_decode_logic_flavor_enum(self) -> None:
        """Test DecodeLogicFlavor enum values."""
        assert DecodeLogicFlavor.READ.value == "rd"
        assert DecodeLogicFlavor.WRITE.value == "wr"

        assert DecodeLogicFlavor.READ.cpuif_address == "cpuif_rd_addr"
        assert DecodeLogicFlavor.WRITE.cpuif_address == "cpuif_wr_addr"

        assert DecodeLogicFlavor.READ.cpuif_select == "cpuif_rd_sel"
        assert DecodeLogicFlavor.WRITE.cpuif_select == "cpuif_wr_sel"


def _walk_generator(ds: DesignState, flavor: DecodeLogicFlavor) -> str:
    """Walk a design and return the generated decode logic string."""
    gen = DecodeLogicGenerator(ds, flavor)
    walker = RDLSteerableWalker()
    walker.walk(ds.top_node, gen, skip_top=True)
    return str(gen)


class TestBinarySearchDecoder:
    """Test binary search optimization in address decoder."""

    def test_many_registers_uses_binary_search(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """With >3 children, decoder should produce a binary search tree."""
        rdl_source = """
        addrmap test {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg0 @ 0x000;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x100;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg2 @ 0x200;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg3 @ 0x300;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg4 @ 0x400;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg5 @ 0x500;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg6 @ 0x600;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg7 @ 0x700;
        };
        """
        top = compile_rdl(rdl_source, top="test")
        ds = DesignState(top, {})

        result = _walk_generator(ds, DecodeLogicFlavor.WRITE)

        # Binary search should produce split comparisons using bare "addr <" checks
        # (as opposed to the range checks "addr >= ... && addr < ..." used at leaves)
        assert "cpuif_wr_addr < " in result

        # All registers should appear in the output
        for i in range(8):
            assert f"reg{i}" in result

        # Binary search produces multiple cpuif_err assignments (one per leaf group)
        # whereas linear would produce only one
        err_count = result.count("cpuif_wr_sel.cpuif_err = 1'b1;")
        assert err_count > 1

    def test_few_registers_uses_linear(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """With <=3 children, decoder should use linear if-else-if."""
        rdl_source = """
        addrmap test {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg0 @ 0x0;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x4;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg2 @ 0x8;
        };
        """
        top = compile_rdl(rdl_source, top="test")
        ds = DesignState(top, {})

        result = _walk_generator(ds, DecodeLogicFlavor.WRITE)

        # All registers should appear
        for i in range(3):
            assert f"reg{i}" in result

        # Linear decoder should have exactly one cpuif_err assignment
        err_count = result.count("cpuif_wr_sel.cpuif_err = 1'b1;")
        assert err_count == 1

    def test_binary_search_with_four_registers(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Exactly 4 children (above threshold of 3) should trigger binary search."""
        rdl_source = """
        addrmap test {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg0 @ 0x000;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x100;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg2 @ 0x200;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg3 @ 0x300;
        };
        """
        top = compile_rdl(rdl_source, top="test")
        ds = DesignState(top, {})

        result = _walk_generator(ds, DecodeLogicFlavor.WRITE)

        # 4 entries split into [0:2] and [2:4], each with 2 entries (linear leaf)
        # Should see a split comparison
        assert "cpuif_wr_addr < " in result

        # Should have 2 cpuif_err assignments (one per leaf group)
        err_count = result.count("cpuif_wr_sel.cpuif_err = 1'b1;")
        assert err_count == 2

    def test_binary_search_read_flavor(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Binary search should work for read decoder as well."""
        rdl_source = """
        addrmap test {
            reg { field { sw=rw; hw=r; } data[31:0]; } reg0 @ 0x000;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg1 @ 0x100;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg2 @ 0x200;
            reg { field { sw=rw; hw=r; } data[31:0]; } reg3 @ 0x300;
        };
        """
        top = compile_rdl(rdl_source, top="test")
        ds = DesignState(top, {})

        result = _walk_generator(ds, DecodeLogicFlavor.READ)

        # Should use cpuif_rd_addr for binary search splits
        assert "cpuif_rd_addr < " in result
        assert "cpuif_rd_sel" in result

    def test_binary_search_with_mixed_array_and_nonarray(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """Binary search should work with a mix of arrayed and non-arrayed children."""
        rdl_source = """
        addrmap child {
            reg { field { sw=rw; hw=r; } data[31:0]; } inner_reg @ 0x0;
        };

        addrmap test {
            external child c0 @ 0x0000;
            external child c1 @ 0x1000;
            external child c2[2] @ 0x2000 += 0x1000;
            external child c3 @ 0x4000;
        };
        """
        top = compile_rdl(rdl_source, top="test")
        ds = DesignState(top, {})

        result = _walk_generator(ds, DecodeLogicFlavor.WRITE)

        # All children should appear
        assert "c0" in result
        assert "c1" in result
        assert "c2" in result
        assert "c3" in result

        # With 4 branches, binary search should be active
        assert "cpuif_wr_addr < " in result
