
from peakrdl_busdecoder.body import Body


class TestBody:
    """Test the base Body class."""

    def test_empty_body(self) -> None:
        """Test empty body returns empty string."""
        body = Body()
        assert str(body) == ""
        assert not body  # Should be falsy when empty

    def test_add_single_line(self) -> None:
        """Test adding a single line to body."""
        body = Body()
        body += "line1"
        assert str(body) == "line1"
        assert body  # Should be truthy when not empty

    def test_add_multiple_lines(self) -> None:
        """Test adding multiple lines to body."""
        body = Body()
        body += "line1"
        body += "line2"
        body += "line3"
        expected = "line1\nline2\nline3"
        assert str(body) == expected

    def test_add_returns_self(self) -> None:
        """Test that add operation returns self for chaining."""
        body = Body()
        body += "line1"
        body += "line2"
        # Chaining works because += returns self
        assert len(body.lines) == 2

    def test_add_nested_body(self) -> None:
        """Test adding another body as a line."""
        outer = Body()
        inner = Body()
        inner += "inner1"
        inner += "inner2"
        outer += "outer1"
        outer += inner
        outer += "outer2"
        expected = "outer1\ninner1\ninner2\nouter2"
        assert str(outer) == expected


