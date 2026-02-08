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
