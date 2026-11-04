"""Shared helpers for cocotb smoke tests."""

from __future__ import annotations

import json
import os
import random
from collections.abc import Iterable
from typing import Any

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from tests.cocotb_lib.handle_utils import resolve_handle


def load_config() -> dict[str, Any]:
    """Read the JSON payload describing the generated register topology."""
    payload = os.environ.get("RDL_TEST_CONFIG")
    if payload is None:
        raise RuntimeError("RDL_TEST_CONFIG environment variable was not provided")
    return json.loads(payload)


def resolve(handle, indices: Iterable[int]):
    """Index into hierarchical cocotb handles."""
    return resolve_handle(handle, indices)


def set_value(handle, indices: Iterable[int], value: int) -> None:
    resolve(handle, indices).value = value


def get_int(handle, indices: Iterable[int]) -> int:
    return int(resolve(handle, indices).value)


def all_index_pairs(table: dict[str, dict[str, Any]]):
    for name, entry in table.items():
        for idx in entry["indices"]:
            yield name, idx


def find_invalid_address(config: dict[str, Any]) -> int | None:
    """Return an address outside any master/array span, or None if fully covered."""
    addr_width = config["address_width"]
    max_addr = 1 << addr_width
    ranges: list[tuple[int, int]] = []

    for master in config["masters"]:
        inst_address = master["inst_address"]
        inst_size = master["inst_size"]
        n_elems = 1
        if master.get("is_array"):
            for dim in master.get("dimensions", []):
                n_elems *= dim
        span = inst_size * n_elems
        ranges.append((inst_address, inst_address + span))

    ranges.sort()

    cursor = 0
    for start, end in ranges:
        if cursor < start:
            return cursor
        cursor = max(cursor, end)

    if cursor < max_addr:
        return cursor
    return None


async def start_clock(clk_handle, period_ns: int = 2) -> None:
    """Start a simple clock if handle is present."""
    if clk_handle is None:
        return
    clk_handle.value = 0
    cocotb.start_soon(Clock(clk_handle, period_ns, unit="ns").start())
    await RisingEdge(clk_handle)


async def apb_setup(slave, addr: int, write: bool, data: int, *, strobe_mask: int | None = None) -> None:
    """APB setup phase helper."""
    if hasattr(slave, "PPROT"):
        slave.PPROT.value = 0
    if hasattr(slave, "PSTRB"):
        if strobe_mask is None:
            strobe_mask = (1 << len(slave.PSTRB)) - 1
        slave.PSTRB.value = strobe_mask
    slave.PADDR.value = addr
    slave.PWDATA.value = data
    slave.PWRITE.value = 1 if write else 0
    slave.PSEL.value = 1
    slave.PENABLE.value = 0
    await Timer(1, unit="ns")


async def apb_access(slave) -> None:
    """APB access phase helper."""
    slave.PENABLE.value = 1
    await Timer(1, unit="ns")


async def advance(clk_handle) -> None:
    """Advance one simulation step: a rising edge if clocked, otherwise a 1ns tick."""
    if clk_handle is not None:
        await RisingEdge(clk_handle)
    else:
        await Timer(1, unit="ns")


def make_rng(env_var: str = "RDL_TEST_SEED", default: int = 0xC0C07B) -> random.Random:
    """Deterministic RNG seeded via environment for reproducible stress runs."""
    seed_raw = os.environ.get(env_var)
    if seed_raw is None:
        seed = default
    else:
        seed = int(seed_raw, 0)
    return random.Random(seed)


def shuffle_transactions(transactions: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    """Return a freshly shuffled copy of ``transactions`` using ``rng``."""
    shuffled = list(transactions)
    rng.shuffle(shuffled)
    return shuffled


def pick_distinct_pairs(
    transactions: list[dict[str, Any]], count: int = 2
) -> list[dict[str, Any]]:
    """Return up to ``count`` transactions that target distinct (master, index) pairs.

    Stress / back-to-back tests need traffic that actually switches masters, so
    we scan the sampled transaction list and keep the first transaction for each
    unique (master, index) tuple.
    """
    seen: set[tuple[str, tuple[int, ...]]] = set()
    picked: list[dict[str, Any]] = []
    for txn in transactions:
        key = (txn["master"], tuple(txn["index"]))
        if key in seen:
            continue
        seen.add(key)
        picked.append(txn)
        if len(picked) >= count:
            break
    return picked
