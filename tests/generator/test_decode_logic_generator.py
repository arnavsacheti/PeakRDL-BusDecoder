from collections.abc import Callable

from systemrdl.node import AddrmapNode

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
