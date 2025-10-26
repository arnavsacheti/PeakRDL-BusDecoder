from collections.abc import Callable

from systemrdl.node import AddrmapNode

from peakrdl_busdecoder.utils import get_indexed_path


class TestGetIndexedPath:
    """Test get_indexed_path function."""

    def test_simple_path(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Test simple path without arrays."""
        rdl_source = """
        addrmap my_addrmap {
            reg {
                field {} data;
            } my_reg;
        };
        """
        top = compile_rdl(rdl_source, top="my_addrmap")
        # Get the register node by iterating through children
        reg_node = None
        for child in top.children():
            if child.inst_name == "my_reg":
                reg_node = child
                break

        assert reg_node is not None
        path = get_indexed_path(top, reg_node)
        assert path == "my_reg"

    def test_nested_path(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Test nested path without arrays."""
        rdl_source = """
        addrmap inner_map {
            reg {
                field {} data;
            } my_reg;
        };
        
        addrmap my_addrmap {
            inner_map inner;
        };
        """
        top = compile_rdl(rdl_source, top="my_addrmap")
        # Navigate to the nested register
        inner_node = None
        for child in top.children():
            if child.inst_name == "inner":
                inner_node = child
                break
        assert inner_node is not None

        reg_node = None
        for child in inner_node.children():
            if child.inst_name == "my_reg":
                reg_node = child
                break
        assert reg_node is not None

        path = get_indexed_path(top, reg_node)
        assert path == "inner.my_reg"

    def test_array_path(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Test path with array indices."""
        rdl_source = """
        addrmap my_addrmap {
            reg {
                field {} data;
            } my_reg[4];
        };
        """
        top = compile_rdl(rdl_source, top="my_addrmap")
        reg_node = None
        for child in top.children():
            if child.inst_name == "my_reg":
                reg_node = child
                break
        assert reg_node is not None

        path = get_indexed_path(top, reg_node)
        assert path == "my_reg[i0]"

    def test_multidimensional_array_path(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Test path with multidimensional arrays."""
        rdl_source = """
        addrmap my_addrmap {
            reg {
                field {} data;
            } my_reg[2][3];
        };
        """
        top = compile_rdl(rdl_source, top="my_addrmap")
        reg_node = None
        for child in top.children():
            if child.inst_name == "my_reg":
                reg_node = child
                break
        assert reg_node is not None

        path = get_indexed_path(top, reg_node)
        assert path == "my_reg[i0][i1]"

    def test_nested_array_path(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Test path with nested arrays."""
        rdl_source = """
        addrmap inner_map {
            reg {
                field {} data;
            } my_reg[2];
        };
        
        addrmap my_addrmap {
            inner_map inner[3];
        };
        """
        top = compile_rdl(rdl_source, top="my_addrmap")
        # Navigate to the nested register
        inner_node = None
        for child in top.children():
            if child.inst_name == "inner":
                inner_node = child
                break
        assert inner_node is not None

        reg_node = None
        for child in inner_node.children():
            if child.inst_name == "my_reg":
                reg_node = child
                break
        assert reg_node is not None

        path = get_indexed_path(top, reg_node)
        assert path == "inner[i0].my_reg[i1]"

    def test_custom_indexer(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Test path with custom indexer name."""
        rdl_source = """
        addrmap my_addrmap {
            reg {
                field {} data;
            } my_reg[4];
        };
        """
        top = compile_rdl(rdl_source, top="my_addrmap")
        reg_node = None
        for child in top.children():
            if child.inst_name == "my_reg":
                reg_node = child
                break
        assert reg_node is not None

        path = get_indexed_path(top, reg_node, indexer="idx")
        assert path == "my_reg[idx0]"

    def test_skip_kw_filter(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """Test path with keyword filtering skipped."""
        rdl_source = """
        addrmap my_addrmap {
            reg {
                field {} data;
            } always_reg;
        };
        """
        top = compile_rdl(rdl_source, top="my_addrmap")
        reg_node = None
        for child in top.children():
            if child.inst_name == "always_reg":
                reg_node = child
                break
        assert reg_node is not None

        # With keyword filter (default) - SystemRDL identifiers can use keywords but SV can't
        path = get_indexed_path(top, reg_node)
        # The path should contain always_reg
        assert "always_reg" in path

        # Without keyword filter
        path = get_indexed_path(top, reg_node, skip_kw_filter=True)
        assert path == "always_reg"
