"""APB4 smoke tests generated from SystemRDL sources."""

from __future__ import annotations

from typing import Any

import cocotb
from cocotb.triggers import RisingEdge, Timer

from tests.cocotb_lib.handle_utils import SignalHandle
from tests.cocotb_lib.protocol_utils import (
    all_index_pairs,
    find_invalid_address,
    get_int,
    load_config,
    set_value,
    start_clock,
)


class _Apb4SlaveShim:
    """Lightweight accessor for the APB4 slave side of the DUT."""

    def __init__(self, dut):
        prefix = "s_apb"
        self.PCLK = getattr(dut, f"{prefix}_PCLK", None)
        self.PRESETn = getattr(dut, f"{prefix}_PRESETn", None)
        self.PSEL = getattr(dut, f"{prefix}_PSEL")
        self.PENABLE = getattr(dut, f"{prefix}_PENABLE")
        self.PWRITE = getattr(dut, f"{prefix}_PWRITE")
        self.PADDR = getattr(dut, f"{prefix}_PADDR")
        self.PPROT = getattr(dut, f"{prefix}_PPROT")
        self.PWDATA = getattr(dut, f"{prefix}_PWDATA")
        self.PSTRB = getattr(dut, f"{prefix}_PSTRB")
        self.PRDATA = getattr(dut, f"{prefix}_PRDATA")
        self.PREADY = getattr(dut, f"{prefix}_PREADY")
        self.PSLVERR = getattr(dut, f"{prefix}_PSLVERR")


