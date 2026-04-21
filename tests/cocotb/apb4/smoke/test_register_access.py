"""APB4 smoke tests generated from SystemRDL sources."""

from __future__ import annotations

from typing import Any

import cocotb
from cocotb.triggers import RisingEdge, Timer

from tests.cocotb_lib.handle_utils import make_signal_handle
from tests.cocotb_lib.protocol_utils import (
    advance,
    all_index_pairs,
    find_invalid_address,
    get_int,
    load_config,
    pick_distinct_pairs,
    set_value,
    start_clock,
)


class _Apb4SlaveShim:
    """Lightweight accessor for the APB4 slave side of the DUT."""

    def __init__(self, dut, *, is_interface: bool = False):
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
    dut, masters_cfg: list[dict[str, Any]], *, is_interface: bool = False
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


def _read_pattern(address: int, width: int) -> int:
    mask = (1 << width) - 1
    return ((address ^ 0xDEAD_BEE5) + width) & mask


def _idle_slave(slave) -> None:
    slave.PSEL.value = 0
    slave.PENABLE.value = 0
    slave.PWRITE.value = 0
    slave.PADDR.value = 0
    slave.PPROT.value = 0
    slave.PWDATA.value = 0
    slave.PSTRB.value = 0


def _idle_masters(masters) -> None:
    for master_name, idx in all_index_pairs(masters):
        entry = masters[master_name]
        set_value(entry["inputs"]["PRDATA"], idx, 0)
        set_value(entry["inputs"]["PREADY"], idx, 0)
        set_value(entry["inputs"]["PSLVERR"], idx, 0)


