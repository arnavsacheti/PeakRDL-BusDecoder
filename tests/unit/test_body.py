"""Tests for body classes used in code generation."""

from __future__ import annotations

import pytest

from peakrdl_busdecoder.body import (
    Body,
    CombinationalBody,
    ForLoopBody,
    IfBody,
    StructBody,
)


class TestBody:
    """Test the base Body class."""

    def test_empty_body(self):
        """Test empty body returns empty string."""
        body = Body()
        assert str(body) == ""
        assert not body  # Should be falsy when empty

    def test_add_single_line(self):
        """Test adding a single line to body."""
        body = Body()
        body += "line1"
        assert str(body) == "line1"
        assert body  # Should be truthy when not empty

    def test_add_multiple_lines(self):
        """Test adding multiple lines to body."""
        body = Body()
        body += "line1"
        body += "line2"
        body += "line3"
        expected = "line1\nline2\nline3"
        assert str(body) == expected

    def test_add_returns_self(self):
        """Test that add operation returns self for chaining."""
        body = Body()
        body += "line1"
        body += "line2"
        # Chaining works because += returns self
        assert len(body.lines) == 2

    def test_add_nested_body(self):
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


class TestForLoopBody:
    """Test the ForLoopBody class."""

    def test_genvar_for_loop(self):
        """Test genvar-style for loop."""
        body = ForLoopBody("genvar", "i", 4)
        body += "statement1;"
        body += "statement2;"
        
        result = str(body)
        assert "for (genvar i = 0; i < 4; i++)" in result
        assert "statement1;" in result
        assert "statement2;" in result
        assert "end" in result

    def test_int_for_loop(self):
        """Test int-style for loop."""
        body = ForLoopBody("int", "j", 8)
        body += "assignment = value;"
        
        result = str(body)
        assert "for (int j = 0; j < 8; j++)" in result
        assert "assignment = value;" in result
        assert "end" in result

    def test_empty_for_loop(self):
        """Test empty for loop."""
        body = ForLoopBody("genvar", "k", 2)
        result = str(body)
        # Empty for loop should still have structure
        assert "for (genvar k = 0; k < 2; k++)" in result

    def test_nested_for_loops(self):
        """Test nested for loops."""
        outer = ForLoopBody("genvar", "i", 3)
        inner = ForLoopBody("genvar", "j", 2)
        inner += "nested_statement;"
        outer += inner
        
        result = str(outer)
        assert "for (genvar i = 0; i < 3; i++)" in result
        assert "for (genvar j = 0; j < 2; j++)" in result
        assert "nested_statement;" in result


class TestIfBody:
    """Test the IfBody class."""

    def test_simple_if(self):
        """Test simple if statement."""
        body = IfBody()
        with body.cm("condition1") as b:
            b += "statement1;"
        
        result = str(body)
        assert "if (condition1)" in result
        assert "statement1;" in result
        assert "end" in result

    def test_if_else(self):
        """Test if-else statement."""
        body = IfBody()
        with body.cm("condition1") as b:
            b += "if_statement;"
        with body.cm(None) as b:  # None for else
            b += "else_statement;"
        
        result = str(body)
        assert "if (condition1)" in result
        assert "if_statement;" in result
        assert "else" in result
        assert "else_statement;" in result

    def test_if_elif_else(self):
        """Test if-elif-else chain."""
        body = IfBody()
        with body.cm("condition1") as b:
            b += "statement1;"
        with body.cm("condition2") as b:
            b += "statement2;"
        with body.cm(None) as b:  # None for else
            b += "statement3;"
        
        result = str(body)
        assert "if (condition1)" in result
        assert "statement1;" in result
        assert "else if (condition2)" in result
        assert "statement2;" in result
        assert "else" in result
        assert "statement3;" in result

    def test_multiple_elif(self):
        """Test multiple elif statements."""
        body = IfBody()
        with body.cm("cond1") as b:
            b += "stmt1;"
        with body.cm("cond2") as b:
            b += "stmt2;"
        with body.cm("cond3") as b:
            b += "stmt3;"
        
        result = str(body)
        assert "if (cond1)" in result
        assert "else if (cond2)" in result
        assert "else if (cond3)" in result

    def test_empty_if_branches(self):
        """Test if statement with empty branches."""
        body = IfBody()
        with body.cm("condition"):
            pass
        
        result = str(body)
        assert "if (condition)" in result

    def test_nested_if(self):
        """Test nested if statements."""
        outer = IfBody()
        with outer.cm("outer_cond") as outer_body:
            inner = IfBody()
            with inner.cm("inner_cond") as inner_body:
                inner_body += "nested_statement;"
            outer_body += inner
        
        result = str(outer)
        assert "if (outer_cond)" in result
        assert "if (inner_cond)" in result
        assert "nested_statement;" in result


class TestCombinationalBody:
    """Test the CombinationalBody class."""

    def test_simple_combinational_block(self):
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

    def test_empty_combinational_block(self):
        """Test empty combinational block."""
        body = CombinationalBody()
        result = str(body)
        assert "always_comb" in result
        assert "begin" in result
        assert "end" in result

    def test_combinational_with_if_statement(self):
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


class TestStructBody:
    """Test the StructBody class."""

    def test_simple_struct(self):
        """Test simple struct definition."""
        body = StructBody("my_struct_t", packed=True, typedef=True)
        body += "logic [7:0] field1;"
        body += "logic field2;"
        
        result = str(body)
        assert "typedef struct packed" in result
        assert "my_struct_t" in result
        assert "logic [7:0] field1;" in result
        assert "logic field2;" in result

    def test_unpacked_struct(self):
        """Test unpacked struct definition."""
        body = StructBody("unpacked_t", packed=False, typedef=True)
        body += "int field1;"
        
        result = str(body)
        assert "typedef struct" in result
        assert "packed" not in result or "typedef struct {" in result
        assert "unpacked_t" in result

    def test_struct_without_typedef(self):
        """Test struct without typedef."""
        body = StructBody("my_struct", packed=True, typedef=False)
        body += "logic field;"
        
        result = str(body)
        # When typedef=False, packed is not used
        assert "struct {" in result
        assert "typedef" not in result
        assert "my_struct" in result

    def test_empty_struct(self):
        """Test empty struct."""
        body = StructBody("empty_t", packed=True, typedef=True)
        result = str(body)
        assert "typedef struct packed" in result
        assert "empty_t" in result

    def test_nested_struct(self):
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
