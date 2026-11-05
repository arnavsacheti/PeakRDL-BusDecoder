"""APB4 randomized readback against autonomous downstream RTL RAMs."""

from __future__ import annotations

from typing import Any

import cocotb
from cocotb.triggers import Timer

from tests.cocotb.apb4.smoke.test_register_access import (
    _Apb4SlaveShim,
    _idle_slave,
    _write_pattern,
)
from tests.cocotb_lib.protocol_utils import (
    apb_access,
    apb_setup,
    load_config,
    make_rng,
    shuffle_transactions,
)


class _RamDriver:
    """Own only the upstream bus; the RTL peripherals own all child responses."""

    def __init__(self, dut) -> None:
        self.dut = dut
        self.slave = _Apb4SlaveShim(dut)
        self.writes = 0
        self.reads = 0

    async def edge(self) -> None:
        self.dut.clk.value = 1
        await Timer(1, unit="ns")
        self.dut.clk.value = 0
        await Timer(1, unit="ns")

    def check_counts(self, context: str) -> None:
        for name, expected in (
            ("completions", self.writes + self.reads),
            ("writes", self.writes),
            ("reads", self.reads),
        ):
            actual = int(getattr(self.dut, f"child_{name}").value)
            assert actual == expected, f"{context}: child {name}={actual}, expected={expected}"

    async def transfer(
        self, address: int, *, write: bool = False, data: int = 0,
        strobe: int | None = None, expected: int = 0, error: bool = False,
    ) -> None:
        context = f"{'write' if write else 'read'} at {address:#x}"
        # Shared SETUP helper also guarantees that reads drive PSTRB=0.
        await apb_setup(self.slave, address, write, data, strobe_mask=strobe)
        await self.edge()
        self.check_counts(f"{context} SETUP has no side effect")
        await apb_access(self.slave)
        for _ in range(4):
            if int(self.slave.PREADY.value):
                assert int(self.slave.PSLVERR.value) == error, f"{context}: response error"
                if not write:
                    actual = int(self.slave.PRDATA.value)
                    wanted = 0 if error else expected
                    assert actual == wanted, (
                        f"{context}: autonomous RAM readback={actual:#x}, expected={wanted:#x}"
                    )
                if not error:
                    if write:
                        self.writes += 1
                    else:
                        self.reads += 1
                await self.edge()
                self.check_counts(f"{context} accepted exactly once")
                break
            assert int(self.slave.PSLVERR.value) == 0, f"{context}: premature error"
            await self.edge()
            self.check_counts(f"{context} wait has no side effect")
        else:
            raise AssertionError(f"{context}: RAM response timed out")
        self.slave.PSEL.value = 0
        self.slave.PENABLE.value = 0
        self.slave.PWRITE.value = 0
        self.slave.PSTRB.value = 0
        await Timer(1, unit="ns")
        await self.edge()
        self.check_counts(f"{context} idle does not replay")


def _merge_bytes(previous: int, data: int, strobe: int, byte_width: int) -> int:
    """Independent request-side ledger, never based on observed child payloads."""
    mask = sum(0xFF << (lane * 8) for lane in range(byte_width) if strobe & (1 << lane))
    return (previous & ~mask) | (data & mask)


@cocotb.test()
async def test_apb4_random_traffic(dut) -> None:
    """Retain sampled addresses across children, stalls and partial overwrites."""
    config = load_config()
    assert config["transactions"], "The stress fixture must contain real transactions"
    driver = _RamDriver(dut)
    dut.clk.value = 0
    dut.rst.value = 1
    _idle_slave(driver.slave)
    await Timer(1, unit="ns")
    await driver.edge()
    await driver.edge()
    dut.rst.value = 0
    await Timer(1, unit="ns")
    driver.check_counts("reset")

    rng = make_rng()
    addr_mask = (1 << config["address_width"]) - 1
    byte_width = config["byte_width"]
    full_strobe = (1 << byte_width) - 1
    shadow: dict[tuple[str, tuple[int, ...], int], int] = {}

    def key(txn: dict[str, Any]) -> tuple[str, tuple[int, ...], int]:
        return txn["master"], tuple(txn["index"]), txn["address"] & addr_mask

    async def read(txn: dict[str, Any]) -> None:
        await driver.transfer(
            txn["address"] & addr_mask, expected=shadow.get(key(txn), 0),
            error=not txn["readable"],
        )

    async def write(txn: dict[str, Any], data: int, strobe: int) -> None:
        await driver.transfer(
            txn["address"] & addr_mask, write=True, data=data, strobe=strobe,
            error=not txn["writable"],
        )
        if txn["writable"]:
            shadow[key(txn)] = _merge_bytes(shadow.get(key(txn), 0), data, strobe, byte_width)

    # Read every sampled address before any write: a child starts at zero, not at
    # a value supplied by this driver. Different children may share local offsets.
    for txn in shuffle_transactions(config["transactions"], rng):
        await read(txn)
    for txn in shuffle_transactions(config["transactions"], rng):
        await write(txn, _write_pattern(txn["address"], config["data_width"]), full_strobe)

    strobes = [0, *(1 << lane for lane in range(byte_width)), full_strobe & 0x5555,
               full_strobe & 0xAAAA, full_strobe]
    for ordinal, txn in enumerate(shuffle_transactions(config["transactions"], rng)):
        await write(txn, rng.getrandbits(config["data_width"]), strobes[ordinal % len(strobes)])
        await read(txn)

    # Even a one-register fixture must exercise every individual byte, preserved
    # unstroked bytes and a zero-strobe write after nonzero state exists.
    writable = next((txn for txn in config["transactions"] if txn["writable"] and txn["readable"]), None)
    assert writable is not None, "The stress fixture must provide a read/write endpoint"
    for strobe in strobes:
        await write(writable, rng.getrandbits(config["data_width"]), strobe)
        await read(writable)

    for txn in shuffle_transactions(config["transactions"], rng):
        await read(txn)
    dut._log.info(
        "APB4 autonomous RAM stress: %d real writes + %d real reads; all strobes retained",
        driver.writes, driver.reads,
    )
