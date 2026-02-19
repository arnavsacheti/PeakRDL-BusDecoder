"""Hypothesis-based transaction generation for cocotb bus decoder tests.

This module bridges Hypothesis and cocotb by generating random bus transactions
at the pytest runner level, which are then passed to a single cocotb simulation
via the test configuration. This avoids the overhead of running a separate
simulation per Hypothesis example while still benefiting from Hypothesis's
data generation heuristics.
"""

from __future__ import annotations

from typing import Any

from hypothesis import strategies as st


def _flat_index(index: list[int], dimensions: list[int]) -> int:
    """Convert a multi-dimensional index to a flat offset.

    For dimensions [d0, d1, d2] and index [i0, i1, i2]:
        flat = i0 * d1 * d2 + i1 * d2 + i2
    """
    flat = 0
    multiplier = 1
    for d, i in zip(reversed(dimensions), reversed(index)):
        flat += i * multiplier
        multiplier *= d
    return flat


def generate_random_transactions(
    config: dict[str, Any],
    data: st.DataObject,
    n_per_index: int = 5,
) -> list[dict[str, Any]]:
    """Generate random valid bus transactions using Hypothesis strategies.

    For each master/index pair, generates ``n_per_index`` random word-aligned
    addresses within the master's address range.

    Parameters
    ----------
    config:
        The cocotb test configuration dictionary (as built by prepare_cpuif_case).
    data:
        A Hypothesis ``st.data()`` draw source.
    n_per_index:
        Number of random transactions to generate per master/index pair.

    Returns
    -------
    list[dict]
        Transaction dicts compatible with the existing cocotb test format.
    """
    byte_width = config["byte_width"]
    extra: list[dict[str, Any]] = []

    for master in config["masters"]:
        for idx in master["indices"]:
            dims = master["dimensions"]
            flat_idx = _flat_index(idx, dims) if dims else 0
            base = master["inst_address"] + flat_idx * master["inst_size"]
            child_size = master["child_size"]

            # Maximum word-aligned offset within the child's address space.
            max_word_offset = (child_size - byte_width) // byte_width
            if max_word_offset < 0:
                continue

            for j in range(n_per_index):
                word_idx = data.draw(
                    st.integers(min_value=0, max_value=max_word_offset),
                    label=f"offset_{master['inst_name']}_{idx}_{j}",
                )
                addr = base + word_idx * byte_width

                extra.append(
                    {
                        "address": addr,
                        "master": master["inst_name"],
                        "index": list(idx),
                        "label": f"hyp_{master['inst_name']}_{idx}_{j}_0x{addr:x}",
                    }
                )

    return extra


def generate_random_invalid_addresses(
    config: dict[str, Any],
    data: st.DataObject,
    n: int = 3,
) -> list[int]:
    """Generate random addresses that do NOT map to any master.

    Parameters
    ----------
    config:
        The cocotb test configuration dictionary.
    data:
        A Hypothesis ``st.data()`` draw source.
    n:
        Number of invalid addresses to attempt to generate.

    Returns
    -------
    list[int]
        Invalid addresses (may be fewer than ``n`` if the address space is
        mostly covered by masters).
    """
    addr_width = config["address_width"]
    byte_width = config["byte_width"]
    max_addr = 1 << addr_width

    # Build occupied ranges
    occupied: list[tuple[int, int]] = []
    for master in config["masters"]:
        base = master["inst_address"]
        size = master["inst_size"]
        n_elems = 1
        for dim in master.get("dimensions", []):
            n_elems *= dim
        span = size * n_elems
        occupied.append((base, base + span))
    occupied.sort()

    # Collect gaps
    gaps: list[tuple[int, int]] = []
    cursor = 0
    for start, end in occupied:
        if cursor < start:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < max_addr:
        gaps.append((cursor, max_addr))

    if not gaps:
        return []

    invalid: list[int] = []
    for i in range(n):
        # Pick a random gap, then a random word-aligned address within it
        gap_idx = data.draw(
            st.integers(min_value=0, max_value=len(gaps) - 1),
            label=f"gap_{i}",
        )
        gap_start, gap_end = gaps[gap_idx]
        # Word-align the range
        aligned_start = ((gap_start + byte_width - 1) // byte_width) * byte_width
        aligned_end = (gap_end // byte_width) * byte_width
        if aligned_start >= aligned_end:
            continue
        addr = data.draw(
            st.integers(
                min_value=aligned_start // byte_width,
                max_value=(aligned_end - byte_width) // byte_width,
            ),
            label=f"invalid_addr_{i}",
        ) * byte_width
        invalid.append(addr)

    return invalid
