"""Property-based tests using Hypothesis."""

import re

from hypothesis import given
from hypothesis import strategies as st

from peakrdl_busdecoder.identifier_filter import SV_KEYWORDS, kw_filter
from peakrdl_busdecoder.sv_int import SVInt
from peakrdl_busdecoder.utils import clog2, is_pow2, roundup_pow2


# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------
# Positive integers in the range that these utility functions operate on.
positive_ints = st.integers(min_value=1, max_value=2**32)

# SVInt values: always non-negative (represents hardware addresses/sizes).
sv_values = st.integers(min_value=0, max_value=2**32)
# SVInt widths: either explicit (>= 1) or None (unsized).
sv_widths = st.one_of(st.none(), st.integers(min_value=1, max_value=128))


# ===========================================================================
# Property 1: Math utility interrelationships (clog2, is_pow2, roundup_pow2)
# ===========================================================================


class TestClog2Properties:
    """Properties of the ceiling-log2 function."""

    @given(n=positive_ints)
    def test_clog2_upper_bound(self, n: int) -> None:
        """2**clog2(n) is always >= n (sufficient bits to represent n values)."""
        assert 2 ** clog2(n) >= n

    @given(n=st.integers(min_value=2, max_value=2**32))
    def test_clog2_tight_bound(self, n: int) -> None:
        """2**(clog2(n)-1) < n, i.e. clog2(n) is the *minimum* sufficient width."""
        assert 2 ** (clog2(n) - 1) < n

    @given(n=st.integers(min_value=1, max_value=2**32 - 1))
    def test_clog2_monotonic(self, n: int) -> None:
        """clog2 is monotonically non-decreasing."""
        assert clog2(n) <= clog2(n + 1)


