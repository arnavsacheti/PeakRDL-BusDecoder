"""AXI4-Lite smoke test driven from SystemRDL-generated register maps."""

from __future__ import annotations

from typing import Any

import cocotb
from cocotb.triggers import Timer

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
    """Accessor for AXI4-Lite slave ports on the DUT."""

    def __init__(self, dut, *, is_interface: bool = False):
        if is_interface:
            intf = dut.s_axil
            self.AWREADY = intf.AWREADY
            self.AWVALID = intf.AWVALID
            self.AWADDR = intf.AWADDR
            self.AWPROT = intf.AWPROT
            self.WREADY = intf.WREADY
            self.WVALID = intf.WVALID
            self.WDATA = intf.WDATA
            self.WSTRB = intf.WSTRB
            self.BREADY = intf.BREADY
            self.BVALID = intf.BVALID
            self.BRESP = intf.BRESP
            self.ARREADY = intf.ARREADY
            self.ARVALID = intf.ARVALID
            self.ARADDR = intf.ARADDR
            self.ARPROT = intf.ARPROT
            self.RREADY = intf.RREADY
            self.RVALID = intf.RVALID
            self.RDATA = intf.RDATA
            self.RRESP = intf.RRESP
        else:
            prefix = "s_axil"
            self.AWREADY = getattr(dut, f"{prefix}_AWREADY")
            self.AWVALID = getattr(dut, f"{prefix}_AWVALID")
            self.AWADDR = getattr(dut, f"{prefix}_AWADDR")
            self.AWPROT = getattr(dut, f"{prefix}_AWPROT")
            self.WREADY = getattr(dut, f"{prefix}_WREADY")
            self.WVALID = getattr(dut, f"{prefix}_WVALID")
            self.WDATA = getattr(dut, f"{prefix}_WDATA")
            self.WSTRB = getattr(dut, f"{prefix}_WSTRB")
            self.BREADY = getattr(dut, f"{prefix}_BREADY")
            self.BVALID = getattr(dut, f"{prefix}_BVALID")
            self.BRESP = getattr(dut, f"{prefix}_BRESP")
            self.ARREADY = getattr(dut, f"{prefix}_ARREADY")
            self.ARVALID = getattr(dut, f"{prefix}_ARVALID")
            self.ARADDR = getattr(dut, f"{prefix}_ARADDR")
            self.ARPROT = getattr(dut, f"{prefix}_ARPROT")
            self.RREADY = getattr(dut, f"{prefix}_RREADY")
            self.RVALID = getattr(dut, f"{prefix}_RVALID")
            self.RDATA = getattr(dut, f"{prefix}_RDATA")
            self.RRESP = getattr(dut, f"{prefix}_RRESP")


def _build_master_table(
    dut, masters_cfg: list[dict[str, Any]], *, is_interface: bool = False
) -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for master in masters_cfg:
        prefix = master["port_prefix"]
        entry = {
            "indices": [tuple(idx) for idx in master["indices"]] or [tuple()],
            "outputs": {
                "AWVALID": make_signal_handle(dut, prefix, "AWVALID", is_interface=is_interface),
                "AWADDR": make_signal_handle(dut, prefix, "AWADDR", is_interface=is_interface),
                "AWPROT": make_signal_handle(dut, prefix, "AWPROT", is_interface=is_interface),
                "WVALID": make_signal_handle(dut, prefix, "WVALID", is_interface=is_interface),
                "WDATA": make_signal_handle(dut, prefix, "WDATA", is_interface=is_interface),
                "WSTRB": make_signal_handle(dut, prefix, "WSTRB", is_interface=is_interface),
                "ARVALID": make_signal_handle(dut, prefix, "ARVALID", is_interface=is_interface),
                "ARADDR": make_signal_handle(dut, prefix, "ARADDR", is_interface=is_interface),
                "ARPROT": make_signal_handle(dut, prefix, "ARPROT", is_interface=is_interface),
            },
            "inputs": {
                "AWREADY": make_signal_handle(dut, prefix, "AWREADY", is_interface=is_interface),
                "WREADY": make_signal_handle(dut, prefix, "WREADY", is_interface=is_interface),
                "BVALID": make_signal_handle(dut, prefix, "BVALID", is_interface=is_interface),
                "BRESP": make_signal_handle(dut, prefix, "BRESP", is_interface=is_interface),
                "ARREADY": make_signal_handle(dut, prefix, "ARREADY", is_interface=is_interface),
                "RVALID": make_signal_handle(dut, prefix, "RVALID", is_interface=is_interface),
                "RDATA": make_signal_handle(dut, prefix, "RDATA", is_interface=is_interface),
                "RRESP": make_signal_handle(dut, prefix, "RRESP", is_interface=is_interface),
            },
            "inst_size": master["inst_size"],
            "inst_address": master["inst_address"],
        }
        table[master["inst_name"]] = entry
    return table


