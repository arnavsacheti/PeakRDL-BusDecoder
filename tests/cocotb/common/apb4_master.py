"""APB4 Master Bus Functional Model for cocotb."""

import cocotb
from cocotb.triggers import RisingEdge, Timer


class APB4Master:
    """APB4 Master Bus Functional Model."""

    def __init__(self, dut, name, clock):
        """
        Initialize APB4 Master.

        Args:
            dut: The device under test
            name: Signal name prefix (e.g., 's_apb')
            clock: Clock signal to use for synchronization
        """
        self.dut = dut
        self.clock = clock
        self.name = name

        # Get signals
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
        """
        Perform APB4 write transaction.

        Args:
            addr: Address to write to
            data: Data to write
            strb: Byte strobe mask (default: all bytes enabled)

        Returns:
            True if write succeeded, False if error
        """
        # Calculate strobe if not provided
        if strb is None:
            data_width_bytes = len(self.pwdata) // 8
            strb = (1 << data_width_bytes) - 1

        # Setup phase
        await RisingEdge(self.clock)
        self.psel.value = 1
        self.penable.value = 0
        self.pwrite.value = 1
        self.paddr.value = addr
        self.pwdata.value = data
        self.pstrb.value = strb
        self.pprot.value = 0

        # Access phase
        await RisingEdge(self.clock)
        self.penable.value = 1

        # Wait for ready
        while True:
            await RisingEdge(self.clock)
            if self.pready.value == 1:
                error = self.pslverr.value == 1
                break

        # Return to idle
        self.psel.value = 0
        self.penable.value = 0

        return not error

    async def read(self, addr):
        """
        Perform APB4 read transaction.

        Args:
            addr: Address to read from

        Returns:
            Tuple of (data, error) where error is True if read failed
        """
        # Setup phase
        await RisingEdge(self.clock)
        self.psel.value = 1
        self.penable.value = 0
        self.pwrite.value = 0
        self.paddr.value = addr
        self.pprot.value = 0

        # Access phase
        await RisingEdge(self.clock)
        self.penable.value = 1

        # Wait for ready
        while True:
            await RisingEdge(self.clock)
            if self.pready.value == 1:
                data = self.prdata.value.integer
                error = self.pslverr.value == 1
                break

        # Return to idle
        self.psel.value = 0
        self.penable.value = 0

        return data, error
