from peakrdl_busdecoder.decode_logic_gen import DecodeLogicFlavor


class TestDecodeLogicFlavor:
    """Test the public decode flavor values and signal names."""

    def test_decode_logic_flavor_enum(self) -> None:
        """Test DecodeLogicFlavor enum values."""
        assert DecodeLogicFlavor.READ.value == "rd"
        assert DecodeLogicFlavor.WRITE.value == "wr"

        assert DecodeLogicFlavor.READ.cpuif_address == "cpuif_rd_addr"
        assert DecodeLogicFlavor.WRITE.cpuif_address == "cpuif_wr_addr"

        assert DecodeLogicFlavor.READ.cpuif_select == "cpuif_rd_sel"
        assert DecodeLogicFlavor.WRITE.cpuif_select == "cpuif_wr_sel"