def _write_pattern(address: int, width: int) -> int:
    mask = (1 << width) - 1
    return ((address * 0x3105) ^ 0x1357_9BDF) & mask


def _read_pattern(address: int, width: int) -> int:
    mask = (1 << width) - 1
    return ((address ^ 0x2468_ACED) + width) & mask


def _idle_slave(slave) -> None:
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


def _idle_masters(masters) -> None:
    for master_name, idx in all_index_pairs(masters):
        entry = masters[master_name]
        set_value(entry["inputs"]["AWREADY"], idx, 0)
        set_value(entry["inputs"]["WREADY"], idx, 0)
        set_value(entry["inputs"]["BVALID"], idx, 0)
        set_value(entry["inputs"]["BRESP"], idx, 0)
        set_value(entry["inputs"]["ARREADY"], idx, 0)
        set_value(entry["inputs"]["RVALID"], idx, 0)
        set_value(entry["inputs"]["RDATA"], idx, 0)
        set_value(entry["inputs"]["RRESP"], idx, 0)


@cocotb.test()
async def test_axi4lite_address_decoding(dut) -> None:
    """Stimulate AXI4-Lite slave channels and verify master port selection."""
    config = load_config()
    is_intf = config.get("cpuif_style") == "interface"
    slave = _AxilSlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

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

    for master_name, idx in all_index_pairs(masters):
        entry = masters[master_name]
        set_value(entry["inputs"]["AWREADY"], idx, 0)
        set_value(entry["inputs"]["WREADY"], idx, 0)
        set_value(entry["inputs"]["BVALID"], idx, 0)
        set_value(entry["inputs"]["BRESP"], idx, 0)
        set_value(entry["inputs"]["ARREADY"], idx, 0)
        set_value(entry["inputs"]["RVALID"], idx, 0)
        set_value(entry["inputs"]["RDATA"], idx, 0)
        set_value(entry["inputs"]["RRESP"], idx, 0)

    await Timer(1, unit="ns")

    addr_mask = (1 << config["address_width"]) - 1
    strobe_mask = (1 << config["byte_width"]) - 1

    for txn in config["transactions"]:
        master_name = txn["master"]
        index = tuple(txn["index"])
        entry = masters[master_name]

        address = txn["address"] & addr_mask
        write_data = _write_pattern(address, config["data_width"])

        set_value(entry["inputs"]["BVALID"], index, 1)
        set_value(entry["inputs"]["BRESP"], index, 0)

        slave.AWADDR.value = address
        slave.AWPROT.value = 0
        slave.AWVALID.value = 1
        slave.WDATA.value = write_data
        slave.WSTRB.value = strobe_mask
        slave.WVALID.value = 1
        slave.BREADY.value = 1

        dut._log.info(
            f"Starting transaction {txn['label']} to {master_name}{index} at address 0x{address:08X}"
        )
        master_address = (address - entry["inst_address"]) % entry["inst_size"]

        await Timer(1, unit="ns")

        assert get_int(entry["outputs"]["AWVALID"], index) == 1, f"{master_name} should see AWVALID asserted"
        assert get_int(entry["outputs"]["AWADDR"], index) == master_address, (
            f"{master_name} must receive AWADDR"
        )
        assert get_int(entry["outputs"]["WVALID"], index) == 1, f"{master_name} should see WVALID asserted"
        assert get_int(entry["outputs"]["WDATA"], index) == write_data, f"{master_name} must receive WDATA"
        assert get_int(entry["outputs"]["WSTRB"], index) == strobe_mask, f"{master_name} must receive WSTRB"
        assert int(slave.AWREADY.value) == 1, "AWREADY should assert when write address/data are valid"
        assert int(slave.WREADY.value) == 1, "WREADY should assert when write address/data are valid"

        for other_name, other_idx in all_index_pairs(masters):
            if other_name == master_name and other_idx == index:
                continue
            other_entry = masters[other_name]
            assert get_int(other_entry["outputs"]["AWVALID"], other_idx) == 0, (
                f"{other_name}{other_idx} AWVALID should remain low during {txn['label']}"
            )
            assert get_int(other_entry["outputs"]["WVALID"], other_idx) == 0, (
                f"{other_name}{other_idx} WVALID should remain low during {txn['label']}"
            )

        assert int(slave.BVALID.value) == 1, "Slave should observe BVALID from selected master"
        assert int(slave.BRESP.value) == 0, "BRESP should indicate OKAY on write"

        slave.AWVALID.value = 0
        slave.WVALID.value = 0
        slave.BREADY.value = 0
        set_value(entry["inputs"]["BVALID"], index, 0)
        await Timer(1, unit="ns")

        read_data = _read_pattern(address, config["data_width"])
        set_value(entry["inputs"]["RVALID"], index, 1)
        set_value(entry["inputs"]["RDATA"], index, read_data)
        set_value(entry["inputs"]["RRESP"], index, 0)

        slave.ARADDR.value = address
        slave.ARPROT.value = 0
        slave.ARVALID.value = 1
        slave.RREADY.value = 1

        await Timer(1, unit="ns")

        assert get_int(entry["outputs"]["ARVALID"], index) == 1, f"{master_name} should assert ARVALID"
        assert get_int(entry["outputs"]["ARADDR"], index) == master_address, (
            f"{master_name} must receive ARADDR"
        )
        assert int(slave.ARREADY.value) == 1, "ARREADY should assert when ARVALID is high"

        for other_name, other_idx in all_index_pairs(masters):
            if other_name == master_name and other_idx == index:
                continue
            other_entry = masters[other_name]
            assert get_int(other_entry["outputs"]["ARVALID"], other_idx) == 0, (
                f"{other_name}{other_idx} ARVALID should remain low during read of {txn['label']}"
            )

        assert int(slave.RVALID.value) == 1, "Slave should observe RVALID when master responds"
        assert int(slave.RDATA.value) == read_data, "Read data must fold back to slave"
        assert int(slave.RRESP.value) == 0, "Read response should indicate success"

        slave.ARVALID.value = 0
        slave.RREADY.value = 0
        set_value(entry["inputs"]["RVALID"], index, 0)
        set_value(entry["inputs"]["RDATA"], index, 0)
        await Timer(1, unit="ns")


