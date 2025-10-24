"""Tests for utility functions."""

from __future__ import annotations

import pytest
from systemrdl import RDLCompiler
from systemrdl.node import AddrmapNode

from peakrdl_busdecoder.utils import clog2, get_indexed_path, is_pow2, roundup_pow2


class TestMathUtils:
    """Test mathematical utility functions."""

    def test_clog2_basic(self):
        """Test clog2 function with basic values."""
        assert clog2(1) == 0
        assert clog2(2) == 1
        assert clog2(3) == 2
        assert clog2(4) == 2
        assert clog2(5) == 3
        assert clog2(8) == 3
        assert clog2(9) == 4
        assert clog2(16) == 4
        assert clog2(17) == 5
        assert clog2(32) == 5
        assert clog2(33) == 6
        assert clog2(64) == 6
        assert clog2(128) == 7
        assert clog2(256) == 8
        assert clog2(1024) == 10

    def test_is_pow2_true_cases(self):
        """Test is_pow2 returns True for powers of 2."""
        assert is_pow2(1) is True
        assert is_pow2(2) is True
        assert is_pow2(4) is True
        assert is_pow2(8) is True
        assert is_pow2(16) is True
        assert is_pow2(32) is True
        assert is_pow2(64) is True
        assert is_pow2(128) is True
        assert is_pow2(256) is True
        assert is_pow2(512) is True
        assert is_pow2(1024) is True

    def test_is_pow2_false_cases(self):
        """Test is_pow2 returns False for non-powers of 2."""
        assert is_pow2(0) is False
        assert is_pow2(3) is False
        assert is_pow2(5) is False
        assert is_pow2(6) is False
        assert is_pow2(7) is False
        assert is_pow2(9) is False
        assert is_pow2(10) is False
        assert is_pow2(15) is False
        assert is_pow2(17) is False
        assert is_pow2(100) is False
        assert is_pow2(255) is False
        assert is_pow2(1000) is False

    def test_roundup_pow2_already_power_of_2(self):
        """Test roundup_pow2 with values that are already powers of 2."""
        assert roundup_pow2(1) == 1
        assert roundup_pow2(2) == 2
        assert roundup_pow2(4) == 4
        assert roundup_pow2(8) == 8
        assert roundup_pow2(16) == 16
        assert roundup_pow2(32) == 32
        assert roundup_pow2(64) == 64
        assert roundup_pow2(128) == 128
        assert roundup_pow2(256) == 256

    def test_roundup_pow2_non_power_of_2(self):
        """Test roundup_pow2 with values that are not powers of 2."""
        assert roundup_pow2(3) == 4
        assert roundup_pow2(5) == 8
        assert roundup_pow2(6) == 8
        assert roundup_pow2(7) == 8
        assert roundup_pow2(9) == 16
        assert roundup_pow2(15) == 16
        assert roundup_pow2(17) == 32
        assert roundup_pow2(31) == 32
        assert roundup_pow2(33) == 64
        assert roundup_pow2(100) == 128
        assert roundup_pow2(255) == 256
        assert roundup_pow2(257) == 512


class TestGetIndexedPath:
    """Test get_indexed_path function."""

    def test_simple_path(self, compile_rdl):
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

    def test_nested_path(self, compile_rdl):
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

    def test_array_path(self, compile_rdl):
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

    def test_multidimensional_array_path(self, compile_rdl):
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

    def test_nested_array_path(self, compile_rdl):
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

    def test_custom_indexer(self, compile_rdl):
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

    def test_skip_kw_filter(self, compile_rdl):
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
