"""Cocotb tests for AXI4-Lite bus decoder."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


class AXI4LiteMaster:
    """AXI4-Lite Master Bus Functional Model."""

    def __init__(self, dut, name, clock):
        self.dut = dut
        self.clock = clock
        self.name = name

        # Write address channel
        self.awvalid = getattr(dut, f"{name}_AWVALID")
        self.awready = getattr(dut, f"{name}_AWREADY")
        self.awaddr = getattr(dut, f"{name}_AWADDR")
        self.awprot = getattr(dut, f"{name}_AWPROT")

        # Write data channel
        self.wvalid = getattr(dut, f"{name}_WVALID")
        self.wready = getattr(dut, f"{name}_WREADY")
        self.wdata = getattr(dut, f"{name}_WDATA")
        self.wstrb = getattr(dut, f"{name}_WSTRB")

        # Write response channel
        self.bvalid = getattr(dut, f"{name}_BVALID")
        self.bready = getattr(dut, f"{name}_BREADY")
        self.bresp = getattr(dut, f"{name}_BRESP")

        # Read address channel
        self.arvalid = getattr(dut, f"{name}_ARVALID")
        self.arready = getattr(dut, f"{name}_ARREADY")
        self.araddr = getattr(dut, f"{name}_ARADDR")
        self.arprot = getattr(dut, f"{name}_ARPROT")

        # Read data channel
        self.rvalid = getattr(dut, f"{name}_RVALID")
        self.rready = getattr(dut, f"{name}_RREADY")
        self.rdata = getattr(dut, f"{name}_RDATA")
        self.rresp = getattr(dut, f"{name}_RRESP")

    def reset(self):
        """Reset the bus to idle state."""
        self.awvalid.value = 0
        self.awaddr.value = 0
        self.awprot.value = 0
        self.wvalid.value = 0
        self.wdata.value = 0
        self.wstrb.value = 0
        self.bready.value = 1
        self.arvalid.value = 0
        self.araddr.value = 0
        self.arprot.value = 0
        self.rready.value = 1

    async def write(self, addr, data, strb=None):
        """Perform AXI4-Lite write transaction."""
        if strb is None:
            strb = 0xF

        # Write address phase
        await RisingEdge(self.clock)
        self.awvalid.value = 1
        self.awaddr.value = addr
        self.awprot.value = 0

        # Write data phase
        self.wvalid.value = 1
        self.wdata.value = data
        self.wstrb.value = strb

        # Wait for address accept
        while True:
            await RisingEdge(self.clock)
            if self.awready.value == 1:
                self.awvalid.value = 0
                break

        # Wait for data accept
        while self.wready.value != 1:
            await RisingEdge(self.clock)
        self.wvalid.value = 0

        # Wait for write response
        self.bready.value = 1
        while self.bvalid.value != 1:
            await RisingEdge(self.clock)

        error = self.bresp.value != 0
        await RisingEdge(self.clock)

        return not error

    async def read(self, addr):
        """Perform AXI4-Lite read transaction."""
        # Read address phase
        await RisingEdge(self.clock)
        self.arvalid.value = 1
        self.araddr.value = addr
        self.arprot.value = 0

        # Wait for address accept
        while True:
            await RisingEdge(self.clock)
            if self.arready.value == 1:
                self.arvalid.value = 0
                break

        # Wait for read data
        self.rready.value = 1
        while self.rvalid.value != 1:
            await RisingEdge(self.clock)

        data = self.rdata.value.integer
        error = self.rresp.value != 0
        await RisingEdge(self.clock)

        return data, error


class AXI4LiteSlaveResponder:
    """Simple AXI4-Lite Slave responder."""

    def __init__(self, dut, name, clock):
        self.dut = dut
        self.clock = clock
        self.name = name

        # Get all signals
        self.awvalid = getattr(dut, f"{name}_AWVALID")
        self.awready = getattr(dut, f"{name}_AWREADY")
        self.awaddr = getattr(dut, f"{name}_AWADDR")
        self.wvalid = getattr(dut, f"{name}_WVALID")
        self.wready = getattr(dut, f"{name}_WREADY")
        self.wdata = getattr(dut, f"{name}_WDATA")
        self.wstrb = getattr(dut, f"{name}_WSTRB")
        self.bvalid = getattr(dut, f"{name}_BVALID")
        self.bready = getattr(dut, f"{name}_BREADY")
        self.bresp = getattr(dut, f"{name}_BRESP")
        self.arvalid = getattr(dut, f"{name}_ARVALID")
        self.arready = getattr(dut, f"{name}_ARREADY")
        self.araddr = getattr(dut, f"{name}_ARADDR")
        self.rvalid = getattr(dut, f"{name}_RVALID")
        self.rready = getattr(dut, f"{name}_RREADY")
        self.rdata = getattr(dut, f"{name}_RDATA")
        self.rresp = getattr(dut, f"{name}_RRESP")

        self.storage = {}
        self.write_pending = False
        self.pending_addr = 0
        self.pending_data = 0

    async def run(self):
        """Run the slave responder."""
        while True:
            await RisingEdge(self.clock)

            # Handle write address channel
            if self.awvalid.value == 1 and not self.write_pending:
                self.awready.value = 1
                self.pending_addr = self.awaddr.value.integer
                self.write_pending = True
            else:
                self.awready.value = 0

            # Handle write data channel
            if self.wvalid.value == 1 and self.write_pending:
                self.wready.value = 1
                self.pending_data = self.wdata.value.integer
                self.storage[self.pending_addr] = self.pending_data
                # Send write response
                self.bvalid.value = 1
                self.bresp.value = 0
                self.write_pending = False
            else:
                self.wready.value = 0
                if self.bvalid.value == 1 and self.bready.value == 1:
                    self.bvalid.value = 0

            # Handle read address channel
            if self.arvalid.value == 1:
                self.arready.value = 1
                addr = self.araddr.value.integer
                data = self.storage.get(addr, 0)
                self.rdata.value = data
                self.rvalid.value = 1
                self.rresp.value = 0
            else:
                self.arready.value = 0
                if self.rvalid.value == 1 and self.rready.value == 1:
                    self.rvalid.value = 0


@cocotb.test()
async def test_simple_read_write(dut):
    """Test simple read and write operations on AXI4-Lite."""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    master = AXI4LiteMaster(dut, "s_axi", dut.clk)
    slave = AXI4LiteSlaveResponder(dut, "m_axi_test_reg", dut.clk)

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
    dut._log.info("Writing 0xFEEDFACE to address 0x0")
    success = await master.write(0x0, 0xFEEDFACE)
    assert success, "Write operation failed"

    # Read test
    dut._log.info("Reading from address 0x0")
    data, error = await master.read(0x0)
    assert not error, "Read operation returned error"
    assert data == 0xFEEDFACE, f"Read data mismatch: expected 0xFEEDFACE, got 0x{data:08X}"

    dut._log.info("Test passed!")


@cocotb.test()
async def test_multiple_registers(dut):
    """Test operations on multiple registers with AXI4-Lite."""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    master = AXI4LiteMaster(dut, "s_axi", dut.clk)
    slave1 = AXI4LiteSlaveResponder(dut, "m_axi_reg1", dut.clk)
    slave2 = AXI4LiteSlaveResponder(dut, "m_axi_reg2", dut.clk)
    slave3 = AXI4LiteSlaveResponder(dut, "m_axi_reg3", dut.clk)

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
    test_data = [0xAAAAAAAA, 0xBBBBBBBB, 0xCCCCCCCC]
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
    """Test byte strobe functionality with AXI4-Lite."""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    master = AXI4LiteMaster(dut, "s_axi", dut.clk)
    slave = AXI4LiteSlaveResponder(dut, "m_axi_test_reg", dut.clk)

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

    # Write full word
    await master.write(0x0, 0x12345678, strb=0xF)

    # Read back
    data, error = await master.read(0x0)
    assert not error
    assert data == 0x12345678

    # Write only lower byte
    await master.write(0x0, 0x000000CD, strb=0x1)
    data, error = await master.read(0x0)
    assert not error
    assert (data & 0xFF) == 0xCD

    dut._log.info("Test passed!")
