"""AXI4-Lite smoke test driven from SystemRDL-generated register maps."""

from __future__ import annotations

import json
import os
from typing import Any, Iterable

import cocotb
from cocotb.triggers import Timer

from tests.cocotb_lib.handle_utils import SignalHandle, resolve_handle

class _AxilSlaveShim:
    """Accessor for AXI4-Lite slave ports on the DUT."""

    def __init__(self, dut):
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


def _load_config() -> dict[str, Any]:
    payload = os.environ.get("RDL_TEST_CONFIG")
    if payload is None:
        raise RuntimeError("RDL_TEST_CONFIG environment variable was not provided")
    return json.loads(payload)


def _resolve(handle, indices: Iterable[int]):
    return resolve_handle(handle, indices)


def _set_value(handle, indices: Iterable[int], value: int) -> None:
    _resolve(handle, indices).value = value


def _get_int(handle, indices: Iterable[int]) -> int:
    return int(_resolve(handle, indices).value)


def _build_master_table(dut, masters_cfg: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for master in masters_cfg:
        prefix = master["port_prefix"]
        entry = {
            "indices": [tuple(idx) for idx in master["indices"]] or [tuple()],
            "outputs": {
                "AWVALID": SignalHandle(dut, f"{prefix}_AWVALID"),
                "AWADDR": SignalHandle(dut, f"{prefix}_AWADDR"),
                "AWPROT": SignalHandle(dut, f"{prefix}_AWPROT"),
                "WVALID": SignalHandle(dut, f"{prefix}_WVALID"),
                "WDATA": SignalHandle(dut, f"{prefix}_WDATA"),
                "WSTRB": SignalHandle(dut, f"{prefix}_WSTRB"),
                "ARVALID": SignalHandle(dut, f"{prefix}_ARVALID"),
                "ARADDR": SignalHandle(dut, f"{prefix}_ARADDR"),
                "ARPROT": SignalHandle(dut, f"{prefix}_ARPROT"),
            },
            "inputs": {
                "AWREADY": SignalHandle(dut, f"{prefix}_AWREADY"),
                "WREADY": SignalHandle(dut, f"{prefix}_WREADY"),
                "BVALID": SignalHandle(dut, f"{prefix}_BVALID"),
                "BRESP": SignalHandle(dut, f"{prefix}_BRESP"),
                "ARREADY": SignalHandle(dut, f"{prefix}_ARREADY"),
                "RVALID": SignalHandle(dut, f"{prefix}_RVALID"),
                "RDATA": SignalHandle(dut, f"{prefix}_RDATA"),
                "RRESP": SignalHandle(dut, f"{prefix}_RRESP"),
            },
        }
        table[master["inst_name"]] = entry
    return table


def _all_index_pairs(table: dict[str, dict[str, Any]]):
    for name, entry in table.items():
        for idx in entry["indices"]:
            yield name, idx


def _write_pattern(address: int, width: int) -> int:
    mask = (1 << width) - 1
    return ((address * 0x3105) ^ 0x1357_9BDF) & mask


def _read_pattern(address: int, width: int) -> int:
    mask = (1 << width) - 1
    return ((address ^ 0x2468_ACED) + width) & mask


@cocotb.test()
async def test_axi4lite_address_decoding(dut) -> None:
    """Stimulate AXI4-Lite slave channels and verify master port selection."""
    config = _load_config()
    slave = _AxilSlaveShim(dut)
    masters = _build_master_table(dut, config["masters"])

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

    for master_name, idx in _all_index_pairs(masters):
        entry = masters[master_name]
        _set_value(entry["inputs"]["AWREADY"], idx, 0)
        _set_value(entry["inputs"]["WREADY"], idx, 0)
        _set_value(entry["inputs"]["BVALID"], idx, 0)
        _set_value(entry["inputs"]["BRESP"], idx, 0)
        _set_value(entry["inputs"]["ARREADY"], idx, 0)
        _set_value(entry["inputs"]["RVALID"], idx, 0)
        _set_value(entry["inputs"]["RDATA"], idx, 0)
        _set_value(entry["inputs"]["RRESP"], idx, 0)

    await Timer(1, units="ns")

    addr_mask = (1 << config["address_width"]) - 1
    strobe_mask = (1 << config["byte_width"]) - 1

    for txn in config["transactions"]:
        master_name = txn["master"]
        index = tuple(txn["index"])
        entry = masters[master_name]

        address = txn["address"] & addr_mask
        write_data = _write_pattern(address, config["data_width"])

        slave.AWADDR.value = address
        slave.AWPROT.value = 0
        slave.AWVALID.value = 1
        slave.WDATA.value = write_data
        slave.WSTRB.value = strobe_mask
        slave.WVALID.value = 1
        slave.BREADY.value = 1

        await Timer(1, units="ns")

        assert _get_int(entry["outputs"]["AWVALID"], index) == 1, f"{master_name} should see AWVALID asserted"
        assert _get_int(entry["outputs"]["AWADDR"], index) == address, f"{master_name} must receive AWADDR"
        assert _get_int(entry["outputs"]["WVALID"], index) == 1, f"{master_name} should see WVALID asserted"
        assert _get_int(entry["outputs"]["WDATA"], index) == write_data, f"{master_name} must receive WDATA"
        assert _get_int(entry["outputs"]["WSTRB"], index) == strobe_mask, f"{master_name} must receive WSTRB"

        for other_name, other_idx in _all_index_pairs(masters):
            if other_name == master_name and other_idx == index:
                continue
            other_entry = masters[other_name]
            assert (
                _get_int(other_entry["outputs"]["AWVALID"], other_idx) == 0
            ), f"{other_name}{other_idx} AWVALID should remain low during {txn['label']}"
            assert (
                _get_int(other_entry["outputs"]["WVALID"], other_idx) == 0
            ), f"{other_name}{other_idx} WVALID should remain low during {txn['label']}"

        slave.AWVALID.value = 0
        slave.WVALID.value = 0
        slave.BREADY.value = 0
        await Timer(1, units="ns")

        read_data = _read_pattern(address, config["data_width"])
        _set_value(entry["inputs"]["RVALID"], index, 1)
        _set_value(entry["inputs"]["RDATA"], index, read_data)
        _set_value(entry["inputs"]["RRESP"], index, 0)

        slave.ARADDR.value = address
        slave.ARPROT.value = 0
        slave.ARVALID.value = 1
        slave.RREADY.value = 1

        await Timer(1, units="ns")

        assert _get_int(entry["outputs"]["ARVALID"], index) == 1, f"{master_name} should assert ARVALID"
        assert _get_int(entry["outputs"]["ARADDR"], index) == address, f"{master_name} must receive ARADDR"

        for other_name, other_idx in _all_index_pairs(masters):
            if other_name == master_name and other_idx == index:
                continue
            other_entry = masters[other_name]
            assert (
                _get_int(other_entry["outputs"]["ARVALID"], other_idx) == 0
            ), f"{other_name}{other_idx} ARVALID should remain low during read of {txn['label']}"

        assert int(slave.RVALID.value) == 1, "Slave should observe RVALID when master responds"
        assert int(slave.RDATA.value) == read_data, "Read data must fold back to slave"
        assert int(slave.RRESP.value) == 0, "Read response should indicate success"

        slave.ARVALID.value = 0
        slave.RREADY.value = 0
        _set_value(entry["inputs"]["RVALID"], index, 0)
        _set_value(entry["inputs"]["RDATA"], index, 0)
        await Timer(1, units="ns")
