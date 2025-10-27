from peakrdl_busdecoder.body import StructBody


class TestStructBody:
    """Test the StructBody class."""

    def test_simple_struct(self) -> None:
        """Test simple struct definition."""
        body = StructBody("my_struct_t", packed=True, typedef=True)
        body += "logic [7:0] field1;"
        body += "logic field2;"

        result = str(body)
        assert "typedef struct packed" in result
        assert "my_struct_t" in result
        assert "logic [7:0] field1;" in result
        assert "logic field2;" in result

    def test_unpacked_struct(self) -> None:
        """Test unpacked struct definition."""
        body = StructBody("unpacked_t", packed=False, typedef=True)
        body += "int field1;"

        result = str(body)
        assert "typedef struct" in result
        assert "packed" not in result or "typedef struct {" in result
        assert "unpacked_t" in result

    def test_struct_without_typedef(self) -> None:
        """Test struct without typedef."""
        body = StructBody("my_struct", packed=True, typedef=False)
        body += "logic field;"

        result = str(body)
        # When typedef=False, packed is not used
        assert "struct {" in result
        assert "typedef" not in result
        assert "my_struct" in result

    def test_empty_struct(self) -> None:
        """Test empty struct."""
        body = StructBody("empty_t", packed=True, typedef=True)
        result = str(body)
        assert "typedef struct packed" in result
        assert "empty_t" in result

    def test_nested_struct(self) -> None:
        """Test struct with nested struct."""
        outer = StructBody("outer_t", packed=True, typedef=True)
        inner = StructBody("inner_t", packed=True, typedef=True)
        inner += "logic field1;"
        outer += "logic field2;"
        outer += str(inner)  # Include inner struct as a string

        result = str(outer)
        assert "outer_t" in result
        assert "field2;" in result
        # Inner struct should appear in the string
        assert "inner_t" in result
