"""Behavioral coverage for high address bits on an SV-interface AXI4-Lite DUT."""

from __future__ import annotations

from typing import Any

import cocotb
from cocotb.triggers import Event, FallingEdge, ReadOnly, RisingEdge

from tests.cocotb.axi4lite.smoke.test_register_access import (
    _accept_read,
    _accept_write,
    _AxilSlaveShim,
    _build_master_table,
    _complete_read_response,
    _complete_write_response,
    _initialize,
    _issue_read,
    _issue_write,
    _wait_until,
)
from tests.cocotb_lib.protocol_utils import all_index_pairs, get_int, load_config


async def _mapped_pair(dut, slave, masters, config, sequence: int) -> None:
    """Route both directions normally, and fully retire their child responses."""
    txn = config["wide_address_transaction"]
    entry = masters[txn["master"]]
    index = tuple(txn["index"])
    address = txn["address"]
    child_address = (address - entry["inst_address"]) % entry["inst_size"]
    data_mask = (1 << config["data_width"]) - 1
    write_data = (0xCAFE_1234 ^ sequence) & data_mask
    read_data = (0x8765_4321 ^ sequence) & data_mask
    strobe = (1 << config["byte_width"]) - 1

    async def write() -> None:
        await _accept_write(dut, slave, address, write_data, strobe, prot=0b101)
        await _issue_write(
            dut,
            entry,
            index,
            expected_addr=child_address,
            data=write_data,
            strobe=strobe,
            prot=0b101,
        )
        await _complete_write_response(dut, slave, entry, index, 0)

    async def read() -> None:
        await _accept_read(dut, slave, address, prot=0b011)
        await _issue_read(dut, entry, index, expected_addr=child_address, prot=0b011)
        await _complete_read_response(dut, slave, entry, index, read_data, 0)

    write_task = cocotb.start_soon(write())
    read_task = cocotb.start_soon(read())
    await write_task
    await read_task


async def _watch_no_downstream_requests(
    dut, masters: dict[str, dict[str, Any]], stop: Event
) -> None:
    """Observe every destination throughout acceptance, backpressure and retirement."""
    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()
        for master_name, index in all_index_pairs(masters):
            for channel in ("AWVALID", "WVALID", "ARVALID"):
                assert get_int(masters[master_name]["outputs"][channel], index) == 0, (
                    f"High address escaped to {master_name}{index}.{channel}"
                )
        if stop.is_set():
            return


async def _reject_pair(dut, slave, masters, config, high_bit: int, order: str) -> None:
    """Reject concurrent high-address traffic locally, including W-before-AW."""
    low_address = config["wide_address_transaction"]["address"]
    high_address = low_address | (1 << high_bit)
    strobe = (1 << config["byte_width"]) - 1
    stop = Event()
    monitor = cocotb.start_soon(_watch_no_downstream_requests(dut, masters, stop))
    try:
        write_task = cocotb.start_soon(
            _accept_write(dut, slave, high_address, 0x1234, strobe, order=order)
        )
        read_task = cocotb.start_soon(_accept_read(dut, slave, high_address))
        await write_task
        await read_task

        # Accepted addresses must be retained independently of the live ports.
        # In particular, the high AW arriving after W must not be truncated or
        # replaced by this mapped address once AWVALID is deasserted.
        slave.AWADDR.value = low_address
        slave.ARADDR.value = low_address
        await _wait_until(
            dut,
            lambda: int(slave.BVALID.value) == 1 and int(slave.RVALID.value) == 1,
            f"High bit {high_bit} ({order}) did not produce local B and R responses",
        )
        assert int(slave.BREADY.value) == 0
        assert int(slave.RREADY.value) == 0
        error_data = int(slave.RDATA.value)
        for _ in range(4):
            assert int(slave.BVALID.value) == 1
            assert int(slave.BRESP.value) == 0b11
            assert int(slave.RVALID.value) == 1
            assert int(slave.RRESP.value) == 0b11
            assert int(slave.RDATA.value) == error_data
            await RisingEdge(dut.clk)
            await ReadOnly()

        # Retire the read first while the independent write DECERR stays held.
        await FallingEdge(dut.clk)
        slave.RREADY.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        slave.RREADY.value = 0
        for _ in range(3):
            await RisingEdge(dut.clk)
            await ReadOnly()
            assert int(slave.RVALID.value) == 0
            assert int(slave.BVALID.value) == 1
            assert int(slave.BRESP.value) == 0b11

        await FallingEdge(dut.clk)
        slave.BREADY.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        slave.BREADY.value = 0
        for _ in range(3):
            await RisingEdge(dut.clk)
            await ReadOnly()
            assert int(slave.BVALID.value) == 0
            assert int(slave.RVALID.value) == 0
    finally:
        stop.set()
        await monitor


@cocotb.test()
async def test_axi4lite_wide_upstream_address(dut) -> None:
    """Only low mapped addresses route; every tested extra address bit rejects."""
    config = load_config()
    slave = _AxilSlaveShim(dut)
    masters = _build_master_table(dut, config["masters"])
    assert len(slave.AWADDR) == config["upstream_address_width"]
    assert len(slave.ARADDR) == config["upstream_address_width"]
    assert config["upstream_address_width"] > config["address_width"]
    low_address = config["wide_address_transaction"]["address"]
    assert low_address < (1 << config["address_width"])
    await _initialize(dut, slave, masters)

    await _mapped_pair(dut, slave, masters, config, 0)
    sequence = 0
    for high_bit in config["high_address_bits"]:
        assert config["address_width"] <= high_bit < config["upstream_address_width"]
        for order in ("together", "aw_first", "w_first"):
            await _reject_pair(dut, slave, masters, config, high_bit, order)
            sequence += 1
            # A rejected request must leave neither direction nor the AW/W
            # pairing state wedged or carrying a stale high-address decision.
            await _mapped_pair(dut, slave, masters, config, sequence)
