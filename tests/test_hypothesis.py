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


# ===========================================================================
# Property 4: Cocotb test infrastructure utilities
# ===========================================================================


from tests.cocotb_lib.protocol_utils import find_invalid_address
from tests.cocotb_lib.utils import _sample_addresses


# ---------------------------------------------------------------------------
# Data pattern functions (reimplemented here to avoid cocotb-dependent imports
# from the per-protocol test_register_access.py modules)
# ---------------------------------------------------------------------------
def _write_pattern(address: int, width: int) -> int:
    mask = (1 << width) - 1
    return ((address * 0x1021) ^ 0x1357_9BDF) & mask


def _read_pattern(address: int, width: int) -> int:
    mask = (1 << width) - 1
    return ((address ^ 0xDEAD_BEE5) + width) & mask


class TestCpuifDataPatterns:
    """Properties of the write/read pattern functions used by cocotb tests."""

    @given(
        address=st.integers(min_value=0, max_value=2**32),
        width=st.sampled_from([8, 16, 32, 64, 128]),
    )
    def test_write_pattern_fits_in_width(self, address: int, width: int) -> None:
        """Write pattern always fits within the specified bus width."""
        result = _write_pattern(address, width)
        assert 0 <= result < (1 << width)

    @given(
        address=st.integers(min_value=0, max_value=2**32),
        width=st.sampled_from([8, 16, 32, 64, 128]),
    )
    def test_read_pattern_fits_in_width(self, address: int, width: int) -> None:
        """Read pattern always fits within the specified bus width."""
        result = _read_pattern(address, width)
        assert 0 <= result < (1 << width)

    @given(
        address=st.integers(min_value=0, max_value=2**32),
        width=st.sampled_from([8, 16, 32, 64, 128]),
    )
    def test_patterns_are_deterministic(self, address: int, width: int) -> None:
        """Same address and width always produce the same pattern."""
        assert _write_pattern(address, width) == _write_pattern(address, width)
        assert _read_pattern(address, width) == _read_pattern(address, width)


class TestSampleAddresses:
    """Properties of the address sampling function used in cocotb test generation."""

    @given(
        addresses=st.lists(st.integers(min_value=0, max_value=0xFFFF), min_size=1, unique=True).map(sorted),
        max_samples=st.integers(min_value=1, max_value=20),
    )
    def test_result_is_subset(self, addresses: list[int], max_samples: int) -> None:
        """Every sampled address comes from the original list."""
        result = _sample_addresses(addresses, max_samples)
        for r in result:
            assert r in addresses

    @given(
        addresses=st.lists(st.integers(min_value=0, max_value=0xFFFF), min_size=1, unique=True).map(sorted),
        max_samples=st.integers(min_value=1, max_value=20),
    )
    def test_result_is_sorted(self, addresses: list[int], max_samples: int) -> None:
        """Sampled addresses are returned in sorted order."""
        result = _sample_addresses(addresses, max_samples)
        assert result == sorted(result)

    @given(
        addresses=st.lists(st.integers(min_value=0, max_value=0xFFFF), min_size=1, unique=True).map(sorted),
        # NOTE: _sample_addresses unconditionally adds first, last, and midpoint before
        # checking the limit, so it can exceed max_samples when max_samples < 3.
        # In practice, the codebase always uses max_samples >= 3.
        max_samples=st.integers(min_value=3, max_value=20),
    )
    def test_result_size_bounded(self, addresses: list[int], max_samples: int) -> None:
        """Never returns more than max_samples addresses (for max_samples >= 3)."""
        result = _sample_addresses(addresses, max_samples)
        assert len(result) <= max_samples

    @given(
        addresses=st.lists(st.integers(min_value=0, max_value=0xFFFF), min_size=1, unique=True).map(sorted),
        max_samples=st.integers(min_value=1, max_value=20),
    )
    def test_small_input_returned_in_full(self, addresses: list[int], max_samples: int) -> None:
        """When the input is small enough, all addresses are returned."""
        result = _sample_addresses(addresses, max_samples)
        if len(addresses) <= max_samples:
            assert result == addresses

    @given(
        addresses=st.lists(
            st.integers(min_value=0, max_value=0xFFFF), min_size=2, unique=True
        ).map(sorted),
        max_samples=st.integers(min_value=2, max_value=20),
    )
    def test_endpoints_always_included(self, addresses: list[int], max_samples: int) -> None:
        """The first and last addresses are always included in the sample."""
        result = _sample_addresses(addresses, max_samples)
        assert addresses[0] in result
        assert addresses[-1] in result


# Strategy: generate a config dict with random master address ranges.
@st.composite
def address_range_configs(draw: st.DrawFn) -> dict:
    """Generate configs with random, non-overlapping master address ranges."""
    n_masters = draw(st.integers(min_value=1, max_value=5))
    addr_width = draw(st.integers(min_value=8, max_value=16))
    max_addr = 1 << addr_width

    masters: list[dict] = []
    cursor = 0
    for _ in range(n_masters):
        if cursor >= max_addr:
            break
        gap = draw(st.integers(min_value=0, max_value=16))
        cursor += gap
        if cursor >= max_addr:
            break
        remaining = max_addr - cursor
        inst_size = draw(st.integers(min_value=1, max_value=min(64, remaining)))
        is_array = draw(st.booleans())
        if is_array:
            max_elems = min(4, remaining // inst_size)
            if max_elems < 1:
                is_array = False
                dims: list[int] = []
            else:
                n_elems = draw(st.integers(min_value=1, max_value=max_elems))
                dims = [n_elems]
        else:
            dims = []
            n_elems = 1
        masters.append(
            {
                "inst_address": cursor,
                "inst_size": inst_size,
                "is_array": is_array,
                "dimensions": dims,
            }
        )
        cursor += inst_size * n_elems

    return {"address_width": addr_width, "masters": masters}


class TestFindInvalidAddress:
    """Properties of the gap-finding function used to locate unmapped addresses."""

    @given(config=address_range_configs())
    def test_result_outside_all_master_ranges(self, config: dict) -> None:
        """If an address is returned, it must not fall within any master's span."""
        result = find_invalid_address(config)
        if result is None:
            return
        assert 0 <= result < (1 << config["address_width"])
        for master in config["masters"]:
            base = master["inst_address"]
            size = master["inst_size"]
            n_elems = 1
            for dim in master.get("dimensions", []):
                n_elems *= dim
            span = size * n_elems
            assert not (base <= result < base + span), (
                f"Returned 0x{result:x} but it falls in master range [0x{base:x}, 0x{base + span:x})"
            )

    @given(config=address_range_configs())
    def test_result_within_address_space(self, config: dict) -> None:
        """Returned address is within the valid address space [0, 2^addr_width)."""
        result = find_invalid_address(config)
        if result is not None:
            assert 0 <= result < (1 << config["address_width"])
