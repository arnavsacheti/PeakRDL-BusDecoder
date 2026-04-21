"""APB3 stress tests: long randomized transaction streams with write/read-back checks."""

from __future__ import annotations

from typing import Any

import cocotb

from tests.cocotb.apb3.smoke.test_register_access import (
    _Apb3SlaveShim,
    _build_master_table,
    _idle_masters,
    _idle_slave,
    _write_pattern,
)
from tests.cocotb_lib.protocol_utils import (
    advance,
    load_config,
    make_rng,
    set_value,
    shuffle_transactions,
    start_clock,
)


async def _apb3_write(
    slave: _Apb3SlaveShim,
    entry: dict[str, Any],
    index: tuple[int, ...],
    address: int,
    data: int,
    ready_delay: int,
) -> None:
    set_value(entry["inputs"]["PSLVERR"], index, 0)
    set_value(entry["inputs"]["PREADY"], index, 0)

    slave.PADDR.value = address
    slave.PWDATA.value = data
    slave.PWRITE.value = 1
    slave.PSEL.value = 1
    slave.PENABLE.value = 0
    await advance(slave.PCLK)

    slave.PENABLE.value = 1
    for _ in range(ready_delay):
        await advance(slave.PCLK)

    set_value(entry["inputs"]["PREADY"], index, 1)
    await advance(slave.PCLK)

    slave.PSEL.value = 0
    slave.PENABLE.value = 0
    slave.PWRITE.value = 0
    set_value(entry["inputs"]["PREADY"], index, 0)
    await advance(slave.PCLK)


async def _apb3_read(
    slave: _Apb3SlaveShim,
    entry: dict[str, Any],
    index: tuple[int, ...],
    address: int,
    expected: int,
    ready_delay: int,
) -> None:
    set_value(entry["inputs"]["PRDATA"], index, expected)
    set_value(entry["inputs"]["PSLVERR"], index, 0)
    set_value(entry["inputs"]["PREADY"], index, 0)

    slave.PADDR.value = address
    slave.PWRITE.value = 0
    slave.PSEL.value = 1
    slave.PENABLE.value = 0
    await advance(slave.PCLK)

    slave.PENABLE.value = 1
    for _ in range(ready_delay):
        await advance(slave.PCLK)

    set_value(entry["inputs"]["PREADY"], index, 1)
    await advance(slave.PCLK)
    assert int(slave.PRDATA.value) == expected, (
        f"Slave PRDATA mismatch at address 0x{address:x}: "
        f"expected 0x{expected:x}, got 0x{int(slave.PRDATA.value):x}"
    )
    assert int(slave.PSLVERR.value) == 0, "Stress read should not raise PSLVERR"

    slave.PSEL.value = 0
    slave.PENABLE.value = 0
    set_value(entry["inputs"]["PREADY"], index, 0)
    set_value(entry["inputs"]["PRDATA"], index, 0)
    await advance(slave.PCLK)


@cocotb.test()
async def test_apb3_random_traffic(dut) -> None:
    """Drive every sampled register with write/read-back in a shuffled, jittered sequence."""
    config = load_config()
    if not config["transactions"]:
        dut._log.warning("No transactions available; skipping stress run")
        return

    is_intf = config.get("cpuif_style") == "interface"
    slave = _Apb3SlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    await start_clock(slave.PCLK)
    if slave.PRESETn is not None:
        slave.PRESETn.value = 1
    _idle_slave(slave)
    _idle_masters(masters)
    await advance(slave.PCLK)

    rng = make_rng()
    addr_mask = (1 << config["address_width"]) - 1
    shadow: dict[tuple[str, tuple[int, ...], int], int] = {}

    write_order = shuffle_transactions(config["transactions"], rng)
    for txn in write_order:
        entry = masters[txn["master"]]
        index = tuple(txn["index"])
        address = txn["address"] & addr_mask
        data = _write_pattern(address, config["data_width"])
        await _apb3_write(slave, entry, index, address, data, rng.randint(0, 2))
        shadow[(txn["master"], index, address)] = data

    read_order = shuffle_transactions(config["transactions"], rng)
    for txn in read_order:
        entry = masters[txn["master"]]
        index = tuple(txn["index"])
        address = txn["address"] & addr_mask
        expected = shadow[(txn["master"], index, address)]
        await _apb3_read(slave, entry, index, address, expected, rng.randint(0, 2))

    dut._log.info(
        f"APB3 stress: completed {len(write_order)} writes + {len(read_order)} reads"
    )
