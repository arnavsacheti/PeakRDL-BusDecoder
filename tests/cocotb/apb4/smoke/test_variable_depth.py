"""APB4 smoke tests for variable depth design testing max_decode_depth parameter."""

import cocotb
from cocotb.triggers import Timer


class _Apb4SlaveShim:
    def __init__(self, dut):
        prefix = "s_apb"
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


class _Apb4MasterShim:
    def __init__(self, dut, base: str):
        self.PSEL = getattr(dut, f"{base}_PSEL")
        self.PENABLE = getattr(dut, f"{base}_PENABLE")
        self.PWRITE = getattr(dut, f"{base}_PWRITE")
        self.PADDR = getattr(dut, f"{base}_PADDR")
        self.PPROT = getattr(dut, f"{base}_PPROT")
        self.PWDATA = getattr(dut, f"{base}_PWDATA")
        self.PSTRB = getattr(dut, f"{base}_PSTRB")
        self.PRDATA = getattr(dut, f"{base}_PRDATA")
        self.PREADY = getattr(dut, f"{base}_PREADY")
        self.PSLVERR = getattr(dut, f"{base}_PSLVERR")


def _apb4_slave(dut):
    return getattr(dut, "s_apb", None) or _Apb4SlaveShim(dut)


def _apb4_master(dut, base: str):
    return getattr(dut, base, None) or _Apb4MasterShim(dut, base)


@cocotb.test()
async def test_depth_1(dut):
    """Test max_decode_depth=1 - should have interface for inner1 only."""
    s_apb = _apb4_slave(dut)

    # At depth 1, we should have m_apb_inner1 but not deeper interfaces
    inner1 = _apb4_master(dut, "m_apb_inner1")

    # Default slave side inputs
    s_apb.PSEL.value = 0
    s_apb.PENABLE.value = 0
    s_apb.PWRITE.value = 0
    s_apb.PADDR.value = 0
    s_apb.PWDATA.value = 0
    s_apb.PPROT.value = 0
    s_apb.PSTRB.value = 0

    inner1.PRDATA.value = 0
    inner1.PREADY.value = 0
    inner1.PSLVERR.value = 0

    await Timer(1, units="ns")

    # Write to address 0x0 (should select inner1)
    inner1.PREADY.value = 1
    s_apb.PADDR.value = 0x0
    s_apb.PWDATA.value = 0x12345678
    s_apb.PSTRB.value = 0xF
    s_apb.PWRITE.value = 1
    s_apb.PSEL.value = 1
    s_apb.PENABLE.value = 1

    await Timer(1, units="ns")

    assert int(inner1.PSEL.value) == 1, "inner1 must be selected"
    assert int(inner1.PWRITE.value) == 1, "Write should propagate"
    assert int(s_apb.PREADY.value) == 1, "Ready should mirror master"


@cocotb.test()
async def test_depth_2(dut):
    """Test max_decode_depth=2 - should have interfaces for reg1 and inner2."""
    s_apb = _apb4_slave(dut)

    # At depth 2, we should have m_apb_reg1 and m_apb_inner2
    reg1 = _apb4_master(dut, "m_apb_reg1")
    inner2 = _apb4_master(dut, "m_apb_inner2")

    # Default slave side inputs
    s_apb.PSEL.value = 0
    s_apb.PENABLE.value = 0
    s_apb.PWRITE.value = 0
    s_apb.PADDR.value = 0
    s_apb.PWDATA.value = 0
    s_apb.PPROT.value = 0
    s_apb.PSTRB.value = 0

    reg1.PRDATA.value = 0
    reg1.PREADY.value = 0
    reg1.PSLVERR.value = 0

    inner2.PRDATA.value = 0
    inner2.PREADY.value = 0
    inner2.PSLVERR.value = 0

    await Timer(1, units="ns")

    # Write to address 0x0 (should select reg1)
    reg1.PREADY.value = 1
    s_apb.PADDR.value = 0x0
    s_apb.PWDATA.value = 0xABCDEF01
    s_apb.PSTRB.value = 0xF
    s_apb.PWRITE.value = 1
    s_apb.PSEL.value = 1
    s_apb.PENABLE.value = 1

    await Timer(1, units="ns")

    assert int(reg1.PSEL.value) == 1, "reg1 must be selected for address 0x0"
    assert int(inner2.PSEL.value) == 0, "inner2 should not be selected"

    # Reset
    s_apb.PSEL.value = 0
    s_apb.PENABLE.value = 0
    reg1.PREADY.value = 0
    await Timer(1, units="ns")

    # Write to address 0x10 (should select inner2)
    inner2.PREADY.value = 1
    s_apb.PADDR.value = 0x10
    s_apb.PWDATA.value = 0x23456789
    s_apb.PSTRB.value = 0xF
    s_apb.PWRITE.value = 1
    s_apb.PSEL.value = 1
    s_apb.PENABLE.value = 1

    await Timer(1, units="ns")

    assert int(inner2.PSEL.value) == 1, "inner2 must be selected for address 0x10"
    assert int(reg1.PSEL.value) == 0, "reg1 should not be selected"