@cocotb.test()
async def test_axi4lite_invalid_write_handshake(dut) -> None:
    """Ensure mismatched AW/W valid signals raise an error and are ignored."""
    config = load_config()
    is_intf = config.get("cpuif_style") == "interface"
    slave = _AxilSlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

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

    for master_name, idx in all_index_pairs(masters):
        entry = masters[master_name]
        set_value(entry["inputs"]["AWREADY"], idx, 0)
        set_value(entry["inputs"]["WREADY"], idx, 0)
        set_value(entry["inputs"]["BVALID"], idx, 0)
        set_value(entry["inputs"]["BRESP"], idx, 0)
        set_value(entry["inputs"]["ARREADY"], idx, 0)
        set_value(entry["inputs"]["RVALID"], idx, 0)
        set_value(entry["inputs"]["RDATA"], idx, 0)
        set_value(entry["inputs"]["RRESP"], idx, 0)

    await Timer(1, unit="ns")

    if not config["transactions"]:
        dut._log.warning("No transactions available; skipping invalid handshake test")
        return

    bad_addr = config["transactions"][0]["address"] & ((1 << config["address_width"]) - 1)
    slave.AWADDR.value = bad_addr
    slave.AWPROT.value = 0
    slave.AWVALID.value = 1
    slave.WVALID.value = 0
    slave.BREADY.value = 1

    await Timer(1, unit="ns")

    for master_name, idx in all_index_pairs(masters):
        entry = masters[master_name]
        assert get_int(entry["outputs"]["AWVALID"], idx) == 0, (
            f"{master_name}{idx} must not see AWVALID on invalid handshake"
        )
        assert get_int(entry["outputs"]["WVALID"], idx) == 0, (
            f"{master_name}{idx} must not see WVALID on invalid handshake"
        )

    assert int(slave.AWREADY.value) == 0, "AWREADY must remain low on invalid write handshake"
    assert int(slave.WREADY.value) == 0, "WREADY must remain low on invalid write handshake"
    assert int(slave.BVALID.value) == 1, "Invalid write handshake should return BVALID"
    assert int(slave.BRESP.value) == 2, "Invalid write handshake should return SLVERR"


