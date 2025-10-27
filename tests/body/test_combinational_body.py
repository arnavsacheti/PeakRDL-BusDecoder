from peakrdl_busdecoder.body import CombinationalBody, IfBody


class TestCombinationalBody:
    """Test the CombinationalBody class."""

    def test_simple_combinational_block(self) -> None:
        """Test simple combinational block."""
        body = CombinationalBody()
        body += "assign1 = value1;"
        body += "assign2 = value2;"

        result = str(body)
        assert "always_comb" in result
        assert "begin" in result
        assert "assign1 = value1;" in result
        assert "assign2 = value2;" in result
        assert "end" in result

    def test_empty_combinational_block(self) -> None:
        """Test empty combinational block."""
        body = CombinationalBody()
        result = str(body)
        assert "always_comb" in result
        assert "begin" in result
        assert "end" in result

    def test_combinational_with_if_statement(self) -> None:
        """Test combinational block with if statement."""
        cb = CombinationalBody()
        ifb = IfBody()
        with ifb.cm("condition") as b:
            b += "assignment = value;"
        cb += ifb

        result = str(cb)
        assert "always_comb" in result
        assert "if (condition)" in result
        assert "assignment = value;" in result
