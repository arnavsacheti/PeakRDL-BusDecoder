"""APB3 smoke tests generated from SystemRDL sources."""

from __future__ import annotations

from typing import Any

import cocotb
from cocotb.triggers import RisingEdge, Timer

from tests.cocotb_lib.handle_utils import make_signal_handle
from tests.cocotb_lib.protocol_utils import (
    all_index_pairs,
    find_invalid_address,
    get_int,
    load_config,
    set_value,
    start_clock,
)


class _Apb3SlaveShim:
    """Accessor for the APB3 slave signals on the DUT."""

    def __init__(self, dut, *, is_interface: bool = False):
        if is_interface:
            intf = dut.s_apb
            self.PCLK = getattr(intf, "PCLK", None)
            self.PRESETn = getattr(intf, "PRESETn", None)
            self.PSEL = intf.PSEL
            self.PENABLE = intf.PENABLE
            self.PWRITE = intf.PWRITE
            self.PADDR = intf.PADDR
            self.PWDATA = intf.PWDATA
            self.PRDATA = intf.PRDATA
            self.PREADY = intf.PREADY
            self.PSLVERR = intf.PSLVERR
        else:
            prefix = "s_apb"
            self.PCLK = getattr(dut, f"{prefix}_PCLK", None)
            self.PRESETn = getattr(dut, f"{prefix}_PRESETn", None)
            self.PSEL = getattr(dut, f"{prefix}_PSEL")
            self.PENABLE = getattr(dut, f"{prefix}_PENABLE")
            self.PWRITE = getattr(dut, f"{prefix}_PWRITE")
            self.PADDR = getattr(dut, f"{prefix}_PADDR")
            self.PWDATA = getattr(dut, f"{prefix}_PWDATA")
            self.PRDATA = getattr(dut, f"{prefix}_PRDATA")
            self.PREADY = getattr(dut, f"{prefix}_PREADY")
            self.PSLVERR = getattr(dut, f"{prefix}_PSLVERR")


def _build_master_table(
    dut, masters_cfg: list[dict[str, Any]], *, is_interface: bool = False
) -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for master in masters_cfg:
        prefix = master["port_prefix"]
        entry = {
            "indices": [tuple(idx) for idx in master["indices"]] or [tuple()],
            "outputs": {
                "PSEL": make_signal_handle(dut, prefix, "PSEL", is_interface=is_interface),
                "PENABLE": make_signal_handle(dut, prefix, "PENABLE", is_interface=is_interface),
                "PWRITE": make_signal_handle(dut, prefix, "PWRITE", is_interface=is_interface),
                "PADDR": make_signal_handle(dut, prefix, "PADDR", is_interface=is_interface),
                "PWDATA": make_signal_handle(dut, prefix, "PWDATA", is_interface=is_interface),
            },
            "inputs": {
                "PRDATA": make_signal_handle(dut, prefix, "PRDATA", is_interface=is_interface),
                "PREADY": make_signal_handle(dut, prefix, "PREADY", is_interface=is_interface),
                "PSLVERR": make_signal_handle(dut, prefix, "PSLVERR", is_interface=is_interface),
            },
            "inst_size": master["inst_size"],
            "inst_address": master["inst_address"],
        }
        table[master["inst_name"]] = entry
    return table


def _write_pattern(address: int, width: int) -> int:
    mask = (1 << width) - 1
    return ((address * 0x2041) ^ 0xCAFEBABE) & mask


def _read_pattern(address: int, width: int) -> int:
    mask = (1 << width) - 1
    return ((address ^ 0x0BAD_F00D) + width) & mask


@cocotb.test()
async def test_apb3_address_decoding(dut) -> None:
    """Exercise the APB3 slave interface against sampled register addresses."""
    config = load_config()
    is_intf = config.get("cpuif_style") == "interface"
    slave = _Apb3SlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    await start_clock(slave.PCLK)
    if slave.PRESETn is not None:
        slave.PRESETn.value = 1

    slave.PSEL.value = 0
    slave.PENABLE.value = 0
    slave.PWRITE.value = 0
    slave.PADDR.value = 0
    slave.PWDATA.value = 0

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

    for txn in config["transactions"]:
        master_name = txn["master"]
        index = tuple(txn["index"])
        entry = masters[master_name]

        address = txn["address"] & addr_mask
        write_data = _write_pattern(address, config["data_width"])

        set_value(entry["inputs"]["PREADY"], index, 0)
        set_value(entry["inputs"]["PSLVERR"], index, 0)

        # ------------------------------------------------------------------
        # Setup phase
        # ------------------------------------------------------------------
        slave.PADDR.value = address
        slave.PWDATA.value = write_data
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
        assert get_int(entry["outputs"]["PWRITE"], index) == 1, f"{master_name} should see write direction"
        assert get_int(entry["outputs"]["PADDR"], index) == master_address, (
            f"{master_name} must receive write address"
        )
        assert get_int(entry["outputs"]["PWDATA"], index) == write_data, (
            f"{master_name} must receive write data"
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

        assert int(slave.PREADY.value) == 1, "Slave ready should mirror selected master"
        assert int(slave.PSLVERR.value) == 0, "Write should complete without error"

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
            f"{master_name} should clear write during read"
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

        assert int(slave.PRDATA.value) == read_data, "Read data should propagate back to the slave"
        assert int(slave.PREADY.value) == 1, "Slave ready should acknowledge the read"
        assert int(slave.PSLVERR.value) == 0, "Read should not signal an error"

        slave.PSEL.value = 0
        slave.PENABLE.value = 0
        set_value(entry["inputs"]["PREADY"], index, 0)
        set_value(entry["inputs"]["PRDATA"], index, 0)
        if slave.PCLK is not None:
            await RisingEdge(slave.PCLK)
        else:
            await Timer(1, unit="ns")


@cocotb.test()
async def test_apb3_invalid_address_response(dut) -> None:
    """Ensure invalid addresses yield an error response and no master select."""
    config = load_config()
    is_intf = config.get("cpuif_style") == "interface"
    slave = _Apb3SlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    await start_clock(slave.PCLK)
    if slave.PRESETn is not None:
        slave.PRESETn.value = 1

    slave.PSEL.value = 0
    slave.PENABLE.value = 0
    slave.PWRITE.value = 0
    slave.PADDR.value = 0
    slave.PWDATA.value = 0

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