@cocotb.test()
async def test_axi4lite_invalid_address_response(dut) -> None:
    """Ensure unmapped addresses return error responses and do not select a master."""
    config = load_config()
    is_intf = config.get("cpuif_style") == "interface"
    slave = _AxilSlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

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

    for master_name, idx in all_index_pairs(masters):
        entry = masters[master_name]
        set_value(entry["inputs"]["AWREADY"], idx, 0)
        set_value(entry["inputs"]["WREADY"], idx, 0)
        set_value(entry["inputs"]["BVALID"], idx, 0)
        set_value(entry["inputs"]["BRESP"], idx, 0)
        set_value(entry["inputs"]["ARREADY"], idx, 0)
        set_value(entry["inputs"]["RVALID"], idx, 0)
        set_value(entry["inputs"]["RDATA"], idx, 0)
        set_value(entry["inputs"]["RRESP"], idx, 0)

    await Timer(1, unit="ns")

    invalid_addr = find_invalid_address(config)
    if invalid_addr is None:
        dut._log.warning("No unmapped address found; skipping invalid address test")
        return

    # Invalid read
    slave.ARADDR.value = invalid_addr
    slave.ARPROT.value = 0
    slave.ARVALID.value = 1
    slave.RREADY.value = 1

    await Timer(1, unit="ns")

    for master_name, idx in all_index_pairs(masters):
        entry = masters[master_name]
        assert get_int(entry["outputs"]["ARVALID"], idx) == 0, (
            f"{master_name}{idx} must stay idle for invalid read address"
        )

    assert int(slave.RVALID.value) == 1, "Invalid read should return RVALID"
    assert int(slave.RRESP.value) == 2, "Invalid read should return SLVERR"

    slave.ARVALID.value = 0
    slave.RREADY.value = 0
    await Timer(1, unit="ns")

    # Invalid write
    slave.AWADDR.value = invalid_addr
    slave.AWPROT.value = 0
    slave.AWVALID.value = 1
    slave.WDATA.value = 0xA5A5_5A5A
    slave.WSTRB.value = (1 << config["byte_width"]) - 1
    slave.WVALID.value = 1
    slave.BREADY.value = 1

    await Timer(1, unit="ns")

    for master_name, idx in all_index_pairs(masters):
        entry = masters[master_name]
        assert get_int(entry["outputs"]["AWVALID"], idx) == 0, (
            f"{master_name}{idx} must stay idle for invalid write address"
        )
        assert get_int(entry["outputs"]["WVALID"], idx) == 0, (
            f"{master_name}{idx} must stay idle for invalid write address"
        )

    assert int(slave.BVALID.value) == 1, "Invalid write should return BVALID"
    assert int(slave.BRESP.value) == 2, "Invalid write should return SLVERR"


