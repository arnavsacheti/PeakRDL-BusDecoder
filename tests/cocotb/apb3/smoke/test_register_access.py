"""APB3 smoke tests generated from SystemRDL sources."""

from __future__ import annotations

import json
import os
from typing import Any, Iterable

import cocotb
from cocotb.triggers import Timer

from tests.cocotb_lib.handle_utils import SignalHandle, resolve_handle


class _Apb3SlaveShim:
    """Accessor for the APB3 slave signals on the DUT."""

    def __init__(self, dut):
        prefix = "s_apb"
        self.PSEL = getattr(dut, f"{prefix}_PSEL")
        self.PENABLE = getattr(dut, f"{prefix}_PENABLE")
        self.PWRITE = getattr(dut, f"{prefix}_PWRITE")
        self.PADDR = getattr(dut, f"{prefix}_PADDR")
        self.PWDATA = getattr(dut, f"{prefix}_PWDATA")
        self.PRDATA = getattr(dut, f"{prefix}_PRDATA")
        self.PREADY = getattr(dut, f"{prefix}_PREADY")
        self.PSLVERR = getattr(dut, f"{prefix}_PSLVERR")


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
                "PSEL": SignalHandle(dut, f"{prefix}_PSEL"),
                "PENABLE": SignalHandle(dut, f"{prefix}_PENABLE"),
                "PWRITE": SignalHandle(dut, f"{prefix}_PWRITE"),
                "PADDR": SignalHandle(dut, f"{prefix}_PADDR"),
                "PWDATA": SignalHandle(dut, f"{prefix}_PWDATA"),
            },
            "inputs": {
                "PRDATA": SignalHandle(dut, f"{prefix}_PRDATA"),
                "PREADY": SignalHandle(dut, f"{prefix}_PREADY"),
                "PSLVERR": SignalHandle(dut, f"{prefix}_PSLVERR"),
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
    return ((address * 0x2041) ^ 0xCAFEBABE) & mask


def _read_pattern(address: int, width: int) -> int:
    mask = (1 << width) - 1
    return ((address ^ 0x0BAD_F00D) + width) & mask


@cocotb.test()
async def test_apb3_address_decoding(dut) -> None:
    """Exercise the APB3 slave interface against sampled register addresses."""
    config = _load_config()
    slave = _Apb3SlaveShim(dut)
    masters = _build_master_table(dut, config["masters"])

    slave.PSEL.value = 0
    slave.PENABLE.value = 0
    slave.PWRITE.value = 0
    slave.PADDR.value = 0
    slave.PWDATA.value = 0

    for master_name, idx in _all_index_pairs(masters):
        entry = masters[master_name]
        _set_value(entry["inputs"]["PRDATA"], idx, 0)
        _set_value(entry["inputs"]["PREADY"], idx, 0)
        _set_value(entry["inputs"]["PSLVERR"], idx, 0)

    await Timer(1, units="ns")

    addr_mask = (1 << config["address_width"]) - 1

    for txn in config["transactions"]:
        master_name = txn["master"]
        index = tuple(txn["index"])
        entry = masters[master_name]

        address = txn["address"] & addr_mask
        write_data = _write_pattern(address, config["data_width"])

        _set_value(entry["inputs"]["PREADY"], index, 1)
        _set_value(entry["inputs"]["PSLVERR"], index, 0)

        slave.PADDR.value = address
        slave.PWDATA.value = write_data
        slave.PWRITE.value = 1
        slave.PSEL.value = 1
        slave.PENABLE.value = 1

        await Timer(1, units="ns")

        assert _get_int(entry["outputs"]["PSEL"], index) == 1, f"{master_name} should assert PSEL for write"
        assert _get_int(entry["outputs"]["PWRITE"], index) == 1, f"{master_name} should see write direction"
        assert _get_int(entry["outputs"]["PADDR"], index) == address, (
            f"{master_name} must receive write address"
        )
        assert _get_int(entry["outputs"]["PWDATA"], index) == write_data, (
            f"{master_name} must receive write data"
        )

        for other_name, other_idx in _all_index_pairs(masters):
            if other_name == master_name and other_idx == index:
                continue
            other_entry = masters[other_name]
            assert _get_int(other_entry["outputs"]["PSEL"], other_idx) == 0, (
                f"{other_name}{other_idx} should remain idle during {txn['label']}"
            )

        assert int(slave.PREADY.value) == 1, "Slave ready should mirror selected master"
        assert int(slave.PSLVERR.value) == 0, "Write should complete without error"

        slave.PSEL.value = 0
        slave.PENABLE.value = 0
        slave.PWRITE.value = 0
        _set_value(entry["inputs"]["PREADY"], index, 0)
        await Timer(1, units="ns")

        # ------------------------------------------------------------------
        # Read phase
        # ------------------------------------------------------------------
        read_data = _read_pattern(address, config["data_width"])
        _set_value(entry["inputs"]["PRDATA"], index, read_data)
        _set_value(entry["inputs"]["PREADY"], index, 1)
        _set_value(entry["inputs"]["PSLVERR"], index, 0)

        slave.PADDR.value = address
        slave.PWRITE.value = 0
        slave.PSEL.value = 1
        slave.PENABLE.value = 1

        await Timer(1, units="ns")

        assert _get_int(entry["outputs"]["PSEL"], index) == 1, f"{master_name} must assert PSEL for read"
        assert _get_int(entry["outputs"]["PWRITE"], index) == 0, (
            f"{master_name} should clear write during read"
        )
        assert _get_int(entry["outputs"]["PADDR"], index) == address, (
            f"{master_name} must receive read address"
        )

        for other_name, other_idx in _all_index_pairs(masters):
            if other_name == master_name and other_idx == index:
                continue
            other_entry = masters[other_name]
            assert _get_int(other_entry["outputs"]["PSEL"], other_idx) == 0, (
                f"{other_name}{other_idx} must stay idle during read of {txn['label']}"
            )

        assert int(slave.PRDATA.value) == read_data, "Read data should propagate back to the slave"
        assert int(slave.PREADY.value) == 1, "Slave ready should acknowledge the read"
        assert int(slave.PSLVERR.value) == 0, "Read should not signal an error"

        slave.PSEL.value = 0
        slave.PENABLE.value = 0
        _set_value(entry["inputs"]["PREADY"], index, 0)
        _set_value(entry["inputs"]["PRDATA"], index, 0)
        await Timer(1, units="ns")