@cocotb.test()
async def test_apb4_address_decoding(dut) -> None:
    """Drive the APB4 slave interface and verify master fanout across all sampled registers."""
    config = load_config()
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
            assert get_int(other_entry["outputs"]["PADDR"], other_idx) == 0, (
                f"{other_name}{other_idx} must see PADDR gated to 0 while unselected"
            )
            assert get_int(other_entry["outputs"]["PWDATA"], other_idx) == 0, (
                f"{other_name}{other_idx} must see PWDATA gated to 0 while unselected"
            )
            assert get_int(other_entry["outputs"]["PSTRB"], other_idx) == 0, (
                f"{other_name}{other_idx} must see PSTRB gated to 0 while unselected"
            )
            assert get_int(other_entry["outputs"]["PPROT"], other_idx) == 0, (
                f"{other_name}{other_idx} must see PPROT gated to 0 while unselected"
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

        for other_name, other_idx in all_index_pairs(masters):
            if other_name == master_name and other_idx == index:
                continue
            other_entry = masters[other_name]
            assert get_int(other_entry["outputs"]["PENABLE"], other_idx) == 0, (
                f"{other_name}{other_idx} must hold PENABLE low while unselected"
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
            assert get_int(other_entry["outputs"]["PADDR"], other_idx) == 0, (
                f"{other_name}{other_idx} must see PADDR gated to 0 while unselected"
            )
            assert get_int(other_entry["outputs"]["PPROT"], other_idx) == 0, (
                f"{other_name}{other_idx} must see PPROT gated to 0 while unselected"
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

        for other_name, other_idx in all_index_pairs(masters):
            if other_name == master_name and other_idx == index:
                continue
            other_entry = masters[other_name]
            assert get_int(other_entry["outputs"]["PENABLE"], other_idx) == 0, (
                f"{other_name}{other_idx} must hold PENABLE low while unselected"
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
        assert get_int(entry["outputs"]["PENABLE"], idx) == 0, (
            f"{master_name}{idx} must hold PENABLE low for invalid address"
        )

    assert int(slave.PREADY.value) == 1, "Invalid address should still complete the transfer"
    assert int(slave.PSLVERR.value) == 1, "Invalid address should raise PSLVERR"


@cocotb.test()
async def test_apb4_reset_quiescent(dut) -> None:
    """With the slave idle, no master should see PSEL asserted."""
    config = load_config()
    is_intf = config.get("cpuif_style") == "interface"
    slave = _Apb4SlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    await start_clock(slave.PCLK)
    if slave.PRESETn is not None:
        slave.PRESETn.value = 0
    _idle_slave(slave)
    _idle_masters(masters)
    await advance(slave.PCLK)

    for master_name, idx in all_index_pairs(masters):
        entry = masters[master_name]
        assert get_int(entry["outputs"]["PSEL"], idx) == 0, (
            f"{master_name}{idx} must be idle while bus is quiescent"
        )
        assert get_int(entry["outputs"]["PENABLE"], idx) == 0, (
            f"{master_name}{idx} must hold PENABLE low while bus is quiescent"
        )

    if slave.PRESETn is not None:
        slave.PRESETn.value = 1
    await advance(slave.PCLK)

    for master_name, idx in all_index_pairs(masters):
        entry = masters[master_name]
        assert get_int(entry["outputs"]["PSEL"], idx) == 0, (
            f"{master_name}{idx} must remain idle after reset release"
        )


@cocotb.test()
async def test_apb4_setup_access_stability(dut) -> None:
    """Master-side command signals must stay stable across multi-cycle access phases."""
    config = load_config()
    if not config["transactions"]:
        dut._log.warning("No transactions available; skipping stability test")
        return

    is_intf = config.get("cpuif_style") == "interface"
    slave = _Apb4SlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    await start_clock(slave.PCLK)
    if slave.PRESETn is not None:
        slave.PRESETn.value = 1
    _idle_slave(slave)
    _idle_masters(masters)
    await advance(slave.PCLK)

    txn = config["transactions"][0]
    entry = masters[txn["master"]]
    index = tuple(txn["index"])
    address = txn["address"] & ((1 << config["address_width"]) - 1)
    strobe_mask = (1 << config["byte_width"]) - 1
    write_data = _write_pattern(address, config["data_width"])
    master_address = (address - entry["inst_address"]) % entry["inst_size"]

    # Setup phase
    slave.PADDR.value = address
    slave.PWDATA.value = write_data
    slave.PSTRB.value = strobe_mask
    slave.PPROT.value = 0
    slave.PWRITE.value = 1
    slave.PSEL.value = 1
    slave.PENABLE.value = 0
    await advance(slave.PCLK)

    slave.PENABLE.value = 1
    wait_states = 3
    for wait in range(wait_states):
        await advance(slave.PCLK)
        assert get_int(entry["outputs"]["PSEL"], index) == 1, (
            f"PSEL must stay high during wait cycle {wait}"
        )
        assert get_int(entry["outputs"]["PENABLE"], index) == 1, (
            f"PENABLE must stay high during wait cycle {wait}"
        )
        assert get_int(entry["outputs"]["PWRITE"], index) == 1, (
            f"PWRITE must remain stable during wait cycle {wait}"
        )
        assert get_int(entry["outputs"]["PADDR"], index) == master_address, (
            f"PADDR must remain stable during wait cycle {wait}"
        )
        assert get_int(entry["outputs"]["PWDATA"], index) == write_data, (
            f"PWDATA must remain stable during wait cycle {wait}"
        )
        assert get_int(entry["outputs"]["PSTRB"], index) == strobe_mask, (
            f"PSTRB must remain stable during wait cycle {wait}"
        )
        assert int(slave.PREADY.value) == 0, (
            f"Slave PREADY must remain low while master stalls at wait {wait}"
        )

    set_value(entry["inputs"]["PREADY"], index, 1)
    await advance(slave.PCLK)
    assert int(slave.PREADY.value) == 1, "Slave PREADY must follow master once released"
    assert int(slave.PSLVERR.value) == 0, "No slave error expected"


@cocotb.test()
async def test_apb4_back_to_back(dut) -> None:
    """Two successive transfers to distinct masters must each complete cleanly."""
    config = load_config()
    is_intf = config.get("cpuif_style") == "interface"
    slave = _Apb4SlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    pair = pick_distinct_pairs(config["transactions"], count=2)
    if len(pair) < 2:
        dut._log.warning("Need at least two distinct master/index transactions; skipping")
        return

    await start_clock(slave.PCLK)
    if slave.PRESETn is not None:
        slave.PRESETn.value = 1
    _idle_slave(slave)
    _idle_masters(masters)
    await advance(slave.PCLK)

    addr_mask = (1 << config["address_width"]) - 1
    strobe_mask = (1 << config["byte_width"]) - 1

    for txn in pair:
        entry = masters[txn["master"]]
        index = tuple(txn["index"])
        address = txn["address"] & addr_mask
        write_data = _write_pattern(address, config["data_width"])
        master_address = (address - entry["inst_address"]) % entry["inst_size"]

        set_value(entry["inputs"]["PREADY"], index, 1)

        slave.PADDR.value = address
        slave.PWDATA.value = write_data
        slave.PSTRB.value = strobe_mask
        slave.PWRITE.value = 1
        slave.PSEL.value = 1
        slave.PENABLE.value = 0
        await advance(slave.PCLK)
        assert get_int(entry["outputs"]["PSEL"], index) == 1, (
            f"{txn['master']}{index} should be selected in setup"
        )
        assert get_int(entry["outputs"]["PADDR"], index) == master_address, (
            f"{txn['master']}{index} must receive its local address"
        )

        slave.PENABLE.value = 1
        await advance(slave.PCLK)
        assert int(slave.PREADY.value) == 1, "Slave must see PREADY when target is ready"

        for other_name, other_idx in all_index_pairs(masters):
            if other_name == txn["master"] and other_idx == index:
                continue
            other_entry = masters[other_name]
            assert get_int(other_entry["outputs"]["PSEL"], other_idx) == 0, (
                f"{other_name}{other_idx} should remain idle during {txn['label']}"
            )

        set_value(entry["inputs"]["PREADY"], index, 0)
        slave.PSEL.value = 0
        slave.PENABLE.value = 0


@cocotb.test()
async def test_apb4_slave_error_passthrough(dut) -> None:
    """Slave-side PSLVERR from the target master must surface on the bus."""
    config = load_config()
    if not config["transactions"]:
        dut._log.warning("No transactions available; skipping slave error test")
        return

    is_intf = config.get("cpuif_style") == "interface"
    slave = _Apb4SlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    await start_clock(slave.PCLK)
    if slave.PRESETn is not None:
        slave.PRESETn.value = 1
    _idle_slave(slave)
    _idle_masters(masters)
    await advance(slave.PCLK)

    txn = config["transactions"][0]
    entry = masters[txn["master"]]
    index = tuple(txn["index"])
    address = txn["address"] & ((1 << config["address_width"]) - 1)
    strobe_mask = (1 << config["byte_width"]) - 1

    set_value(entry["inputs"]["PREADY"], index, 1)
    set_value(entry["inputs"]["PSLVERR"], index, 1)

    slave.PADDR.value = address
    slave.PWDATA.value = _write_pattern(address, config["data_width"])
    slave.PSTRB.value = strobe_mask
    slave.PWRITE.value = 1
    slave.PSEL.value = 1
    slave.PENABLE.value = 0
    await advance(slave.PCLK)

    slave.PENABLE.value = 1
    await advance(slave.PCLK)

    assert int(slave.PREADY.value) == 1, "Bus PREADY must mirror master PREADY"
    assert int(slave.PSLVERR.value) == 1, "Bus PSLVERR must mirror master PSLVERR"

    for other_name, other_idx in all_index_pairs(masters):
        if other_name == txn["master"] and other_idx == index:
            continue
        other_entry = masters[other_name]
        assert get_int(other_entry["outputs"]["PSEL"], other_idx) == 0, (
            f"{other_name}{other_idx} must remain idle during error response"
        )


@cocotb.test()
async def test_apb4_byte_strobes(dut) -> None:
    """Exercise a spread of PSTRB values and verify the target master sees them intact."""
    config = load_config()
    if not config["transactions"]:
        dut._log.warning("No transactions available; skipping PSTRB sweep")
        return

    byte_width = config["byte_width"]
    full_mask = (1 << byte_width) - 1

    # Build a small set of interesting strobe patterns for this data width.
    strobe_set: list[int] = []
    for base in (0x1, 0x2, 0x4, 0x8, 0xF, 0x5, 0xA):
        masked = base & full_mask
        if masked and masked not in strobe_set:
            strobe_set.append(masked)
    if full_mask not in strobe_set:
        strobe_set.append(full_mask)

    is_intf = config.get("cpuif_style") == "interface"
    slave = _Apb4SlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    await start_clock(slave.PCLK)
    if slave.PRESETn is not None:
        slave.PRESETn.value = 1
    _idle_slave(slave)
    _idle_masters(masters)
    await advance(slave.PCLK)

    txn = config["transactions"][0]
    entry = masters[txn["master"]]
    index = tuple(txn["index"])
    address = txn["address"] & ((1 << config["address_width"]) - 1)
    write_data = _write_pattern(address, config["data_width"])
    master_address = (address - entry["inst_address"]) % entry["inst_size"]

    for strobe in strobe_set:
        set_value(entry["inputs"]["PREADY"], index, 1)
        set_value(entry["inputs"]["PSLVERR"], index, 0)

        slave.PADDR.value = address
        slave.PWDATA.value = write_data
        slave.PSTRB.value = strobe
        slave.PWRITE.value = 1
        slave.PSEL.value = 1
        slave.PENABLE.value = 0
        await advance(slave.PCLK)
        assert get_int(entry["outputs"]["PSTRB"], index) == strobe, (
            f"PSTRB 0x{strobe:x} must reach target master in setup"
        )

        slave.PENABLE.value = 1
        await advance(slave.PCLK)
        assert get_int(entry["outputs"]["PSTRB"], index) == strobe, (
            f"PSTRB 0x{strobe:x} must remain stable in access"
        )
        assert get_int(entry["outputs"]["PADDR"], index) == master_address
        assert get_int(entry["outputs"]["PWDATA"], index) == write_data
        assert int(slave.PREADY.value) == 1

        slave.PSEL.value = 0
        slave.PENABLE.value = 0
        set_value(entry["inputs"]["PREADY"], index, 0)
        await advance(slave.PCLK)