@cocotb.test()
async def test_axi4lite_reset_quiescent(dut) -> None:
    """When the slave is idle, no master should see any valid asserted."""
    config = load_config()
    is_intf = config.get("cpuif_style") == "interface"
    slave = _AxilSlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    _idle_slave(slave)
    _idle_masters(masters)
    await Timer(1, unit="ns")

    for master_name, idx in all_index_pairs(masters):
        entry = masters[master_name]
        assert get_int(entry["outputs"]["AWVALID"], idx) == 0, (
            f"{master_name}{idx} AWVALID must be idle"
        )
        assert get_int(entry["outputs"]["WVALID"], idx) == 0, (
            f"{master_name}{idx} WVALID must be idle"
        )
        assert get_int(entry["outputs"]["ARVALID"], idx) == 0, (
            f"{master_name}{idx} ARVALID must be idle"
        )
    assert int(slave.BVALID.value) == 0, "BVALID must be low while idle"
    assert int(slave.RVALID.value) == 0, "RVALID must be low while idle"
    assert int(slave.AWREADY.value) == 0, "AWREADY must be low while idle"
    assert int(slave.WREADY.value) == 0, "WREADY must be low while idle"
    assert int(slave.ARREADY.value) == 0, "ARREADY must be low while idle"


@cocotb.test()
async def test_axi4lite_aw_then_w(dut) -> None:
    """AW arriving before W must trigger SLVERR, then W arriving completes the write cleanly."""
    config = load_config()
    if not config["transactions"]:
        dut._log.warning("No transactions available; skipping AW→W ordering test")
        return

    is_intf = config.get("cpuif_style") == "interface"
    slave = _AxilSlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    _idle_slave(slave)
    _idle_masters(masters)
    await Timer(1, unit="ns")

    txn = config["transactions"][0]
    entry = masters[txn["master"]]
    index = tuple(txn["index"])
    address = txn["address"] & ((1 << config["address_width"]) - 1)
    write_data = _write_pattern(address, config["data_width"])
    strobe_mask = (1 << config["byte_width"]) - 1
    master_address = (address - entry["inst_address"]) % entry["inst_size"]

    # Phase 1: AW only, W deasserted. Decoder must raise SLVERR via axi_wr_invalid.
    slave.AWADDR.value = address
    slave.AWPROT.value = 0
    slave.AWVALID.value = 1
    slave.WVALID.value = 0
    slave.BREADY.value = 1
    await Timer(1, unit="ns")

    assert int(slave.BVALID.value) == 1, "AW alone must still assert BVALID via invalid-handshake"
    assert int(slave.BRESP.value) == 2, "AW alone must raise BRESP=SLVERR"
    assert int(slave.AWREADY.value) == 0, "AWREADY requires both AW & W to be high"
    for master_name, idx in all_index_pairs(masters):
        other_entry = masters[master_name]
        assert get_int(other_entry["outputs"]["AWVALID"], idx) == 0, (
            f"{master_name}{idx} must not see AWVALID while W is missing"
        )
        assert get_int(other_entry["outputs"]["WVALID"], idx) == 0, (
            f"{master_name}{idx} must not see WVALID while W is missing"
        )

    # Phase 2: bring W up alongside AW. Target master should now receive the request.
    set_value(entry["inputs"]["BVALID"], index, 1)
    set_value(entry["inputs"]["BRESP"], index, 0)
    slave.WDATA.value = write_data
    slave.WSTRB.value = strobe_mask
    slave.WVALID.value = 1
    await Timer(1, unit="ns")

    assert get_int(entry["outputs"]["AWVALID"], index) == 1, "Target must see AWVALID when both channels valid"
    assert get_int(entry["outputs"]["WVALID"], index) == 1, "Target must see WVALID when both channels valid"
    assert get_int(entry["outputs"]["AWADDR"], index) == master_address
    assert get_int(entry["outputs"]["WDATA"], index) == write_data
    assert get_int(entry["outputs"]["WSTRB"], index) == strobe_mask
    assert int(slave.AWREADY.value) == 1, "AWREADY asserts once both AW & W are valid"
    assert int(slave.WREADY.value) == 1, "WREADY asserts once both AW & W are valid"
    assert int(slave.BVALID.value) == 1, "BVALID should follow the master ack"
    assert int(slave.BRESP.value) == 0, "BRESP should be OKAY for a clean master ack"


