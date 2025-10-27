"""APB3 smoke tests for generated multi-register design."""

import cocotb
from cocotb.triggers import Timer

WRITE_ADDR = 0x0
READ_ADDR = 0x8
WRITE_DATA = 0xCAFEBABE
READ_DATA = 0x0BAD_F00D


class _Apb3SlaveShim:
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


class _Apb3MasterShim:
    def __init__(self, dut, base: str):
        self.PSEL = getattr(dut, f"{base}_PSEL")
        self.PENABLE = getattr(dut, f"{base}_PENABLE")
        self.PWRITE = getattr(dut, f"{base}_PWRITE")
        self.PADDR = getattr(dut, f"{base}_PADDR")
        self.PWDATA = getattr(dut, f"{base}_PWDATA")
        self.PRDATA = getattr(dut, f"{base}_PRDATA")
        self.PREADY = getattr(dut, f"{base}_PREADY")
        self.PSLVERR = getattr(dut, f"{base}_PSLVERR")


def _apb3_slave(dut):
    return getattr(dut, "s_apb", None) or _Apb3SlaveShim(dut)


def _apb3_master(dut, base: str):
    return getattr(dut, base, None) or _Apb3MasterShim(dut, base)


@cocotb.test()
async def test_apb3_read_write_paths(dut):
    """Exercise APB3 slave interface and observe master fanout."""
    s_apb = _apb3_slave(dut)
    masters = {
        "reg1": _apb3_master(dut, "m_apb_reg1"),
        "reg2": _apb3_master(dut, "m_apb_reg2"),
        "reg3": _apb3_master(dut, "m_apb_reg3"),
    }

    s_apb.PSEL.value = 0
    s_apb.PENABLE.value = 0
    s_apb.PWRITE.value = 0
    s_apb.PADDR.value = 0
    s_apb.PWDATA.value = 0

    for master in masters.values():
        master.PRDATA.value = 0
        master.PREADY.value = 0
        master.PSLVERR.value = 0

    await Timer(1, units="ns")

    # Write to reg1
    masters["reg1"].PREADY.value = 1
    s_apb.PADDR.value = WRITE_ADDR
    s_apb.PWDATA.value = WRITE_DATA
    s_apb.PWRITE.value = 1
    s_apb.PSEL.value = 1
    s_apb.PENABLE.value = 1

    await Timer(1, units="ns")

    assert int(masters["reg1"].PSEL.value) == 1, "reg1 should be selected for write"
    assert int(masters["reg1"].PWRITE.value) == 1, "Write should propagate to master"
    assert int(masters["reg1"].PADDR.value) == WRITE_ADDR, "Address should reach selected master"
    assert int(masters["reg1"].PWDATA.value) == WRITE_DATA, "Write data should fan out"

    for name, master in masters.items():
        if name != "reg1":
            assert int(master.PSEL.value) == 0, f"{name} must idle during reg1 write"

    assert int(s_apb.PREADY.value) == 1, "Ready must reflect selected master"
    assert int(s_apb.PSLVERR.value) == 0, "Write should not signal error"

    s_apb.PSEL.value = 0
    s_apb.PENABLE.value = 0
    s_apb.PWRITE.value = 0
    masters["reg1"].PREADY.value = 0
    await Timer(1, units="ns")

    # Read from reg3
    masters["reg3"].PRDATA.value = READ_DATA
    masters["reg3"].PREADY.value = 1
    masters["reg3"].PSLVERR.value = 0

    s_apb.PADDR.value = READ_ADDR
    s_apb.PSEL.value = 1
    s_apb.PENABLE.value = 1
    s_apb.PWRITE.value = 0

    await Timer(1, units="ns")

    assert int(masters["reg3"].PSEL.value) == 1, "reg3 should be selected for read"
    assert int(masters["reg3"].PWRITE.value) == 0, "Read should clear write"
    assert int(masters["reg3"].PADDR.value) == READ_ADDR, "Address should reach read target"

    for name, master in masters.items():
        if name != "reg3":
            assert int(master.PSEL.value) == 0, f"{name} must idle during reg3 read"

    assert int(s_apb.PRDATA.value) == READ_DATA, "Read data should return to slave"
    assert int(s_apb.PREADY.value) == 1, "Read should acknowledge"
    assert int(s_apb.PSLVERR.value) == 0, "Read should not signal error"

    s_apb.PSEL.value = 0
    s_apb.PENABLE.value = 0
    masters["reg3"].PREADY.value = 0
    await Timer(1, units="ns")