class TestMathUtilInterrelationships:
    """Cross-function properties linking clog2, is_pow2, and roundup_pow2."""

    @given(x=positive_ints)
    def test_roundup_pow2_is_power_of_2(self, x: int) -> None:
        """roundup_pow2 always returns a power of 2."""
        assert is_pow2(roundup_pow2(x))

    @given(x=positive_ints)
    def test_roundup_pow2_is_upper_bound(self, x: int) -> None:
        """roundup_pow2(x) >= x."""
        assert roundup_pow2(x) >= x

    @given(x=positive_ints)
    def test_roundup_pow2_is_tight(self, x: int) -> None:
        """roundup_pow2(x) is the *smallest* power of 2 >= x."""
        r = roundup_pow2(x)
        # The next smaller power of 2 must be strictly less than x
        # (unless x is itself a power of 2, in which case r == x).
        if r > 1:
            assert (r // 2) < x

    @given(x=positive_ints)
    def test_roundup_pow2_fixpoint_iff_is_pow2(self, x: int) -> None:
        """roundup_pow2(x) == x if and only if x is already a power of 2."""
        assert (roundup_pow2(x) == x) == is_pow2(x)

    @given(n=st.integers(min_value=0, max_value=30))
    def test_clog2_of_power_of_2(self, n: int) -> None:
        """clog2(2**n) == n for all non-negative n."""
        assert clog2(2**n) == n


# ===========================================================================
# Property 2: SVInt arithmetic and string formatting
# ===========================================================================


class TestSVIntArithmetic:
    """Properties of SVInt addition and subtraction."""

    @given(a_val=sv_values, b_val=sv_values, a_w=sv_widths, b_w=sv_widths)
    def test_addition_preserves_value(
        self, a_val: int, b_val: int, a_w: int | None, b_w: int | None
    ) -> None:
        """(a + b).value == a.value + b.value."""
        result = SVInt(a_val, a_w) + SVInt(b_val, b_w)
        assert result.value == a_val + b_val

    @given(a_val=sv_values, b_val=sv_values, a_w=sv_widths, b_w=sv_widths)
    def test_subtraction_preserves_value(
        self, a_val: int, b_val: int, a_w: int | None, b_w: int | None
    ) -> None:
        """(a - b).value == a.value - b.value."""
        result = SVInt(a_val, a_w) - SVInt(b_val, b_w)
        assert result.value == a_val - b_val

    @given(
        a_val=sv_values,
        b_val=sv_values,
        a_w=st.integers(min_value=1, max_value=128),
        b_w=st.integers(min_value=1, max_value=128),
    )
    def test_addition_width_both_sized(self, a_val: int, b_val: int, a_w: int, b_w: int) -> None:
        """When both operands are sized, result width is max(a.width, b.width)."""
        result = SVInt(a_val, a_w) + SVInt(b_val, b_w)
        assert result.width == max(a_w, b_w)

    @given(a_val=sv_values, b_val=sv_values, w=st.integers(min_value=1, max_value=128))
    def test_addition_width_any_unsized_yields_unsized(self, a_val: int, b_val: int, w: int) -> None:
        """When either operand is unsized, result is unsized."""
        assert (SVInt(a_val, None) + SVInt(b_val, w)).width is None
        assert (SVInt(a_val, w) + SVInt(b_val, None)).width is None
        assert (SVInt(a_val, None) + SVInt(b_val, None)).width is None

    @given(a_val=sv_values, b_val=sv_values, a_w=sv_widths, b_w=sv_widths)
    def test_addition_commutative(self, a_val: int, b_val: int, a_w: int | None, b_w: int | None) -> None:
        """SVInt addition is commutative (value and width)."""
        assert SVInt(a_val, a_w) + SVInt(b_val, b_w) == SVInt(b_val, b_w) + SVInt(a_val, a_w)


class TestSVIntFormatting:
    """Properties of SVInt string formatting."""

    @given(val=sv_values, width=st.integers(min_value=1, max_value=128))
    def test_sized_format_roundtrip(self, val: int, width: int) -> None:
        """Parsing the hex value from a sized SVInt string recovers the original value."""
        s = str(SVInt(val, width))
        m = re.fullmatch(r"(\d+)'h([0-9a-f]+)", s)
        assert m is not None, f"Unexpected format: {s!r}"
        assert int(m.group(1)) == width
        assert int(m.group(2), 16) == val

    @given(val=st.integers(min_value=0, max_value=2**32))
    def test_unsized_format_roundtrip(self, val: int) -> None:
        """Parsing the hex value from an unsized SVInt string recovers the original value."""
        s = str(SVInt(val))
        # Unsized: 'hXX  or  auto-sized: NN'hXX (when > 32 bits)
        m = re.fullmatch(r"(?:(\d+))?'h([0-9a-f]+)", s)
        assert m is not None, f"Unexpected format: {s!r}"
        assert int(m.group(2), 16) == val


class TestSVIntEqualityAndHash:
    """Properties of SVInt equality and hashing."""

    @given(val=sv_values, width=sv_widths)
    def test_equality_reflexive(self, val: int, width: int | None) -> None:
        """An SVInt is equal to an identical copy of itself."""
        assert SVInt(val, width) == SVInt(val, width)

    @given(val=sv_values, width=sv_widths)
    def test_equal_implies_same_hash(self, val: int, width: int | None) -> None:
        """Equal SVInts have the same hash (required for use in dicts/sets)."""
        a = SVInt(val, width)
        b = SVInt(val, width)
        assert hash(a) == hash(b)

    @given(val=sv_values, w1=st.integers(min_value=1, max_value=128))
    def test_different_width_means_not_equal(self, val: int, w1: int) -> None:
        """SVInts with different widths (sized vs unsized) are not equal."""
        assert SVInt(val, w1) != SVInt(val, None)


# ===========================================================================
# Property 3: kw_filter idempotence and safety
# ===========================================================================


# Strategy: generate strings that look like identifiers (word characters only),
# including strings drawn directly from SV_KEYWORDS for targeted coverage.
identifier_strategy = st.one_of(
    st.sampled_from(sorted(SV_KEYWORDS)),
    st.from_regex(r"[a-z_]\w{0,19}", fullmatch=True),
)


class TestKwFilterProperties:
    """Properties of the SystemVerilog keyword filter."""

    @given(s=identifier_strategy)
    def test_idempotent(self, s: str) -> None:
        """Applying kw_filter twice yields the same result as once."""
        assert kw_filter(kw_filter(s)) == kw_filter(s)

    @given(s=identifier_strategy)
    def test_result_not_a_keyword(self, s: str) -> None:
        """The result of kw_filter is never a SystemVerilog keyword."""
        assert kw_filter(s) not in SV_KEYWORDS

    @given(s=identifier_strategy)
    def test_non_keywords_unchanged(self, s: str) -> None:
        """Non-keyword identifiers pass through kw_filter unchanged."""
        if s not in SV_KEYWORDS:
            assert kw_filter(s) == s

    @given(s=st.sampled_from(sorted(SV_KEYWORDS)))
    def test_keywords_get_underscore_suffix(self, s: str) -> None:
        """Every SV keyword gets an underscore suffix."""
        assert kw_filter(s) == s + "_"
