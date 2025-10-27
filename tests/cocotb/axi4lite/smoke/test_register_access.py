"""AXI4-Lite smoke test ensuring address decode fanout works."""

import cocotb
from cocotb.triggers import Timer

WRITE_ADDR = 0x4
READ_ADDR = 0x8
WRITE_DATA = 0x1357_9BDF
READ_DATA = 0x2468_ACED


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
async def test_axi4lite_read_write_paths(dut):
    """Drive AXI4-Lite slave channels and validate master side wiring."""
    s_axil = _axil_slave(dut)
    masters = {
        "reg1": _axil_master(dut, "m_axil_reg1"),
        "reg2": _axil_master(dut, "m_axil_reg2"),
        "reg3": _axil_master(dut, "m_axil_reg3"),
    }

    # Default slave-side inputs
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

    for master in masters.values():
        master.AWREADY.value = 0
        master.WREADY.value = 0
        master.BVALID.value = 0
        master.BRESP.value = 0
        master.ARREADY.value = 0
        master.RVALID.value = 0
        master.RDATA.value = 0
        master.RRESP.value = 0

    await Timer(1, units="ns")

    # --------------------------------------------------------------
    # Write transaction targeting reg2
    # --------------------------------------------------------------
    s_axil.AWADDR.value = WRITE_ADDR
    s_axil.AWPROT.value = 0
    s_axil.AWVALID.value = 1
    s_axil.WDATA.value = WRITE_DATA
    s_axil.WSTRB.value = 0xF
    s_axil.WVALID.value = 1
    s_axil.BREADY.value = 1

    await Timer(1, units="ns")

    assert int(masters["reg2"].AWVALID.value) == 1, "reg2 AWVALID should follow slave"
    assert int(masters["reg2"].WVALID.value) == 1, "reg2 WVALID should follow slave"
    assert int(masters["reg2"].AWADDR.value) == WRITE_ADDR, "AWADDR should fan out"
    assert int(masters["reg2"].WDATA.value) == WRITE_DATA, "WDATA should fan out"
    assert int(masters["reg2"].WSTRB.value) == 0xF, "WSTRB should propagate"

    for name, master in masters.items():
        if name != "reg2":
            assert int(master.AWVALID.value) == 0, f"{name} AWVALID should stay low"
            assert int(master.WVALID.value) == 0, f"{name} WVALID should stay low"

    # Release write channel
    s_axil.AWVALID.value = 0
    s_axil.WVALID.value = 0
    s_axil.BREADY.value = 0
    await Timer(1, units="ns")

    # --------------------------------------------------------------
    # Read transaction targeting reg3
    # --------------------------------------------------------------
    masters["reg3"].RVALID.value = 1
    masters["reg3"].RDATA.value = READ_DATA
    masters["reg3"].RRESP.value = 0

    s_axil.ARADDR.value = READ_ADDR
    s_axil.ARPROT.value = 0
    s_axil.ARVALID.value = 1
    s_axil.RREADY.value = 1

    await Timer(1, units="ns")

    assert int(masters["reg3"].ARVALID.value) == 1, "reg3 ARVALID should follow slave"
    assert int(masters["reg3"].ARADDR.value) == READ_ADDR, "ARADDR should fan out"

    for name, master in masters.items():
        if name != "reg3":
            assert int(master.ARVALID.value) == 0, f"{name} ARVALID should stay low"

    assert int(s_axil.RVALID.value) == 1, "Slave should raise RVALID when master responds"
    assert int(s_axil.RDATA.value) == READ_DATA, "Read data should return to slave"
    assert int(s_axil.RRESP.value) == 0, "No error expected for read"

    # Return to idle
    s_axil.ARVALID.value = 0
    s_axil.RREADY.value = 0
    masters["reg3"].RVALID.value = 0
    await Timer(1, units="ns")
