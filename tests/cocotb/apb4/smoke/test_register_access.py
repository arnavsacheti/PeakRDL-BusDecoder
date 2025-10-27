"""APB4 smoke tests using generated multi-register design."""

import cocotb
from cocotb.triggers import Timer

WRITE_ADDR = 0x4
READ_ADDR = 0x8
WRITE_DATA = 0x1234_5678
READ_DATA = 0x89AB_CDEF


class _Apb4SlaveShim:
    def __init__(self, dut):
        prefix = "s_apb"
        self.PSEL = getattr(dut, f"{prefix}_PSELx")
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
        self.PSEL = getattr(dut, f"{base}_PSELx")
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
async def test_apb4_read_write_paths(dut):
    """Drive APB4 slave signals and observe master activity."""
    s_apb = _apb4_slave(dut)
    masters = {
        "reg1": _apb4_master(dut, "m_apb_reg1"),
        "reg2": _apb4_master(dut, "m_apb_reg2"),
        "reg3": _apb4_master(dut, "m_apb_reg3"),
    }

    # Default slave side inputs
    s_apb.PSEL.value = 0
    s_apb.PENABLE.value = 0
    s_apb.PWRITE.value = 0
    s_apb.PADDR.value = 0
    s_apb.PWDATA.value = 0
    s_apb.PPROT.value = 0
    s_apb.PSTRB.value = 0

    for master in masters.values():
        master.PRDATA.value = 0
        master.PREADY.value = 0
        master.PSLVERR.value = 0

    await Timer(1, units="ns")

    # ------------------------------------------------------------------
    # Write transfer to reg2
    # ------------------------------------------------------------------
    masters["reg2"].PREADY.value = 1
    s_apb.PADDR.value = WRITE_ADDR
    s_apb.PWDATA.value = WRITE_DATA
    s_apb.PSTRB.value = 0xF
    s_apb.PPROT.value = 0
    s_apb.PWRITE.value = 1
    s_apb.PSEL.value = 1
    s_apb.PENABLE.value = 1

    await Timer(1, units="ns")

    assert int(masters["reg2"].PSEL.value) == 1, "reg2 must be selected for write"
    assert int(masters["reg2"].PWRITE.value) == 1, "Write strobes should propagate"
    assert int(masters["reg2"].PADDR.value) == WRITE_ADDR, "Address should fan out"
    assert int(masters["reg2"].PWDATA.value) == WRITE_DATA, "Write data should fan out"

    for name, master in masters.items():
        if name != "reg2":
            assert int(master.PSEL.value) == 0, f"{name} should remain idle on write"

    assert int(s_apb.PREADY.value) == 1, "Ready should mirror selected master"
    assert int(s_apb.PSLVERR.value) == 0, "No error expected on successful write"

    # Return to idle
    s_apb.PSEL.value = 0
    s_apb.PENABLE.value = 0
    s_apb.PWRITE.value = 0
    masters["reg2"].PREADY.value = 0
    await Timer(1, units="ns")

    # ------------------------------------------------------------------
    # Read transfer from reg3
    # ------------------------------------------------------------------
    masters["reg3"].PRDATA.value = READ_DATA
    masters["reg3"].PREADY.value = 1
    masters["reg3"].PSLVERR.value = 0

    s_apb.PADDR.value = READ_ADDR
    s_apb.PSEL.value = 1
    s_apb.PENABLE.value = 1
    s_apb.PWRITE.value = 0

    await Timer(1, units="ns")

    assert int(masters["reg3"].PSEL.value) == 1, "reg3 must be selected for read"
    assert int(masters["reg3"].PWRITE.value) == 0, "Read should deassert write"
    assert int(masters["reg3"].PADDR.value) == READ_ADDR, "Read address should propagate"

    for name, master in masters.items():
        if name != "reg3":
            assert int(master.PSEL.value) == 0, f"{name} should remain idle on read"

    assert int(s_apb.PRDATA.value) == READ_DATA, "Read data should return from master"
    assert int(s_apb.PREADY.value) == 1, "Ready must follow selected master"
    assert int(s_apb.PSLVERR.value) == 0, "No error expected on successful read"

    # Back to idle
    s_apb.PSEL.value = 0
    s_apb.PENABLE.value = 0
    masters["reg3"].PREADY.value = 0
    await Timer(1, units="ns")