@cocotb.test()
async def test_depth_0(dut):
    """Test max_decode_depth=0 - should have interfaces for all leaf registers."""
    s_apb = _apb4_slave(dut)

    # At depth 0, we should have all leaf registers: reg1, reg2, reg2b
    reg1 = _apb4_master(dut, "m_apb_reg1")
    reg2 = _apb4_master(dut, "m_apb_reg2")
    reg2b = _apb4_master(dut, "m_apb_reg2b")

    # Default slave side inputs
    s_apb.PSEL.value = 0
    s_apb.PENABLE.value = 0
    s_apb.PWRITE.value = 0
    s_apb.PADDR.value = 0
    s_apb.PWDATA.value = 0
    s_apb.PPROT.value = 0
    s_apb.PSTRB.value = 0

    for master in [reg1, reg2, reg2b]:
        master.PRDATA.value = 0
        master.PREADY.value = 0
        master.PSLVERR.value = 0

    await Timer(1, units="ns")

    # Write to address 0x0 (should select reg1)
    reg1.PREADY.value = 1
    s_apb.PADDR.value = 0x0
    s_apb.PWDATA.value = 0x11111111
    s_apb.PSTRB.value = 0xF
    s_apb.PWRITE.value = 1
    s_apb.PSEL.value = 1
    s_apb.PENABLE.value = 1

    await Timer(1, units="ns")

    assert int(reg1.PSEL.value) == 1, "reg1 must be selected for address 0x0"
    assert int(reg2.PSEL.value) == 0, "reg2 should not be selected"
    assert int(reg2b.PSEL.value) == 0, "reg2b should not be selected"

    # Reset
    s_apb.PSEL.value = 0
    s_apb.PENABLE.value = 0
    reg1.PREADY.value = 0
    await Timer(1, units="ns")

    # Write to address 0x10 (should select reg2)
    reg2.PREADY.value = 1
    s_apb.PADDR.value = 0x10
    s_apb.PWDATA.value = 0x22222222
    s_apb.PSTRB.value = 0xF
    s_apb.PWRITE.value = 1
    s_apb.PSEL.value = 1
    s_apb.PENABLE.value = 1

    await Timer(1, units="ns")

    assert int(reg2.PSEL.value) == 1, "reg2 must be selected for address 0x10"
    assert int(reg1.PSEL.value) == 0, "reg1 should not be selected"
    assert int(reg2b.PSEL.value) == 0, "reg2b should not be selected"

    # Reset
    s_apb.PSEL.value = 0
    s_apb.PENABLE.value = 0
    reg2.PREADY.value = 0
    await Timer(1, units="ns")

    # Write to address 0x14 (should select reg2b)
    reg2b.PREADY.value = 1
    s_apb.PADDR.value = 0x14
    s_apb.PWDATA.value = 0x33333333
    s_apb.PSTRB.value = 0xF
    s_apb.PWRITE.value = 1
    s_apb.PSEL.value = 1
    s_apb.PENABLE.value = 1

    await Timer(1, units="ns")

    assert int(reg2b.PSEL.value) == 1, "reg2b must be selected for address 0x14"
    assert int(reg1.PSEL.value) == 0, "reg1 should not be selected"
    assert int(reg2.PSEL.value) == 0, "reg2 should not be selected"
