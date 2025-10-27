from peakrdl_busdecoder.body import ForLoopBody


class TestForLoopBody:
    """Test the ForLoopBody class."""

    def test_genvar_for_loop(self) -> None:
        """Test genvar-style for loop."""
        body = ForLoopBody("genvar", "i", 4)
        body += "statement1;"
        body += "statement2;"

        result = str(body)
        assert "for (genvar i = 0; i < 4; i++)" in result
        assert "statement1;" in result
        assert "statement2;" in result
        assert "end" in result

    def test_int_for_loop(self) -> None:
        """Test int-style for loop."""
        body = ForLoopBody("int", "j", 8)
        body += "assignment = value;"

        result = str(body)
        assert "for (int j = 0; j < 8; j++)" in result
        assert "assignment = value;" in result
        assert "end" in result

    def test_empty_for_loop(self) -> None:
        """Test empty for loop."""
        body = ForLoopBody("genvar", "k", 2)
        result = str(body)
        # Empty for loop should still have structure
        assert "for (genvar k = 0; k < 2; k++)" in result

    def test_nested_for_loops(self) -> None:
        """Test nested for loops."""
        outer = ForLoopBody("genvar", "i", 3)
        inner = ForLoopBody("genvar", "j", 2)
        inner += "nested_statement;"
        outer += inner

        result = str(outer)
        assert "for (genvar i = 0; i < 3; i++)" in result
        assert "for (genvar j = 0; j < 2; j++)" in result
        assert "nested_statement;" in result
