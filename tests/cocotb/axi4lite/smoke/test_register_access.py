"""Clocked AXI4-Lite protocol and ordered-response tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge, Timer

from tests.cocotb_lib.handle_utils import make_signal_handle
from tests.cocotb_lib.protocol_utils import (
    all_index_pairs,
    find_invalid_address,
    get_int,
    load_config,
    pick_distinct_pairs,
    set_value,
)


class _AxilSlaveShim:
    """Accessor for flat ports and directly visible SV interfaces."""

    def __init__(self, dut, *, is_interface: bool = False):
        if is_interface:
            intf = dut.s_axil
            prefix = None
        else:
            intf = dut
            prefix = "s_axil_"

        def signal(name: str):
            return getattr(intf, name if prefix is None else f"{prefix}{name}")

        self.AWREADY = signal("AWREADY")
        self.AWVALID = signal("AWVALID")
        self.AWADDR = signal("AWADDR")
        self.AWPROT = signal("AWPROT")
        self.WREADY = signal("WREADY")
        self.WVALID = signal("WVALID")
        self.WDATA = signal("WDATA")
        self.WSTRB = signal("WSTRB")
        self.BREADY = signal("BREADY")
        self.BVALID = signal("BVALID")
        self.BRESP = signal("BRESP")
        self.ARREADY = signal("ARREADY")
        self.ARVALID = signal("ARVALID")
        self.ARADDR = signal("ARADDR")
        self.ARPROT = signal("ARPROT")
        self.RREADY = signal("RREADY")
        self.RVALID = signal("RVALID")
        self.RDATA = signal("RDATA")
        self.RRESP = signal("RRESP")


def _build_master_table(
    dut, masters_cfg: list[dict[str, Any]], *, is_interface: bool = False
) -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for master in masters_cfg:
        prefix = master["port_prefix"]
        table[master["inst_name"]] = {
            "indices": [tuple(idx) for idx in master["indices"]] or [tuple()],
            "outputs": {
                name: make_signal_handle(dut, prefix, name, is_interface=is_interface)
                for name in (
                    "AWVALID",
                    "AWADDR",
                    "AWPROT",
                    "WVALID",
                    "WDATA",
                    "WSTRB",
                    "BREADY",
                    "ARVALID",
                    "ARADDR",
                    "ARPROT",
                    "RREADY",
                )
            },
            "inputs": {
                name: make_signal_handle(dut, prefix, name, is_interface=is_interface)
                for name in (
                    "AWREADY",
                    "WREADY",
                    "BVALID",
                    "BRESP",
                    "ARREADY",
                    "RVALID",
                    "RDATA",
                    "RRESP",
                )
            },
            "inst_size": master["inst_size"],
            "inst_address": master["inst_address"],
        }
    return table


def _write_pattern(address: int, width: int) -> int:
    return ((address * 0x3105) ^ 0x1357_9BDF) & ((1 << width) - 1)


def _read_pattern(address: int, width: int) -> int:
    return ((address ^ 0x2468_ACED) + width) & ((1 << width) - 1)


def _idle_slave(slave: _AxilSlaveShim) -> None:
    slave.AWVALID.value = 0
    slave.AWADDR.value = 0
    slave.AWPROT.value = 0
    slave.WVALID.value = 0
    slave.WDATA.value = 0
    slave.WSTRB.value = 0
    slave.BREADY.value = 0
    slave.ARVALID.value = 0
    slave.ARADDR.value = 0
    slave.ARPROT.value = 0
    slave.RREADY.value = 0


def _idle_masters(masters: dict[str, dict[str, Any]]) -> None:
    for master_name, idx in all_index_pairs(masters):
        entry = masters[master_name]
        for name in ("AWREADY", "WREADY", "BVALID", "BRESP", "ARREADY", "RVALID", "RDATA", "RRESP"):
            set_value(entry["inputs"][name], idx, 0)


async def _initialize(dut, slave: _AxilSlaveShim, masters: dict[str, dict[str, Any]]) -> None:
    """Start the design clock and put the decoder through its async reset."""
    _idle_slave(slave)
    _idle_masters(masters)
    dut.clk.value = 0
    dut.rst.value = 1
    cocotb.start_soon(Clock(dut.clk, 2, unit="ns").start())
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert int(slave.AWREADY.value) == 1
    assert int(slave.WREADY.value) == 1
    assert int(slave.ARREADY.value) == 1


async def _wait_until(dut, predicate: Callable[[], bool], message: str, cycles: int = 30) -> None:
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if predicate():
            return
    raise AssertionError(message)


async def _handshake_ready(dut, ready, message: str) -> None:
    """Wait for READY and then the edge that accepts the already-driven VALID."""
    for _ in range(30):
        # READY is sampled before the active edge. Sampling it after the edge
        # can miss a handshake because the holding register immediately makes
        # READY fall.
        await Timer(1, unit="ps")
        if int(ready.value) == 1:
            await RisingEdge(dut.clk)
            return
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
    raise AssertionError(message)


async def _accept_write(
    dut,
    slave: _AxilSlaveShim,
    address: int,
    data: int,
    strobe: int,
    *,
    prot: int = 0,
    order: str = "together",
) -> None:
    """Complete upstream AW and W handshakes in the requested channel order."""

    async def send_aw() -> None:
        await FallingEdge(dut.clk)
        slave.AWADDR.value = address
        slave.AWPROT.value = prot
        slave.AWVALID.value = 1
        await _handshake_ready(dut, slave.AWREADY, "AW was not accepted")
        await FallingEdge(dut.clk)
        slave.AWVALID.value = 0

    async def send_w() -> None:
        await FallingEdge(dut.clk)
        slave.WDATA.value = data
        slave.WSTRB.value = strobe
        slave.WVALID.value = 1
        await _handshake_ready(dut, slave.WREADY, "W was not accepted")
        await FallingEdge(dut.clk)
        slave.WVALID.value = 0

    if order == "aw_first":
        await send_aw()
        await send_w()
    elif order == "w_first":
        await send_w()
        await send_aw()
    else:
        await FallingEdge(dut.clk)
        slave.AWADDR.value = address
        slave.AWPROT.value = prot
        slave.WDATA.value = data
        slave.WSTRB.value = strobe
        slave.AWVALID.value = 1
        slave.WVALID.value = 1
        await Timer(1, unit="ps")
        if int(slave.AWREADY.value) != 1 or int(slave.WREADY.value) != 1:
            raise AssertionError("AW/W were not accepted")
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        slave.AWVALID.value = 0
        slave.WVALID.value = 0


async def _accept_read(dut, slave: _AxilSlaveShim, address: int, *, prot: int = 0) -> None:
    await FallingEdge(dut.clk)
    slave.ARADDR.value = address
    slave.ARPROT.value = prot
    slave.ARVALID.value = 1
    await _handshake_ready(dut, slave.ARREADY, "AR was not accepted")
    await FallingEdge(dut.clk)
    slave.ARVALID.value = 0


async def _complete_write_response(
    dut,
    slave: _AxilSlaveShim,
    entry: dict[str, Any],
    index: tuple[int, ...],
    response: int,
) -> None:
    """Present a child response, verify it holds, then accept it upstream."""
    await FallingEdge(dut.clk)
    set_value(entry["inputs"]["BRESP"], index, response)
    set_value(entry["inputs"]["BVALID"], index, 1)
    await _wait_until(dut, lambda: int(slave.BVALID.value) == 1, "B response did not reach upstream")
    assert int(slave.BRESP.value) == response
    assert get_int(entry["outputs"]["BREADY"], index) == 0
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert int(slave.BVALID.value) == 1
    assert int(slave.BRESP.value) == response
    await FallingEdge(dut.clk)
    slave.BREADY.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    slave.BREADY.value = 0
    set_value(entry["inputs"]["BVALID"], index, 0)


async def _complete_read_response(
    dut,
    slave: _AxilSlaveShim,
    entry: dict[str, Any],
    index: tuple[int, ...],
    data: int,
    response: int,
) -> None:
    await FallingEdge(dut.clk)
    set_value(entry["inputs"]["RDATA"], index, data)
    set_value(entry["inputs"]["RRESP"], index, response)
    set_value(entry["inputs"]["RVALID"], index, 1)
    await _wait_until(dut, lambda: int(slave.RVALID.value) == 1, "R response did not reach upstream")
    assert int(slave.RDATA.value) == data
    assert int(slave.RRESP.value) == response
    assert get_int(entry["outputs"]["RREADY"], index) == 0
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert int(slave.RVALID.value) == 1
    assert int(slave.RDATA.value) == data
    assert int(slave.RRESP.value) == response
    await FallingEdge(dut.clk)
    slave.RREADY.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    slave.RREADY.value = 0
    set_value(entry["inputs"]["RVALID"], index, 0)


async def _issue_write(
    dut,
    entry: dict[str, Any],
    index: tuple[int, ...],
    *,
    expected_addr: int,
    data: int,
    strobe: int,
    prot: int = 0,
) -> None:
    await _wait_until(
        dut,
        lambda: get_int(entry["outputs"]["AWVALID"], index) == 1
        and get_int(entry["outputs"]["WVALID"], index) == 1,
        "write request was not issued downstream",
    )
    assert get_int(entry["outputs"]["AWADDR"], index) == expected_addr
    assert get_int(entry["outputs"]["AWPROT"], index) == prot
    assert get_int(entry["outputs"]["WDATA"], index) == data
    assert get_int(entry["outputs"]["WSTRB"], index) == strobe
    await FallingEdge(dut.clk)
    set_value(entry["inputs"]["AWREADY"], index, 1)
    set_value(entry["inputs"]["WREADY"], index, 1)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    set_value(entry["inputs"]["AWREADY"], index, 0)
    set_value(entry["inputs"]["WREADY"], index, 0)


async def _issue_read(
    dut, entry: dict[str, Any], index: tuple[int, ...], *, expected_addr: int, prot: int = 0
) -> None:
    await _wait_until(
        dut,
        lambda: get_int(entry["outputs"]["ARVALID"], index) == 1,
        "read request was not issued downstream",
    )
    assert get_int(entry["outputs"]["ARADDR"], index) == expected_addr
    assert get_int(entry["outputs"]["ARPROT"], index) == prot
    await FallingEdge(dut.clk)
    set_value(entry["inputs"]["ARREADY"], index, 1)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    set_value(entry["inputs"]["ARREADY"], index, 0)


def _test_context(dut):
    config = load_config()
    is_intf = config.get("cpuif_style") == "interface"
    slave = _AxilSlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)
    return config, slave, masters


@cocotb.test()
async def test_axi4lite_address_decoding(dut) -> None:
    """Every sampled address routes clocked read/write traffic to its child."""
    config, slave, masters = _test_context(dut)
    await _initialize(dut, slave, masters)
    addr_mask = (1 << config["address_width"]) - 1
    strobe = (1 << config["byte_width"]) - 1

    for txn in config["transactions"]:
        entry = masters[txn["master"]]
        index = tuple(txn["index"])
        address = txn["address"] & addr_mask
        child_addr = (address - entry["inst_address"]) % entry["inst_size"]
        data = _write_pattern(address, config["data_width"])

        await _accept_write(dut, slave, address, data, strobe, prot=0b101)
        await _issue_write(
            dut, entry, index, expected_addr=child_addr, data=data, strobe=strobe, prot=0b101
        )
        await _complete_write_response(dut, slave, entry, index, 0)

        read_data = _read_pattern(address, config["data_width"])
        await _accept_read(dut, slave, address, prot=0b011)
        await _issue_read(dut, entry, index, expected_addr=child_addr, prot=0b011)
        await _complete_read_response(dut, slave, entry, index, read_data, 0)


@cocotb.test()
async def test_axi4lite_independent_aw_w_and_read_direction(dut) -> None:
    """AW/W can arrive in either order, while the read direction remains live."""
    config, slave, masters = _test_context(dut)
    await _initialize(dut, slave, masters)
    if not config["transactions"]:
        return
    txn = config["transactions"][0]
    entry = masters[txn["master"]]
    index = tuple(txn["index"])
    address = txn["address"]
    child_addr = (address - entry["inst_address"]) % entry["inst_size"]
    strobe = (1 << config["byte_width"]) - 1

    # AW can be accepted and retained without W. A read accepted afterwards
    # must still issue independently.
    await FallingEdge(dut.clk)
    slave.AWADDR.value = address
    slave.AWPROT.value = 0
    slave.AWVALID.value = 1
    await _handshake_ready(dut, slave.AWREADY, "AW-first beat was not accepted")
    await FallingEdge(dut.clk)
    slave.AWVALID.value = 0
    await _accept_read(dut, slave, address)
    await _issue_read(dut, entry, index, expected_addr=child_addr)
    await _complete_read_response(dut, slave, entry, index, 0xA5, 0)

    await FallingEdge(dut.clk)
    slave.WDATA.value = 0x1234
    slave.WSTRB.value = strobe
    slave.WVALID.value = 1
    await _handshake_ready(dut, slave.WREADY, "W-second beat was not accepted")
    await FallingEdge(dut.clk)
    slave.WVALID.value = 0
    await _issue_write(dut, entry, index, expected_addr=child_addr, data=0x1234, strobe=strobe)
    await _complete_write_response(dut, slave, entry, index, 0)

    await _accept_write(dut, slave, address, 0x5678, strobe, order="w_first")
    await _issue_write(dut, entry, index, expected_addr=child_addr, data=0x5678, strobe=strobe)
    await _complete_write_response(dut, slave, entry, index, 0)


@cocotb.test()
async def test_axi4lite_unmapped_decerr_and_reset(dut) -> None:
    """Unmapped requests complete locally with DECERR; reset flushes state."""
    config, slave, masters = _test_context(dut)
    await _initialize(dut, slave, masters)
    invalid = find_invalid_address(config)
    if invalid is not None:
        await _accept_read(dut, slave, invalid)
        await _wait_until(dut, lambda: int(slave.RVALID.value) == 1, "unmapped read did not complete")
        assert int(slave.RRESP.value) == 0b11
        await FallingEdge(dut.clk)
        slave.RREADY.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        slave.RREADY.value = 0

        await _accept_write(dut, slave, invalid, 0xDEAD, 1)
        await _wait_until(dut, lambda: int(slave.BVALID.value) == 1, "unmapped write did not complete")
        assert int(slave.BRESP.value) == 0b11

    await FallingEdge(dut.clk)
    dut.rst.value = 1
    await ReadOnly()
    assert int(slave.AWREADY.value) == 0
    assert int(slave.WREADY.value) == 0
    assert int(slave.ARREADY.value) == 0
    assert int(slave.BVALID.value) == 0
    assert int(slave.RVALID.value) == 0


@cocotb.test()
async def test_axi4lite_cross_child_response_order(dut) -> None:
    """A faster later child cannot overtake an older read or write response."""
    config, slave, masters = _test_context(dut)
    await _initialize(dut, slave, masters)
    pair = pick_distinct_pairs(config["transactions"], 2)
    if len(pair) < 2:
        dut._log.info("Need two child destinations; skipping cross-child ordering case")
        return
    first, second = pair
    first_entry = masters[first["master"]]
    second_entry = masters[second["master"]]
    first_idx = tuple(first["index"])
    second_idx = tuple(second["index"])

    await _accept_read(dut, slave, first["address"])
    await _accept_read(dut, slave, second["address"])
    await _issue_read(
        dut,
        first_entry,
        first_idx,
        expected_addr=(first["address"] - first_entry["inst_address"]) % first_entry["inst_size"],
    )
    await _issue_read(
        dut,
        second_entry,
        second_idx,
        expected_addr=(second["address"] - second_entry["inst_address"]) % second_entry["inst_size"],
    )

    # The later response is already valid, but must remain backpressured and
    # invisible until the older response handshakes.
    await FallingEdge(dut.clk)
    set_value(second_entry["inputs"]["RDATA"], second_idx, 0x2222)
    set_value(second_entry["inputs"]["RVALID"], second_idx, 1)
    slave.RREADY.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert int(slave.RVALID.value) == 0
    assert get_int(second_entry["outputs"]["RREADY"], second_idx) == 0
    await FallingEdge(dut.clk)
    slave.RREADY.value = 0
    set_value(first_entry["inputs"]["RDATA"], first_idx, 0x1111)
    set_value(first_entry["inputs"]["RVALID"], first_idx, 1)
    await _wait_until(dut, lambda: int(slave.RVALID.value) == 1, "first read response missing")
    assert int(slave.RDATA.value) == 0x1111
    await FallingEdge(dut.clk)
    slave.RREADY.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert int(slave.RVALID.value) == 1
    assert int(slave.RDATA.value) == 0x2222
    await FallingEdge(dut.clk)
    slave.RREADY.value = 0
    set_value(first_entry["inputs"]["RVALID"], first_idx, 0)
    set_value(second_entry["inputs"]["RVALID"], second_idx, 0)

    strobe = (1 << config["byte_width"]) - 1
    await _accept_write(dut, slave, first["address"], 0xAAAA, strobe)
    await _accept_write(dut, slave, second["address"], 0xBBBB, strobe)
    await _issue_write(
        dut,
        first_entry,
        first_idx,
        expected_addr=(first["address"] - first_entry["inst_address"]) % first_entry["inst_size"],
        data=0xAAAA,
        strobe=strobe,
    )
    await _issue_write(
        dut,
        second_entry,
        second_idx,
        expected_addr=(second["address"] - second_entry["inst_address"]) % second_entry["inst_size"],
        data=0xBBBB,
        strobe=strobe,
    )
    await FallingEdge(dut.clk)
    set_value(second_entry["inputs"]["BRESP"], second_idx, 0b10)
    set_value(second_entry["inputs"]["BVALID"], second_idx, 1)
    slave.BREADY.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert int(slave.BVALID.value) == 0
    assert get_int(second_entry["outputs"]["BREADY"], second_idx) == 0
    await FallingEdge(dut.clk)
    slave.BREADY.value = 0
    set_value(first_entry["inputs"]["BRESP"], first_idx, 0)
    set_value(first_entry["inputs"]["BVALID"], first_idx, 1)
    await _wait_until(dut, lambda: int(slave.BVALID.value) == 1, "first write response missing")
    assert int(slave.BRESP.value) == 0
    await FallingEdge(dut.clk)
    slave.BREADY.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert int(slave.BVALID.value) == 1
    assert int(slave.BRESP.value) == 0b10


@cocotb.test()
async def test_axi4lite_same_child_delayed_responses(dut) -> None:
    """Two delayed responses from one child retain that child's AXI order."""
    config, slave, masters = _test_context(dut)
    await _initialize(dut, slave, masters)
    by_child: dict[tuple[str, tuple[int, ...]], list[dict[str, Any]]] = {}
    for txn in config["transactions"]:
        by_child.setdefault((txn["master"], tuple(txn["index"])), []).append(txn)
    txns = next((items[:2] for items in by_child.values() if len(items) >= 2), None)
    if txns is None:
        dut._log.info("Need two addresses in one child; skipping same-child ordering case")
        return
    first, second = txns
    entry = masters[first["master"]]
    index = tuple(first["index"])

    await _accept_read(dut, slave, first["address"])
    await _accept_read(dut, slave, second["address"])
    await _issue_read(
        dut,
        entry,
        index,
        expected_addr=(first["address"] - entry["inst_address"]) % entry["inst_size"],
    )
    await _issue_read(
        dut,
        entry,
        index,
        expected_addr=(second["address"] - entry["inst_address"]) % entry["inst_size"],
    )
    await _complete_read_response(dut, slave, entry, index, 0x1111, 0)
    await _complete_read_response(dut, slave, entry, index, 0x2222, 0b10)


@cocotb.test()
async def test_axi4lite_bounded_independent_queues(dut) -> None:
    """The default four-entry read/write queues backpressure independently."""
    config, slave, masters = _test_context(dut)
    await _initialize(dut, slave, masters)
    if not config["transactions"]:
        return
    address = config["transactions"][0]["address"]

    # Leave downstream request READY low so none of these requests can finish.
    for _ in range(4):
        await _accept_read(dut, slave, address)
    await Timer(1, unit="ps")
    assert int(slave.ARREADY.value) == 0
    assert int(slave.AWREADY.value) == 1
    assert int(slave.WREADY.value) == 1

    strobe = (1 << config["byte_width"]) - 1
    for value in range(4):
        await _accept_write(dut, slave, address, value, strobe)
    await Timer(1, unit="ps")
    assert int(slave.ARREADY.value) == 0
    assert int(slave.AWREADY.value) == 0
    assert int(slave.WREADY.value) == 0
