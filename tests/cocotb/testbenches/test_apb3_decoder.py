"""Cocotb tests for APB3 bus decoder."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


class APB3Master:
    """APB3 Master Bus Functional Model (no PSTRB support)."""

    def __init__(self, dut, name, clock):
        self.dut = dut
        self.clock = clock
        self.name = name
        self.psel = getattr(dut, f"{name}_PSEL")
        self.penable = getattr(dut, f"{name}_PENABLE")
        self.pwrite = getattr(dut, f"{name}_PWRITE")
        self.paddr = getattr(dut, f"{name}_PADDR")
        self.pwdata = getattr(dut, f"{name}_PWDATA")
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

    async def write(self, addr, data):
        """Perform APB3 write transaction."""
        await RisingEdge(self.clock)
        self.psel.value = 1
        self.penable.value = 0
        self.pwrite.value = 1
        self.paddr.value = addr
        self.pwdata.value = data
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
        """Perform APB3 read transaction."""
        await RisingEdge(self.clock)
        self.psel.value = 1
        self.penable.value = 0
        self.pwrite.value = 0
        self.paddr.value = addr
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


class APB3SlaveResponder:
    """Simple APB3 Slave responder."""

    def __init__(self, dut, name, clock):
        self.dut = dut
        self.clock = clock
        self.name = name
        self.psel = getattr(dut, f"{name}_PSEL")
        self.penable = getattr(dut, f"{name}_PENABLE")
        self.pwrite = getattr(dut, f"{name}_PWRITE")
        self.paddr = getattr(dut, f"{name}_PADDR")
        self.pwdata = getattr(dut, f"{name}_PWDATA")
        self.prdata = getattr(dut, f"{name}_PRDATA")
        self.pready = getattr(dut, f"{name}_PREADY")
        self.pslverr = getattr(dut, f"{name}_PSLVERR")
        self.storage = {}

    async def run(self):
        """Run the slave responder."""
        while True:
            await RisingEdge(self.clock)
            if self.psel.value == 1 and self.penable.value == 1:
                addr = self.paddr.value.integer
                if self.pwrite.value == 1:
                    data = self.pwdata.value.integer
                    self.storage[addr] = data
                    self.pready.value = 1
                    self.pslverr.value = 0
                else:
                    data = self.storage.get(addr, 0)
                    self.prdata.value = data
                    self.pready.value = 1
                    self.pslverr.value = 0
            else:
                self.pready.value = 0
                self.pslverr.value = 0


@cocotb.test()
async def test_simple_read_write(dut):
    """Test simple read and write operations on APB3."""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    master = APB3Master(dut, "s_apb", dut.clk)
    slave = APB3SlaveResponder(dut, "m_apb_test_reg", dut.clk)

    # Reset
    dut.rst.value = 1
    master.reset()
    await Timer(100, units="ns")
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    cocotb.start_soon(slave.run())

    for _ in range(5):
        await RisingEdge(dut.clk)

    # Write test
    dut._log.info("Writing 0xABCD1234 to address 0x0")
    success = await master.write(0x0, 0xABCD1234)
    assert success, "Write operation failed"

    # Read test
    dut._log.info("Reading from address 0x0")
    data, error = await master.read(0x0)
    assert not error, "Read operation returned error"
    assert data == 0xABCD1234, f"Read data mismatch: expected 0xABCD1234, got 0x{data:08X}"

    dut._log.info("Test passed!")


@cocotb.test()
async def test_multiple_registers(dut):
    """Test operations on multiple registers with APB3."""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    master = APB3Master(dut, "s_apb", dut.clk)
    slave1 = APB3SlaveResponder(dut, "m_apb_reg1", dut.clk)
    slave2 = APB3SlaveResponder(dut, "m_apb_reg2", dut.clk)
    slave3 = APB3SlaveResponder(dut, "m_apb_reg3", dut.clk)

    # Reset
    dut.rst.value = 1
    master.reset()
    await Timer(100, units="ns")
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    cocotb.start_soon(slave1.run())
    cocotb.start_soon(slave2.run())
    cocotb.start_soon(slave3.run())

    for _ in range(5):
        await RisingEdge(dut.clk)

    # Test each register
    test_data = [0x11111111, 0x22222222, 0x33333333]
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