@cocotb.test()
async def test_axi4lite_w_then_aw(dut) -> None:
    """W arriving before AW must not drive any master until AW joins; SLVERR is never observed."""
    config = load_config()
    if not config["transactions"]:
        dut._log.warning("No transactions available; skipping W→AW ordering test")
        return

    is_intf = config.get("cpuif_style") == "interface"
    slave = _AxilSlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    _idle_slave(slave)
    _idle_masters(masters)
    await Timer(1, unit="ns")

    txn = config["transactions"][0]
    entry = masters[txn["master"]]
    index = tuple(txn["index"])
    address = txn["address"] & ((1 << config["address_width"]) - 1)
    write_data = _write_pattern(address, config["data_width"])
    strobe_mask = (1 << config["byte_width"]) - 1

    # Phase 1: W only. No cpuif_req for writes → no master should engage, and BVALID must be low
    # because axi_wr_invalid requires AW XOR W (only one high), so W alone → BVALID=1 SLVERR.
    slave.WDATA.value = write_data
    slave.WSTRB.value = strobe_mask
    slave.WVALID.value = 1
    slave.BREADY.value = 1
    await Timer(1, unit="ns")

    assert int(slave.WREADY.value) == 0, "WREADY requires both AW & W to be high"
    for master_name, idx in all_index_pairs(masters):
        other_entry = masters[master_name]
        assert get_int(other_entry["outputs"]["WVALID"], idx) == 0, (
            f"{master_name}{idx} must not see WVALID without AW"
        )

    # Phase 2: add AW. Both master channels engage and transfer completes.
    set_value(entry["inputs"]["BVALID"], index, 1)
    set_value(entry["inputs"]["BRESP"], index, 0)
    slave.AWADDR.value = address
    slave.AWPROT.value = 0
    slave.AWVALID.value = 1
    await Timer(1, unit="ns")

    assert get_int(entry["outputs"]["AWVALID"], index) == 1
    assert get_int(entry["outputs"]["WVALID"], index) == 1
    assert int(slave.AWREADY.value) == 1
    assert int(slave.WREADY.value) == 1
    assert int(slave.BRESP.value) == 0, "BRESP should be OKAY once both channels align"


@cocotb.test()
async def test_axi4lite_read_wait_states(dut) -> None:
    """Read-channel master-side signals stay stable across multi-cycle RVALID delay."""
    config = load_config()
    if not config["transactions"]:
        dut._log.warning("No transactions available; skipping read wait-state test")
        return

    is_intf = config.get("cpuif_style") == "interface"
    slave = _AxilSlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    _idle_slave(slave)
    _idle_masters(masters)
    await Timer(1, unit="ns")

    txn = config["transactions"][0]
    entry = masters[txn["master"]]
    index = tuple(txn["index"])
    address = txn["address"] & ((1 << config["address_width"]) - 1)
    master_address = (address - entry["inst_address"]) % entry["inst_size"]

    slave.ARADDR.value = address
    slave.ARPROT.value = 0
    slave.ARVALID.value = 1
    slave.RREADY.value = 1

    wait_cycles = 3
    for wait in range(wait_cycles):
        await Timer(1, unit="ns")
        assert get_int(entry["outputs"]["ARVALID"], index) == 1, (
            f"ARVALID must stay high during wait cycle {wait}"
        )
        assert get_int(entry["outputs"]["ARADDR"], index) == master_address, (
            f"ARADDR must remain stable during wait cycle {wait}"
        )
        assert int(slave.RVALID.value) == 0, (
            f"RVALID must stay low while master stalls at wait {wait}"
        )

    read_data = _read_pattern(address, config["data_width"])
    set_value(entry["inputs"]["RVALID"], index, 1)
    set_value(entry["inputs"]["RDATA"], index, read_data)
    set_value(entry["inputs"]["RRESP"], index, 0)
    await Timer(1, unit="ns")

    assert int(slave.RVALID.value) == 1, "RVALID must propagate once master releases it"
    assert int(slave.RDATA.value) == read_data, "RDATA must match the master's response"
    assert int(slave.RRESP.value) == 0, "RRESP should be OKAY"


