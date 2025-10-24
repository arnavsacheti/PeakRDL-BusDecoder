"""Cocotb tests for APB4 bus decoder."""

import os
import tempfile
from pathlib import Path

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif

# Import the common test utilities
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from common.utils import compile_rdl_and_export


# APB4 Master BFM
class APB4Master:
    """APB4 Master Bus Functional Model."""

    def __init__(self, dut, name, clock):
        self.dut = dut
        self.clock = clock
        self.name = name
        self.psel = getattr(dut, f"{name}_PSEL")
        self.penable = getattr(dut, f"{name}_PENABLE")
        self.pwrite = getattr(dut, f"{name}_PWRITE")
        self.paddr = getattr(dut, f"{name}_PADDR")
        self.pwdata = getattr(dut, f"{name}_PWDATA")
        self.pstrb = getattr(dut, f"{name}_PSTRB")
        self.pprot = getattr(dut, f"{name}_PPROT")
        self.prdata = getattr(dut, f"{name}_PRDATA")
        self.pready = getattr(dut, f"{name}_PREADY")
        self.pslverr = getattr(dut, f"{name}_PSLVERR")

    def reset(self):
        """Reset the bus to idle state."""
        self.psel.value = 0
        self.penable.value = 0
        self.pwrite.value = 0
        self.paddr.value = 0
        self.pwdata.value = 0
        self.pstrb.value = 0
        self.pprot.value = 0

    async def write(self, addr, data, strb=None):
        """Perform APB4 write transaction."""
        if strb is None:
            strb = 0xF
        await RisingEdge(self.clock)
        self.psel.value = 1
        self.penable.value = 0
        self.pwrite.value = 1
        self.paddr.value = addr
        self.pwdata.value = data
        self.pstrb.value = strb
        self.pprot.value = 0
        await RisingEdge(self.clock)
        self.penable.value = 1
        while True:
            await RisingEdge(self.clock)
            if self.pready.value == 1:
                error = self.pslverr.value == 1
                break
        self.psel.value = 0
        self.penable.value = 0
        return not error

    async def read(self, addr):
        """Perform APB4 read transaction."""
        await RisingEdge(self.clock)
        self.psel.value = 1
        self.penable.value = 0
        self.pwrite.value = 0
        self.paddr.value = addr
        self.pprot.value = 0
        await RisingEdge(self.clock)
        self.penable.value = 1
        while True:
            await RisingEdge(self.clock)
            if self.pready.value == 1:
                data = self.prdata.value.integer
                error = self.pslverr.value == 1
                break
        self.psel.value = 0
        self.penable.value = 0
        return data, error


# APB4 Slave responder
class APB4SlaveResponder:
    """Simple APB4 Slave responder that acknowledges all transactions."""

    def __init__(self, dut, name, clock):
        self.dut = dut
        self.clock = clock
        self.name = name
        self.psel = getattr(dut, f"{name}_PSEL")
        self.penable = getattr(dut, f"{name}_PENABLE")
        self.pwrite = getattr(dut, f"{name}_PWRITE")
        self.paddr = getattr(dut, f"{name}_PADDR")
        self.pwdata = getattr(dut, f"{name}_PWDATA")
        self.pstrb = getattr(dut, f"{name}_PSTRB")
        self.prdata = getattr(dut, f"{name}_PRDATA")
        self.pready = getattr(dut, f"{name}_PREADY")
        self.pslverr = getattr(dut, f"{name}_PSLVERR")
        # Storage for register values
        self.storage = {}

    async def run(self):
        """Run the slave responder."""
        while True:
            await RisingEdge(self.clock)
            if self.psel.value == 1 and self.penable.value == 1:
                addr = self.paddr.value.integer
                if self.pwrite.value == 1:
                    # Write operation
                    data = self.pwdata.value.integer
                    self.storage[addr] = data
                    self.pready.value = 1
                    self.pslverr.value = 0
                else:
                    # Read operation
                    data = self.storage.get(addr, 0)
                    self.prdata.value = data
                    self.pready.value = 1
                    self.pslverr.value = 0
            else:
                self.pready.value = 0
                self.pslverr.value = 0


@cocotb.test()
async def test_simple_read_write(dut):
    """Test simple read and write operations."""
    # Start clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Create master and slave
    master = APB4Master(dut, "s_apb", dut.clk)
    slave = APB4SlaveResponder(dut, "m_apb_test_reg", dut.clk)

    # Reset
    dut.rst.value = 1
    master.reset()
    await Timer(100, units="ns")
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # Start slave responder
    cocotb.start_soon(slave.run())

    # Wait a few cycles
    for _ in range(5):
        await RisingEdge(dut.clk)

    # Write test
    dut._log.info("Writing 0xDEADBEEF to address 0x0")
    success = await master.write(0x0, 0xDEADBEEF)
    assert success, "Write operation failed"

    # Read test
    dut._log.info("Reading from address 0x0")
    data, error = await master.read(0x0)
    assert not error, "Read operation returned error"
    assert data == 0xDEADBEEF, f"Read data mismatch: expected 0xDEADBEEF, got 0x{data:08X}"

    dut._log.info("Test passed!")


@cocotb.test()
async def test_multiple_registers(dut):
    """Test operations on multiple registers."""
    # Start clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Create master and slaves
    master = APB4Master(dut, "s_apb", dut.clk)
    slave1 = APB4SlaveResponder(dut, "m_apb_reg1", dut.clk)
    slave2 = APB4SlaveResponder(dut, "m_apb_reg2", dut.clk)
    slave3 = APB4SlaveResponder(dut, "m_apb_reg3", dut.clk)

    # Reset
    dut.rst.value = 1
    master.reset()
    await Timer(100, units="ns")
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # Start slave responders
    cocotb.start_soon(slave1.run())
    cocotb.start_soon(slave2.run())
    cocotb.start_soon(slave3.run())

    # Wait a few cycles
    for _ in range(5):
        await RisingEdge(dut.clk)

    # Test each register
    test_data = [0x12345678, 0xABCDEF00, 0xCAFEBABE]
    for i, data in enumerate(test_data):
        addr = i * 4
        dut._log.info(f"Writing 0x{data:08X} to address 0x{addr:X}")
        success = await master.write(addr, data)
        assert success, f"Write to address 0x{addr:X} failed"

        dut._log.info(f"Reading from address 0x{addr:X}")
        read_data, error = await master.read(addr)
        assert not error, f"Read from address 0x{addr:X} returned error"
        assert read_data == data, f"Data mismatch at 0x{addr:X}: expected 0x{data:08X}, got 0x{read_data:08X}"

    dut._log.info("Test passed!")


@cocotb.test()
async def test_byte_strobe(dut):
    """Test byte strobe functionality."""
    # Start clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Create master and slave
    master = APB4Master(dut, "s_apb", dut.clk)
    slave = APB4SlaveResponder(dut, "m_apb_test_reg", dut.clk)

    # Reset
    dut.rst.value = 1
    master.reset()
    await Timer(100, units="ns")
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # Start slave responder
    cocotb.start_soon(slave.run())

    # Wait a few cycles
    for _ in range(5):
        await RisingEdge(dut.clk)

    # Write full word
    await master.write(0x0, 0x12345678, strb=0xF)

    # Read back
    data, error = await master.read(0x0)
    assert not error
    assert data == 0x12345678

    # Write only lower byte
    await master.write(0x0, 0x000000AB, strb=0x1)
    data, error = await master.read(0x0)
    assert not error
    assert (data & 0xFF) == 0xAB

    dut._log.info("Test passed!")

