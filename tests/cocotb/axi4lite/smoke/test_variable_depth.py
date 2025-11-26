"""AXI4-Lite smoke tests for variable depth design testing max_decode_depth parameter."""

import cocotb
from cocotb.triggers import Timer


class _AxilSlaveShim:
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


class _AxilMasterShim:
    def __init__(self, dut, base: str):
        self.AWREADY = getattr(dut, f"{base}_AWREADY")
        self.AWVALID = getattr(dut, f"{base}_AWVALID")
        self.AWADDR = getattr(dut, f"{base}_AWADDR")
        self.AWPROT = getattr(dut, f"{base}_AWPROT")
        self.WREADY = getattr(dut, f"{base}_WREADY")
        self.WVALID = getattr(dut, f"{base}_WVALID")
        self.WDATA = getattr(dut, f"{base}_WDATA")
        self.WSTRB = getattr(dut, f"{base}_WSTRB")
        self.BREADY = getattr(dut, f"{base}_BREADY")
        self.BVALID = getattr(dut, f"{base}_BVALID")
        self.BRESP = getattr(dut, f"{base}_BRESP")
        self.ARREADY = getattr(dut, f"{base}_ARREADY")
        self.ARVALID = getattr(dut, f"{base}_ARVALID")
        self.ARADDR = getattr(dut, f"{base}_ARADDR")
        self.ARPROT = getattr(dut, f"{base}_ARPROT")
        self.RREADY = getattr(dut, f"{base}_RREADY")
        self.RVALID = getattr(dut, f"{base}_RVALID")
        self.RDATA = getattr(dut, f"{base}_RDATA")
        self.RRESP = getattr(dut, f"{base}_RRESP")


def _axil_slave(dut):
    return getattr(dut, "s_axil", None) or _AxilSlaveShim(dut)


def _axil_master(dut, base: str):
    return getattr(dut, base, None) or _AxilMasterShim(dut, base)


@cocotb.test()
async def test_depth_1(dut):
    """Test max_decode_depth=1 - should have interface for inner1 only."""
    s_axil = _axil_slave(dut)

    # At depth 1, we should have m_axil_inner1 but not deeper interfaces
    inner1 = _axil_master(dut, "m_axil_inner1")

    # Default slave side inputs
    s_axil.AWVALID.value = 0
    s_axil.AWADDR.value = 0
    s_axil.AWPROT.value = 0
    s_axil.WVALID.value = 0
    s_axil.WDATA.value = 0
    s_axil.WSTRB.value = 0
    s_axil.BREADY.value = 0
    s_axil.ARVALID.value = 0
    s_axil.ARADDR.value = 0
    s_axil.ARPROT.value = 0
    s_axil.RREADY.value = 0

    inner1.AWREADY.value = 0
    inner1.WREADY.value = 0
    inner1.BVALID.value = 0
    inner1.BRESP.value = 0
    inner1.ARREADY.value = 0
    inner1.RVALID.value = 0
    inner1.RDATA.value = 0
    inner1.RRESP.value = 0

    await Timer(1, units="ns")

    # Write to address 0x0 (should select inner1)
    inner1.AWREADY.value = 1
    inner1.WREADY.value = 1
    s_axil.AWVALID.value = 1
    s_axil.AWADDR.value = 0x0
    s_axil.WVALID.value = 1
    s_axil.WDATA.value = 0x12345678
    s_axil.WSTRB.value = 0xF

    await Timer(1, units="ns")

    assert int(inner1.AWVALID.value) == 1, "inner1 write address valid must be set"
    assert int(inner1.WVALID.value) == 1, "inner1 write data valid must be set"


@cocotb.test()
async def test_depth_2(dut):
    """Test max_decode_depth=2 - should have interfaces for reg1 and inner2."""
    s_axil = _axil_slave(dut)

    # At depth 2, we should have m_axil_reg1 and m_axil_inner2
    reg1 = _axil_master(dut, "m_axil_reg1")
    inner2 = _axil_master(dut, "m_axil_inner2")

    # Default slave side inputs
    s_axil.AWVALID.value = 0
    s_axil.AWADDR.value = 0
    s_axil.AWPROT.value = 0
    s_axil.WVALID.value = 0
    s_axil.WDATA.value = 0
    s_axil.WSTRB.value = 0
    s_axil.BREADY.value = 0
    s_axil.ARVALID.value = 0
    s_axil.ARADDR.value = 0
    s_axil.ARPROT.value = 0
    s_axil.RREADY.value = 0

    for master in [reg1, inner2]:
        master.AWREADY.value = 0
        master.WREADY.value = 0
        master.BVALID.value = 0
        master.BRESP.value = 0
        master.ARREADY.value = 0
        master.RVALID.value = 0
        master.RDATA.value = 0
        master.RRESP.value = 0

    await Timer(1, units="ns")

    # Write to address 0x0 (should select reg1)
    reg1.AWREADY.value = 1
    reg1.WREADY.value = 1
    s_axil.AWVALID.value = 1
    s_axil.AWADDR.value = 0x0
    s_axil.WVALID.value = 1
    s_axil.WDATA.value = 0xABCDEF01
    s_axil.WSTRB.value = 0xF

    await Timer(1, units="ns")

    assert int(reg1.AWVALID.value) == 1, "reg1 must be selected for address 0x0"
    assert int(inner2.AWVALID.value) == 0, "inner2 should not be selected"

    # Reset
    s_axil.AWVALID.value = 0
    s_axil.WVALID.value = 0
    reg1.AWREADY.value = 0
    reg1.WREADY.value = 0
    await Timer(1, units="ns")

    # Write to address 0x10 (should select inner2)
    inner2.AWREADY.value = 1
    inner2.WREADY.value = 1
    s_axil.AWVALID.value = 1
    s_axil.AWADDR.value = 0x10
    s_axil.WVALID.value = 1
    s_axil.WDATA.value = 0x23456789
    s_axil.WSTRB.value = 0xF

    await Timer(1, units="ns")

    assert int(inner2.AWVALID.value) == 1, "inner2 must be selected for address 0x10"
    assert int(reg1.AWVALID.value) == 0, "reg1 should not be selected"


