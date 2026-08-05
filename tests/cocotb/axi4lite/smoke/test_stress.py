"""AXI4-Lite randomized transaction-stream smoke coverage."""

from __future__ import annotations

import cocotb

from tests.cocotb.axi4lite.smoke.test_register_access import (
    _AxilSlaveShim,
    _accept_read,
    _accept_write,
    _build_master_table,
    _complete_read_response,
    _complete_write_response,
    _initialize,
    _issue_read,
    _issue_write,
    _write_pattern,
)
from tests.cocotb_lib.protocol_utils import load_config, make_rng, shuffle_transactions


@cocotb.test()
async def test_axi4lite_random_traffic(dut) -> None:
    """Write/read every sampled register in deterministic randomized order."""
    config = load_config()
    if not config["transactions"]:
        dut._log.warning("No transactions available; skipping stress run")
        return

    is_intf = config.get("cpuif_style") == "interface"
    slave = _AxilSlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)
    await _initialize(dut, slave, masters)

    rng = make_rng()
    addr_mask = (1 << config["address_width"]) - 1
    strobe_mask = (1 << config["byte_width"]) - 1
    shadow: dict[tuple[str, tuple[int, ...], int], int] = {}

    write_order = shuffle_transactions(config["transactions"], rng)
    for txn in write_order:
        entry = masters[txn["master"]]
        index = tuple(txn["index"])
        address = txn["address"] & addr_mask
        child_addr = (address - entry["inst_address"]) % entry["inst_size"]
        data = _write_pattern(address, config["data_width"])
        strobe_choices = [strobe_mask, strobe_mask, strobe_mask & 0x5, strobe_mask & 0xA]
        strobe = rng.choice([candidate for candidate in strobe_choices if candidate])
        order = rng.choice(["together", "aw_first", "w_first"])

        await _accept_write(dut, slave, address, data, strobe, order=order)
        await _issue_write(
            dut,
            entry,
            index,
            expected_addr=child_addr,
            data=data,
            strobe=strobe,
        )
        await _complete_write_response(dut, slave, entry, index, 0)
        shadow[(txn["master"], index, address)] = data

    read_order = shuffle_transactions(config["transactions"], rng)
    for txn in read_order:
        entry = masters[txn["master"]]
        index = tuple(txn["index"])
        address = txn["address"] & addr_mask
        child_addr = (address - entry["inst_address"]) % entry["inst_size"]
        expected = shadow[(txn["master"], index, address)]

        await _accept_read(dut, slave, address)
        await _issue_read(dut, entry, index, expected_addr=child_addr)
        await _complete_read_response(dut, slave, entry, index, expected, 0)

    dut._log.info(
        f"AXI4-Lite stress: completed {len(write_order)} writes + {len(read_order)} reads"
    )
