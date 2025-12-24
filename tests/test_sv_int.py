from peakrdl_busdecoder.sv_int import SVInt


def test_string_formatting() -> None:
    """SV literals should format width and value correctly."""
    assert str(SVInt(0x1A, 8)) == "8'h1a"
    assert str(SVInt(0xDEADBEEF)) == "'hdeadbeef"
    assert str(SVInt(0x1FFFFFFFF)) == "33'h1ffffffff"


def test_arithmetic_width_propagation() -> None:
    """Addition and subtraction should preserve sizing rules."""
    small = SVInt(3, 4)
    large = SVInt(5, 6)

    summed = small + large
    assert summed.value == 8
    assert summed.width == 6  # max width wins when both are sized

    diff = large - small
    assert diff.value == 2
    assert diff.width == 6

    unsized_left = SVInt(1)
    mixed = unsized_left + small
    assert mixed.width is None  # any unsized operand yields unsized result


def test_length_and_to_bytes() -> None:
    """Length and byte conversion should reflect the represented value."""
    sized = SVInt(0x3, 12)
    assert len(sized) == 12

    value = SVInt(0x1234)
    assert len(value) == 13
    assert value.to_bytes("little") == b"\x34\x12"
    assert value.to_bytes("big") == b"\x12\x34"


def test_equality_and_hash() -> None:
    """Equality compares both value and width."""
    a = SVInt(7, 4)
    b = SVInt(7, 4)
    c = SVInt(7)

    assert a == b
    assert hash(a) == hash(b)
    assert a != c
    assert (a == 7) is False  # Non-SVInt comparisons fall back to NotImplemented