@cocotb.test()
async def test_depth_0(dut):
    """Test max_decode_depth=0 - should have interfaces for all leaf registers."""
    s_axil = _axil_slave(dut)

    # At depth 0, we should have all leaf registers: reg1, reg2, reg2b
    reg1 = _axil_master(dut, "m_axil_reg1")
    reg2 = _axil_master(dut, "m_axil_reg2")
    reg2b = _axil_master(dut, "m_axil_reg2b")

    # Default slave side inputs
    s_axil.AWVALID.value = 0
    s_axil.AWADDR.value = 0
    s_axil.AWPROT.value = 0
    s_axil.WVALID.value = 0
    s_axil.WDATA.value = 0
    s_axil.WSTRB.value = 0
    s_axil.BREADY.value = 0
    s_axil.ARVALID.value = 0
    s_axil.ARADDR.value = 0
    s_axil.ARPROT.value = 0
    s_axil.RREADY.value = 0

    for master in [reg1, reg2, reg2b]:
        master.AWREADY.value = 0
        master.WREADY.value = 0
        master.BVALID.value = 0
        master.BRESP.value = 0
        master.ARREADY.value = 0
        master.RVALID.value = 0
        master.RDATA.value = 0
        master.RRESP.value = 0

    await Timer(1, units="ns")

    # Write to address 0x0 (should select reg1)
    reg1.AWREADY.value = 1
    reg1.WREADY.value = 1
    s_axil.AWVALID.value = 1
    s_axil.AWADDR.value = 0x0
    s_axil.WVALID.value = 1
    s_axil.WDATA.value = 0x11111111
    s_axil.WSTRB.value = 0xF

    await Timer(1, units="ns")

    assert int(reg1.AWVALID.value) == 1, "reg1 must be selected for address 0x0"
    assert int(reg2.AWVALID.value) == 0, "reg2 should not be selected"
    assert int(reg2b.AWVALID.value) == 0, "reg2b should not be selected"

    # Reset
    s_axil.AWVALID.value = 0
    s_axil.WVALID.value = 0
    reg1.AWREADY.value = 0
    reg1.WREADY.value = 0
    await Timer(1, units="ns")

    # Write to address 0x10 (should select reg2)
    reg2.AWREADY.value = 1
    reg2.WREADY.value = 1
    s_axil.AWVALID.value = 1
    s_axil.AWADDR.value = 0x10
    s_axil.WVALID.value = 1
    s_axil.WDATA.value = 0x22222222
    s_axil.WSTRB.value = 0xF

    await Timer(1, units="ns")

    assert int(reg2.AWVALID.value) == 1, "reg2 must be selected for address 0x10"
    assert int(reg1.AWVALID.value) == 0, "reg1 should not be selected"
    assert int(reg2b.AWVALID.value) == 0, "reg2b should not be selected"

    # Reset
    s_axil.AWVALID.value = 0
    s_axil.WVALID.value = 0
    reg2.AWREADY.value = 0
    reg2.WREADY.value = 0
    await Timer(1, units="ns")

    # Write to address 0x14 (should select reg2b)
    reg2b.AWREADY.value = 1
    reg2b.WREADY.value = 1
    s_axil.AWVALID.value = 1
    s_axil.AWADDR.value = 0x14
    s_axil.WVALID.value = 1
    s_axil.WDATA.value = 0x33333333
    s_axil.WSTRB.value = 0xF

    await Timer(1, units="ns")

    assert int(reg2b.AWVALID.value) == 1, "reg2b must be selected for address 0x14"
    assert int(reg1.AWVALID.value) == 0, "reg1 should not be selected"
    assert int(reg2.AWVALID.value) == 0, "reg2 should not be selected"