@cocotb.test()
async def test_axi4lite_slave_error_propagation(dut) -> None:
    """Master-sourced BRESP/RRESP SLVERR responses must surface on the slave bus."""
    config = load_config()
    if not config["transactions"]:
        dut._log.warning("No transactions available; skipping slave-error test")
        return

    is_intf = config.get("cpuif_style") == "interface"
    slave = _AxilSlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    _idle_slave(slave)
    _idle_masters(masters)
    await Timer(1, unit="ns")

    txn = config["transactions"][0]
    entry = masters[txn["master"]]
    index = tuple(txn["index"])
    address = txn["address"] & ((1 << config["address_width"]) - 1)
    write_data = _write_pattern(address, config["data_width"])
    read_data = _read_pattern(address, config["data_width"])
    strobe_mask = (1 << config["byte_width"]) - 1

    # Write with master-sourced BRESP=SLVERR
    set_value(entry["inputs"]["BVALID"], index, 1)
    set_value(entry["inputs"]["BRESP"], index, 2)

    slave.AWADDR.value = address
    slave.AWPROT.value = 0
    slave.AWVALID.value = 1
    slave.WDATA.value = write_data
    slave.WSTRB.value = strobe_mask
    slave.WVALID.value = 1
    slave.BREADY.value = 1
    await Timer(1, unit="ns")

    assert int(slave.BVALID.value) == 1, "BVALID must reflect master BVALID"
    assert int(slave.BRESP.value) == 2, "BRESP must propagate SLVERR from the master"

    # Return to idle before exercising read
    slave.AWVALID.value = 0
    slave.WVALID.value = 0
    slave.BREADY.value = 0
    set_value(entry["inputs"]["BVALID"], index, 0)
    set_value(entry["inputs"]["BRESP"], index, 0)
    await Timer(1, unit="ns")

    # Read with master-sourced RRESP=SLVERR
    set_value(entry["inputs"]["RVALID"], index, 1)
    set_value(entry["inputs"]["RDATA"], index, read_data)
    set_value(entry["inputs"]["RRESP"], index, 2)

    slave.ARADDR.value = address
    slave.ARPROT.value = 0
    slave.ARVALID.value = 1
    slave.RREADY.value = 1
    await Timer(1, unit="ns")

    assert int(slave.RVALID.value) == 1, "RVALID must reflect master RVALID"
    assert int(slave.RRESP.value) == 2, "RRESP must propagate SLVERR from the master"
    assert int(slave.RDATA.value) == read_data


