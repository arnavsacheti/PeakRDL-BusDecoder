"""Clocked routing checks for each ``max_decode_depth`` setting."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

from tests.cocotb.axi4lite.smoke.test_register_access import (
    _AxilSlaveShim,
    _accept_write,
    _wait_until,
)


class _AxilMasterShim:
    def __init__(self, dut, base: str):
        for name in (
            "AWREADY",
            "AWVALID",
            "AWADDR",
            "AWPROT",
            "WREADY",
            "WVALID",
            "WDATA",
            "WSTRB",
            "BREADY",
            "BVALID",
            "BRESP",
            "ARREADY",
            "ARVALID",
            "ARADDR",
            "ARPROT",
            "RREADY",
            "RVALID",
            "RDATA",
            "RRESP",
        ):
            setattr(self, name, getattr(dut, f"{base}_{name}"))


def _idle_master(master: _AxilMasterShim) -> None:
    master.AWREADY.value = 0
    master.WREADY.value = 0
    master.BVALID.value = 0
    master.BRESP.value = 0
    master.ARREADY.value = 0
    master.RVALID.value = 0
    master.RDATA.value = 0
    master.RRESP.value = 0


async def _initialize(dut, slave: _AxilSlaveShim, masters: dict[str, _AxilMasterShim]) -> None:
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
    for master in masters.values():
        _idle_master(master)

    dut.clk.value = 0
    dut.rst.value = 1
    cocotb.start_soon(Clock(dut.clk, 2, unit="ns").start())
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def _check_write_route(
    dut,
    slave: _AxilSlaveShim,
    masters: dict[str, _AxilMasterShim],
    target: str,
    address: int,
    data: int,
) -> None:
    await _accept_write(dut, slave, address, data, 0xF)
    await _wait_until(
        dut,
        lambda: int(masters[target].AWVALID.value) == 1
        and int(masters[target].WVALID.value) == 1,
        f"{target} was not selected for {address:#x}",
    )
    assert int(masters[target].AWADDR.value) == 0
    assert int(masters[target].WDATA.value) == data
    for name, master in masters.items():
        if name != target:
            assert int(master.AWVALID.value) == 0
            assert int(master.WVALID.value) == 0

    await FallingEdge(dut.clk)
    masters[target].AWREADY.value = 1
    masters[target].WREADY.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    masters[target].AWREADY.value = 0
    masters[target].WREADY.value = 0


@cocotb.test()
async def test_depth_1(dut) -> None:
    slave = _AxilSlaveShim(dut)
    masters = {"inner1": _AxilMasterShim(dut, "m_axil_inner1")}
    await _initialize(dut, slave, masters)
    await _check_write_route(dut, slave, masters, "inner1", 0x0, 0x1234_5678)


@cocotb.test()
async def test_depth_2(dut) -> None:
    slave = _AxilSlaveShim(dut)
    masters = {
        "reg1": _AxilMasterShim(dut, "m_axil_reg1"),
        "inner2": _AxilMasterShim(dut, "m_axil_inner2"),
    }
    await _initialize(dut, slave, masters)
    await _check_write_route(dut, slave, masters, "reg1", 0x0, 0xABCD_EF01)
    await _check_write_route(dut, slave, masters, "inner2", 0x10, 0x2345_6789)


@cocotb.test()
async def test_depth_0(dut) -> None:
    slave = _AxilSlaveShim(dut)
    masters = {
        "reg1": _AxilMasterShim(dut, "m_axil_reg1"),
        "reg2": _AxilMasterShim(dut, "m_axil_reg2"),
        "reg2b": _AxilMasterShim(dut, "m_axil_reg2b"),
    }
    await _initialize(dut, slave, masters)
    await _check_write_route(dut, slave, masters, "reg1", 0x0, 0x1111_1111)
    await _check_write_route(dut, slave, masters, "reg2", 0x10, 0x2222_2222)
    await _check_write_route(dut, slave, masters, "reg2b", 0x14, 0x3333_3333)
