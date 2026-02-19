"""APB4 cocotb tests driven by Hypothesis-generated random transactions.

This module validates that the bus decoder correctly handles randomly
generated valid and invalid addresses. Transactions are generated at
the pytest runner level using Hypothesis strategies and passed via
the RDL_TEST_CONFIG environment variable.
"""

from __future__ import annotations

from typing import Any

import cocotb
from cocotb.triggers import RisingEdge, Timer

from tests.cocotb_lib.handle_utils import make_signal_handle
from tests.cocotb_lib.protocol_utils import (
    all_index_pairs,
    get_int,
    load_config,
    set_value,
    start_clock,
)


class _Apb4SlaveShim:
    """Lightweight accessor for the APB4 slave side of the DUT."""

    def __init__(self, dut: Any, *, is_interface: bool = False) -> None:
        if is_interface:
            intf = dut.s_apb
            self.PCLK = getattr(intf, "PCLK", None)
            self.PRESETn = getattr(intf, "PRESETn", None)
            self.PSEL = intf.PSEL
            self.PENABLE = intf.PENABLE
            self.PWRITE = intf.PWRITE
            self.PADDR = intf.PADDR
            self.PPROT = intf.PPROT
            self.PWDATA = intf.PWDATA
            self.PSTRB = intf.PSTRB
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
            self.PPROT = getattr(dut, f"{prefix}_PPROT")
            self.PWDATA = getattr(dut, f"{prefix}_PWDATA")
            self.PSTRB = getattr(dut, f"{prefix}_PSTRB")
            self.PRDATA = getattr(dut, f"{prefix}_PRDATA")
            self.PREADY = getattr(dut, f"{prefix}_PREADY")
            self.PSLVERR = getattr(dut, f"{prefix}_PSLVERR")


def _build_master_table(
    dut: Any, masters_cfg: list[dict[str, Any]], *, is_interface: bool = False
) -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for master in masters_cfg:
        port_prefix = master["port_prefix"]
        entry = {
            "port_prefix": port_prefix,
            "indices": [tuple(idx) for idx in master["indices"]] or [tuple()],
            "outputs": {
                "PSEL": make_signal_handle(dut, port_prefix, "PSEL", is_interface=is_interface),
                "PENABLE": make_signal_handle(dut, port_prefix, "PENABLE", is_interface=is_interface),
                "PWRITE": make_signal_handle(dut, port_prefix, "PWRITE", is_interface=is_interface),
                "PADDR": make_signal_handle(dut, port_prefix, "PADDR", is_interface=is_interface),
                "PPROT": make_signal_handle(dut, port_prefix, "PPROT", is_interface=is_interface),
                "PWDATA": make_signal_handle(dut, port_prefix, "PWDATA", is_interface=is_interface),
                "PSTRB": make_signal_handle(dut, port_prefix, "PSTRB", is_interface=is_interface),
            },
            "inputs": {
                "PRDATA": make_signal_handle(dut, port_prefix, "PRDATA", is_interface=is_interface),
                "PREADY": make_signal_handle(dut, port_prefix, "PREADY", is_interface=is_interface),
                "PSLVERR": make_signal_handle(dut, port_prefix, "PSLVERR", is_interface=is_interface),
            },
            "inst_size": master["inst_size"],
            "inst_address": master["inst_address"],
        }
        table[master["inst_name"]] = entry
    return table


def _write_pattern(address: int, width: int) -> int:
    mask = (1 << width) - 1
    return ((address * 0x1021) ^ 0x1357_9BDF) & mask


async def _tick(slave: _Apb4SlaveShim) -> None:
    if slave.PCLK is not None:
        await RisingEdge(slave.PCLK)
    else:
        await Timer(1, unit="ns")