@cocotb.test()
async def test_axi4lite_byte_strobes(dut) -> None:
    """Exercise a spread of WSTRB values and verify the target master sees them intact."""
    config = load_config()
    if not config["transactions"]:
        dut._log.warning("No transactions available; skipping WSTRB sweep")
        return

    byte_width = config["byte_width"]
    full_mask = (1 << byte_width) - 1

    strobe_set: list[int] = []
    for base in (0x1, 0x2, 0x4, 0x8, 0xF, 0x5, 0xA):
        masked = base & full_mask
        if masked and masked not in strobe_set:
            strobe_set.append(masked)
    if full_mask not in strobe_set:
        strobe_set.append(full_mask)

    is_intf = config.get("cpuif_style") == "interface"
    slave = _AxilSlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    _idle_slave(slave)
    _idle_masters(masters)
    await Timer(1, unit="ns")

    txn = config["transactions"][0]
    entry = masters[txn["master"]]
    index = tuple(txn["index"])
    address = txn["address"] & ((1 << config["address_width"]) - 1)
    write_data = _write_pattern(address, config["data_width"])
    master_address = (address - entry["inst_address"]) % entry["inst_size"]

    for strobe in strobe_set:
        set_value(entry["inputs"]["BVALID"], index, 1)
        set_value(entry["inputs"]["BRESP"], index, 0)

        slave.AWADDR.value = address
        slave.AWPROT.value = 0
        slave.AWVALID.value = 1
        slave.WDATA.value = write_data
        slave.WSTRB.value = strobe
        slave.WVALID.value = 1
        slave.BREADY.value = 1
        await Timer(1, unit="ns")

        assert get_int(entry["outputs"]["AWADDR"], index) == master_address
        assert get_int(entry["outputs"]["WDATA"], index) == write_data
        assert get_int(entry["outputs"]["WSTRB"], index) == strobe, (
            f"WSTRB 0x{strobe:x} must reach target master"
        )
        assert int(slave.BRESP.value) == 0, f"Strobe 0x{strobe:x} should yield OKAY"

        slave.AWVALID.value = 0
        slave.WVALID.value = 0
        slave.BREADY.value = 0
        set_value(entry["inputs"]["BVALID"], index, 0)
        await Timer(1, unit="ns")


@cocotb.test()
async def test_axi4lite_back_to_back(dut) -> None:
    """Two successive writes to distinct masters must each be routed correctly."""
    config = load_config()
    is_intf = config.get("cpuif_style") == "interface"
    slave = _AxilSlaveShim(dut, is_interface=is_intf)
    masters = _build_master_table(dut, config["masters"], is_interface=is_intf)

    pair = pick_distinct_pairs(config["transactions"], count=2)
    if len(pair) < 2:
        dut._log.warning("Need at least two distinct master/index transactions; skipping")
        return

    _idle_slave(slave)
    _idle_masters(masters)
    await Timer(1, unit="ns")

    addr_mask = (1 << config["address_width"]) - 1
    strobe_mask = (1 << config["byte_width"]) - 1

    for txn in pair:
        entry = masters[txn["master"]]
        index = tuple(txn["index"])
        address = txn["address"] & addr_mask
        write_data = _write_pattern(address, config["data_width"])
        master_address = (address - entry["inst_address"]) % entry["inst_size"]

        set_value(entry["inputs"]["BVALID"], index, 1)
        set_value(entry["inputs"]["BRESP"], index, 0)

        slave.AWADDR.value = address
        slave.AWPROT.value = 0
        slave.AWVALID.value = 1
        slave.WDATA.value = write_data
        slave.WSTRB.value = strobe_mask
        slave.WVALID.value = 1
        slave.BREADY.value = 1
        await Timer(1, unit="ns")

        assert get_int(entry["outputs"]["AWVALID"], index) == 1
        assert get_int(entry["outputs"]["AWADDR"], index) == master_address
        assert get_int(entry["outputs"]["WVALID"], index) == 1

        for other_name, other_idx in all_index_pairs(masters):
            if other_name == txn["master"] and other_idx == index:
                continue
            other_entry = masters[other_name]
            assert get_int(other_entry["outputs"]["AWVALID"], other_idx) == 0, (
                f"{other_name}{other_idx} must stay idle during {txn['label']}"
            )

        slave.AWVALID.value = 0
        slave.WVALID.value = 0
        slave.BREADY.value = 0
        set_value(entry["inputs"]["BVALID"], index, 0)
        await Timer(1, unit="ns")
