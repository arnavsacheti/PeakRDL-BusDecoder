from peakrdl_busdecoder.body import IfBody


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