@cocotb.test()
async def test_apb4_hypothesis_valid_transactions(dut: Any) -> None:
    """Drive Hypothesis-generated valid addresses and verify correct master selection."""
    config = load_config()
    is_intf = config.get("cpuif_style") == "interface"
    slave = _Apb4SlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    await start_clock(slave.PCLK)
    if slave.PRESETn is not None:
        slave.PRESETn.value = 1

    # Initialize all signals
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

    await _tick(slave)

    addr_mask = (1 << config["address_width"]) - 1
    strobe_mask = (1 << config["byte_width"]) - 1
    txn_count = 0

    for txn in config["transactions"]:
        master_name = txn["master"]
        index = tuple(txn["index"])
        entry = masters[master_name]

        address = txn["address"] & addr_mask
        write_data = _write_pattern(address, config["data_width"])

        set_value(entry["inputs"]["PREADY"], index, 0)
        set_value(entry["inputs"]["PSLVERR"], index, 0)

        # --- Setup phase ---
        slave.PADDR.value = address
        slave.PWDATA.value = write_data
        slave.PSTRB.value = strobe_mask
        slave.PPROT.value = 0
        slave.PWRITE.value = 1
        slave.PSEL.value = 1
        slave.PENABLE.value = 0

        master_address = (address - entry["inst_address"]) % entry["inst_size"]

        await _tick(slave)

        assert get_int(entry["outputs"]["PSEL"], index) == 1, (
            f"[{txn['label']}] {master_name} must assert PSEL"
        )
        assert get_int(entry["outputs"]["PADDR"], index) == master_address, (
            f"[{txn['label']}] {master_name} address decode mismatch: "
            f"expected 0x{master_address:x}, got 0x{get_int(entry['outputs']['PADDR'], index):x}"
        )
        assert get_int(entry["outputs"]["PWDATA"], index) == write_data, (
            f"[{txn['label']}] {master_name} write data mismatch"
        )

        # Verify isolation: no other master selected
        for other_name, other_idx in all_index_pairs(masters):
            if other_name == master_name and other_idx == index:
                continue
            other_entry = masters[other_name]
            assert get_int(other_entry["outputs"]["PSEL"], other_idx) == 0, (
                f"[{txn['label']}] {other_name}{other_idx} should be idle"
            )

        # --- Access phase ---
        set_value(entry["inputs"]["PREADY"], index, 1)
        slave.PENABLE.value = 1

        await _tick(slave)

        assert int(slave.PREADY.value) == 1, f"[{txn['label']}] PREADY should mirror master"
        assert int(slave.PSLVERR.value) == 0, f"[{txn['label']}] no error expected"

        # Return to idle
        slave.PSEL.value = 0
        slave.PENABLE.value = 0
        slave.PWRITE.value = 0
        set_value(entry["inputs"]["PREADY"], index, 0)
        await _tick(slave)
        txn_count += 1

    dut._log.info(f"Validated {txn_count} Hypothesis-generated transactions")


@cocotb.test()
async def test_apb4_hypothesis_invalid_addresses(dut: Any) -> None:
    """Drive Hypothesis-generated invalid addresses and verify SLVERR response."""
    config = load_config()
    invalid_addresses = config.get("invalid_addresses", [])
    if not invalid_addresses:
        dut._log.warning("No invalid addresses in config; skipping")
        return

    is_intf = config.get("cpuif_style") == "interface"
    slave = _Apb4SlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

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

    await _tick(slave)

    strobe_mask = (1 << config["byte_width"]) - 1
    err_count = 0

    for addr in invalid_addresses:
        # --- Setup phase ---
        slave.PADDR.value = addr
        slave.PWRITE.value = 1
        slave.PWDATA.value = _write_pattern(addr, config["data_width"])
        slave.PSTRB.value = strobe_mask
        slave.PSEL.value = 1
        slave.PENABLE.value = 0

        await _tick(slave)

        # --- Access phase ---
        slave.PENABLE.value = 1

        await _tick(slave)

        # No master should be selected
        for master_name, idx in all_index_pairs(masters):
            entry = masters[master_name]
            assert get_int(entry["outputs"]["PSEL"], idx) == 0, (
                f"Invalid addr 0x{addr:x}: {master_name}{idx} should not be selected"
            )

        assert int(slave.PREADY.value) == 1, (
            f"Invalid addr 0x{addr:x}: transfer should still complete"
        )
        assert int(slave.PSLVERR.value) == 1, (
            f"Invalid addr 0x{addr:x}: PSLVERR should be asserted"
        )

        # Return to idle
        slave.PSEL.value = 0
        slave.PENABLE.value = 0
        await _tick(slave)
        err_count += 1

    dut._log.info(f"Validated {err_count} Hypothesis-generated invalid addresses")
