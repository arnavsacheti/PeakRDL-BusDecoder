"""AXI4-Lite stress tests: long randomized transaction streams with write/read-back checks."""

from __future__ import annotations

from typing import Any

import cocotb
from cocotb.triggers import Timer

from tests.cocotb.axi4lite.smoke.test_register_access import (
    _AxilSlaveShim,
    _build_master_table,
    _idle_masters,
    _idle_slave,
    _write_pattern,
)
from tests.cocotb_lib.protocol_utils import (
    load_config,
    make_rng,
    set_value,
    shuffle_transactions,
)


async def _axil_write(
    slave: _AxilSlaveShim,
    entry: dict[str, Any],
    index: tuple[int, ...],
    address: int,
    data: int,
    strobe: int,
) -> None:
    set_value(entry["inputs"]["BRESP"], index, 0)
    set_value(entry["inputs"]["BVALID"], index, 1)

    slave.AWADDR.value = address
    slave.AWPROT.value = 0
    slave.AWVALID.value = 1
    slave.WDATA.value = data
    slave.WSTRB.value = strobe
    slave.WVALID.value = 1
    slave.BREADY.value = 1
    await Timer(1, unit="ns")

    assert int(slave.AWREADY.value) == 1, "AWREADY should assert once both AW & W are valid"
    assert int(slave.WREADY.value) == 1, "WREADY should assert once both AW & W are valid"
    assert int(slave.BVALID.value) == 1, "BVALID should mirror master BVALID"
    assert int(slave.BRESP.value) == 0, f"Stress write 0x{address:x} expected OKAY BRESP"

    slave.AWVALID.value = 0
    slave.WVALID.value = 0
    slave.BREADY.value = 0
    set_value(entry["inputs"]["BVALID"], index, 0)
    await Timer(1, unit="ns")


async def _axil_read(
    slave: _AxilSlaveShim,
    entry: dict[str, Any],
    index: tuple[int, ...],
    address: int,
    expected: int,
    rvalid_delay: int,
) -> None:
    set_value(entry["inputs"]["RVALID"], index, 0)
    set_value(entry["inputs"]["RDATA"], index, expected)
    set_value(entry["inputs"]["RRESP"], index, 0)

    slave.ARADDR.value = address
    slave.ARPROT.value = 0
    slave.ARVALID.value = 1
    slave.RREADY.value = 1

    for _ in range(rvalid_delay):
        await Timer(1, unit="ns")

    set_value(entry["inputs"]["RVALID"], index, 1)
    await Timer(1, unit="ns")

    assert int(slave.RVALID.value) == 1, f"RVALID must propagate at 0x{address:x}"
    assert int(slave.RDATA.value) == expected, (
        f"Stress read mismatch at 0x{address:x}: "
        f"expected 0x{expected:x}, got 0x{int(slave.RDATA.value):x}"
    )
    assert int(slave.RRESP.value) == 0, "Stress read should yield OKAY"

    slave.ARVALID.value = 0
    slave.RREADY.value = 0
    set_value(entry["inputs"]["RVALID"], index, 0)
    set_value(entry["inputs"]["RDATA"], index, 0)
    await Timer(1, unit="ns")


@cocotb.test()
async def test_axi4lite_random_traffic(dut) -> None:
    """Drive every sampled register with write/read-back in a shuffled, jittered sequence."""
    config = load_config()
    if not config["transactions"]:
        dut._log.warning("No transactions available; skipping stress run")
        return

    is_intf = config.get("cpuif_style") == "interface"
    slave = _AxilSlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    _idle_slave(slave)
    _idle_masters(masters)
    await Timer(1, unit="ns")

    rng = make_rng()
    addr_mask = (1 << config["address_width"]) - 1
    strobe_mask = (1 << config["byte_width"]) - 1
    shadow: dict[tuple[str, tuple[int, ...], int], int] = {}

    write_order = shuffle_transactions(config["transactions"], rng)
    for txn in write_order:
        entry = masters[txn["master"]]
        index = tuple(txn["index"])
        address = txn["address"] & addr_mask
        data = _write_pattern(address, config["data_width"])
        strobe_choices = [strobe_mask, strobe_mask, strobe_mask & 0x5, strobe_mask & 0xA]
        strobe = rng.choice([s for s in strobe_choices if s]) or strobe_mask
        await _axil_write(slave, entry, index, address, data, strobe)
        shadow[(txn["master"], index, address)] = data

    read_order = shuffle_transactions(config["transactions"], rng)
    for txn in read_order:
        entry = masters[txn["master"]]
        index = tuple(txn["index"])
        address = txn["address"] & addr_mask
        expected = shadow[(txn["master"], index, address)]
        await _axil_read(slave, entry, index, address, expected, rng.randint(0, 2))

    dut._log.info(
        f"AXI4-Lite stress: completed {len(write_order)} writes + {len(read_order)} reads"
    )