def _build_master_table(dut, masters_cfg: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for master in masters_cfg:
        port_prefix = master["port_prefix"]
        entry = {
            "port_prefix": port_prefix,
            "indices": [tuple(idx) for idx in master["indices"]] or [tuple()],
            "outputs": {
                "PSEL": SignalHandle(dut, f"{port_prefix}_PSEL"),
                "PENABLE": SignalHandle(dut, f"{port_prefix}_PENABLE"),
                "PWRITE": SignalHandle(dut, f"{port_prefix}_PWRITE"),
                "PADDR": SignalHandle(dut, f"{port_prefix}_PADDR"),
                "PPROT": SignalHandle(dut, f"{port_prefix}_PPROT"),
                "PWDATA": SignalHandle(dut, f"{port_prefix}_PWDATA"),
                "PSTRB": SignalHandle(dut, f"{port_prefix}_PSTRB"),
            },
            "inputs": {
                "PRDATA": SignalHandle(dut, f"{port_prefix}_PRDATA"),
                "PREADY": SignalHandle(dut, f"{port_prefix}_PREADY"),
                "PSLVERR": SignalHandle(dut, f"{port_prefix}_PSLVERR"),
            },
            "inst_size": master["inst_size"],
            "inst_address": master["inst_address"],
        }
        table[master["inst_name"]] = entry
    return table


def _write_pattern(address: int, width: int) -> int:
    mask = (1 << width) - 1
    return ((address * 0x1021) ^ 0x1357_9BDF) & mask


def _read_pattern(address: int, width: int) -> int:
    mask = (1 << width) - 1
    return ((address ^ 0xDEAD_BEE5) + width) & mask


@cocotb.test()
async def test_apb4_address_decoding(dut) -> None:
    """Drive the APB4 slave interface and verify master fanout across all sampled registers."""
    config = load_config()
    slave = _Apb4SlaveShim(dut)
    masters = _build_master_table(dut, config["masters"])

    await start_clock(slave.PCLK)
    if slave.PRESETn is not None:
        slave.PRESETn.value = 1

    slave.PSEL.value = 0
    slave.PENABLE.value = 0
    slave.PWRITE.value = 0
    slave.PADDR.value = 0
    slave.PPROT.value = 0
    slave.PWDATA.value = 0
    slave.PSTRB.value = 0

    for master_name, idx in all_index_pairs(masters):
        entry = masters[master_name]
        set_value(entry["inputs"]["PRDATA"], idx, 0)
        set_value(entry["inputs"]["PREADY"], idx, 0)
        set_value(entry["inputs"]["PSLVERR"], idx, 0)

    if slave.PCLK is not None:
        await RisingEdge(slave.PCLK)
    else:
        await Timer(1, unit="ns")

    addr_mask = (1 << config["address_width"]) - 1
    strobe_mask = (1 << config["byte_width"]) - 1

    for txn in config["transactions"]:
        master_name = txn["master"]
        index = tuple(txn["index"])
        entry = masters[master_name]

        address = txn["address"] & addr_mask
        write_data = _write_pattern(address, config["data_width"])

        # Prime master-side inputs for the write phase
        set_value(entry["inputs"]["PREADY"], index, 0)
        set_value(entry["inputs"]["PSLVERR"], index, 0)

        # ------------------------------------------------------------------
        # Setup phase
        # ------------------------------------------------------------------
        slave.PADDR.value = address
        slave.PWDATA.value = write_data
        slave.PSTRB.value = strobe_mask
        slave.PPROT.value = 0
        slave.PWRITE.value = 1
        slave.PSEL.value = 1
        slave.PENABLE.value = 0

        dut._log.info(
            f"Starting transaction {txn['label']} to {master_name}{index} at address 0x{address:08X}"
        )
        master_address = (address - entry["inst_address"]) % entry["inst_size"]

        if slave.PCLK is not None:
            await RisingEdge(slave.PCLK)
        else:
            await Timer(1, unit="ns")

        assert get_int(entry["outputs"]["PSEL"], index) == 1, f"{master_name} should assert PSEL for write"
        assert get_int(entry["outputs"]["PENABLE"], index) == 0, (
            f"{master_name} must hold PENABLE low in setup"
        )
        assert get_int(entry["outputs"]["PWRITE"], index) == 1, f"{master_name} should see write intent"
        assert get_int(entry["outputs"]["PADDR"], index) == master_address, (
            f"{master_name} must receive write address"
        )
        assert get_int(entry["outputs"]["PWDATA"], index) == write_data, (
            f"{master_name} must receive write data"
        )
        assert get_int(entry["outputs"]["PSTRB"], index) == strobe_mask, (
            f"{master_name} must receive full strobes"
        )

        for other_name, other_idx in all_index_pairs(masters):
            if other_name == master_name and other_idx == index:
                continue
            other_entry = masters[other_name]
            assert get_int(other_entry["outputs"]["PSEL"], other_idx) == 0, (
                f"{other_name}{other_idx} should remain idle during {txn['label']}"
            )

        # ------------------------------------------------------------------
        # Access phase
        # ------------------------------------------------------------------
        set_value(entry["inputs"]["PREADY"], index, 1)
        slave.PENABLE.value = 1

        if slave.PCLK is not None:
            await RisingEdge(slave.PCLK)
        else:
            await Timer(1, unit="ns")

        assert get_int(entry["outputs"]["PSEL"], index) == 1, f"{master_name} must keep PSEL asserted"
        assert get_int(entry["outputs"]["PENABLE"], index) == 1, (
            f"{master_name} must assert PENABLE in access"
        )
        assert get_int(entry["outputs"]["PADDR"], index) == master_address, (
            f"{master_name} must keep write address stable"
        )
        assert get_int(entry["outputs"]["PWDATA"], index) == write_data, (
            f"{master_name} must keep write data stable"
        )
        assert get_int(entry["outputs"]["PSTRB"], index) == strobe_mask, (
            f"{master_name} must keep write strobes stable"
        )

        assert int(slave.PREADY.value) == 1, "Slave ready should reflect selected master"
        assert int(slave.PSLVERR.value) == 0, "No error expected during write"

        # Return to idle for next transaction
        slave.PSEL.value = 0
        slave.PENABLE.value = 0
        slave.PWRITE.value = 0
        set_value(entry["inputs"]["PREADY"], index, 0)
        if slave.PCLK is not None:
            await RisingEdge(slave.PCLK)
        else:
            await Timer(1, unit="ns")

        # ------------------------------------------------------------------
        # Read phase
        # ------------------------------------------------------------------
        read_data = _read_pattern(address, config["data_width"])
        set_value(entry["inputs"]["PRDATA"], index, read_data)
        set_value(entry["inputs"]["PREADY"], index, 0)
        set_value(entry["inputs"]["PSLVERR"], index, 0)

        # ------------------------------------------------------------------
        # Setup phase
        # ------------------------------------------------------------------
        slave.PADDR.value = address
        slave.PWRITE.value = 0
        slave.PSEL.value = 1
        slave.PENABLE.value = 0

        if slave.PCLK is not None:
            await RisingEdge(slave.PCLK)
        else:
            await Timer(1, unit="ns")

        assert get_int(entry["outputs"]["PSEL"], index) == 1, f"{master_name} must assert PSEL for read"
        assert get_int(entry["outputs"]["PENABLE"], index) == 0, (
            f"{master_name} must hold PENABLE low in setup"
        )
        assert get_int(entry["outputs"]["PWRITE"], index) == 0, (
            f"{master_name} should deassert write for reads"
        )
        assert get_int(entry["outputs"]["PADDR"], index) == master_address, (
            f"{master_name} must receive read address"
        )

        for other_name, other_idx in all_index_pairs(masters):
            if other_name == master_name and other_idx == index:
                continue
            other_entry = masters[other_name]
            assert get_int(other_entry["outputs"]["PSEL"], other_idx) == 0, (
                f"{other_name}{other_idx} must stay idle during read of {txn['label']}"
            )

        # ------------------------------------------------------------------
        # Access phase
        # ------------------------------------------------------------------
        set_value(entry["inputs"]["PREADY"], index, 1)
        slave.PENABLE.value = 1

        if slave.PCLK is not None:
            await RisingEdge(slave.PCLK)
        else:
            await Timer(1, unit="ns")

        assert get_int(entry["outputs"]["PSEL"], index) == 1, f"{master_name} must keep PSEL asserted"
        assert get_int(entry["outputs"]["PENABLE"], index) == 1, (
            f"{master_name} must assert PENABLE in access"
        )

        assert int(slave.PRDATA.value) == read_data, "Slave should observe readback data from master"
        assert int(slave.PREADY.value) == 1, "Slave ready should follow responding master"
        assert int(slave.PSLVERR.value) == 0, "Read should complete without error"

        # Reset to idle before progressing
        slave.PSEL.value = 0
        slave.PENABLE.value = 0
        set_value(entry["inputs"]["PREADY"], index, 0)
        set_value(entry["inputs"]["PRDATA"], index, 0)
        if slave.PCLK is not None:
            await RisingEdge(slave.PCLK)
        else:
            await Timer(1, unit="ns")


@cocotb.test()
async def test_apb4_invalid_address_response(dut) -> None:
    """Ensure invalid addresses yield an error response and no master select."""
    config = load_config()
    slave = _Apb4SlaveShim(dut)
    masters = _build_master_table(dut, config["masters"])

    await start_clock(slave.PCLK)
    if slave.PRESETn is not None:
        slave.PRESETn.value = 1

    slave.PSEL.value = 0
    slave.PENABLE.value = 0
    slave.PWRITE.value = 0
    slave.PADDR.value = 0
    slave.PPROT.value = 0
    slave.PWDATA.value = 0
    slave.PSTRB.value = 0

    for master_name, idx in all_index_pairs(masters):
        entry = masters[master_name]
        set_value(entry["inputs"]["PREADY"], idx, 0)
        set_value(entry["inputs"]["PSLVERR"], idx, 0)
        set_value(entry["inputs"]["PRDATA"], idx, 0)

    invalid_addr = find_invalid_address(config)
    if invalid_addr is None:
        dut._log.warning("No unmapped address found; skipping invalid address test")
        return

    slave.PADDR.value = invalid_addr
    slave.PWRITE.value = 1
    slave.PWDATA.value = _write_pattern(invalid_addr, config["data_width"])
    slave.PSTRB.value = (1 << config["byte_width"]) - 1
    slave.PSEL.value = 1
    slave.PENABLE.value = 0

    if slave.PCLK is not None:
        await RisingEdge(slave.PCLK)
    else:
        await Timer(1, unit="ns")

    slave.PENABLE.value = 1

    if slave.PCLK is not None:
        await RisingEdge(slave.PCLK)
    else:
        await Timer(1, unit="ns")

    for master_name, idx in all_index_pairs(masters):
        entry = masters[master_name]
        assert get_int(entry["outputs"]["PSEL"], idx) == 0, (
            f"{master_name}{idx} must stay idle for invalid address"
        )

    assert int(slave.PREADY.value) == 1, "Invalid address should still complete the transfer"
    assert int(slave.PSLVERR.value) == 1, "Invalid address should raise PSLVERR"
