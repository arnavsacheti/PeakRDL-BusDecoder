from collections import deque
from typing import TYPE_CHECKING, overload

from systemrdl.node import AddressableNode

from ...sv_int import SVInt
from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif
from .axi4_lite_interface import AXI4LiteFlatInterface

if TYPE_CHECKING:
    from ...exporter import BusDecoderExporter


class AXI4LiteCpuifFlat(BaseCpuif):
    """Verilator-friendly variant that flattens the AXI4-Lite interface ports."""

    template_path = "axi4_lite_tmpl.sv"

    def __init__(self, exp: "BusDecoderExporter") -> None:
        super().__init__(exp)
        self._interface = AXI4LiteFlatInterface(self)

    @property
    def is_interface(self) -> bool:
        return self._interface.is_interface

    @property
    def port_declaration(self) -> str:
        """Returns the port declaration for the AXI4-Lite interface."""
        return self._interface.get_port_declaration("s_axil_", "m_axil_")

    @overload
    def signal(self, signal: str, node: None = None, indexer: None = None) -> str: ...
    @overload
    def signal(self, signal: str, node: AddressableNode, indexer: str | None = None) -> str: ...
    def signal(self, signal: str, node: AddressableNode | None = None, indexer: str | None = None) -> str:
        return self._interface.signal(signal, node, indexer)

    def fanout(self, node: AddressableNode, array_stack: deque[int]) -> str:
        fanout: dict[str, str] = {}
        waddr_comp = [f"{self.signal('AWADDR')}", f"{SVInt(node.raw_absolute_address, self.addr_width)}"]
        raddr_comp = [f"{self.signal('ARADDR')}", f"{SVInt(node.raw_absolute_address, self.addr_width)}"]
        for i, stride in enumerate(array_stack):
            offset = f"{self.addr_width}'(gi{i}*{SVInt(stride, self.addr_width)})"
            waddr_comp.append(offset)
            raddr_comp.append(offset)

        addr_width = f"{self.exp.ds.module_name.upper()}_{node.inst_name.upper()}_ADDR_WIDTH"

        wr_sel = f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        rd_sel = f"cpuif_rd_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"

        # Write address channel
        fanout[self.signal("AWVALID", node, "gi")] = wr_sel
        if self._can_truncate_addr(node, array_stack):
            # Size is a power of 2 and aligned, so we can directly use the address bits as the slave address
            fanout[self.signal("AWADDR", node, "gi")] = (
                f"{self.signal('AWADDR')}[{addr_width}-1:0]"
            )
        else:
            fanout[self.signal("AWADDR", node, "gi")] = (
                f"{addr_width}'({'-'.join(waddr_comp)})"
            )
        fanout[self.signal("AWPROT", node, "gi")] = self.signal("AWPROT")

        # Write data channel
        fanout[self.signal("WVALID", node, "gi")] = wr_sel
        fanout[self.signal("WDATA", node, "gi")] = "cpuif_wr_data"
        fanout[self.signal("WSTRB", node, "gi")] = "cpuif_wr_byte_en"

        # Write response channel (master -> slave)
        fanout[self.signal("BREADY", node, "gi")] = self.signal("BREADY")

        # Read address channel
        fanout[self.signal("ARVALID", node, "gi")] = rd_sel
        if self._can_truncate_addr(node, array_stack):
            # Size is a power of 2 and aligned, so we can directly use the address bits as the slave address
            fanout[self.signal("ARADDR", node, "gi")] = (
                f"{self.signal('ARADDR')}[{addr_width}-1:0]"
            )
        else:
            fanout[self.signal("ARADDR", node, "gi")] = (
                f"{addr_width}'({'-'.join(raddr_comp)})"
            )
        fanout[self.signal("ARPROT", node, "gi")] = self.signal("ARPROT")

        # Read data channel (master -> slave)
        fanout[self.signal("RREADY", node, "gi")] = self.signal("RREADY")

        return "\n".join(f"assign {lhs} = {rhs};" for lhs, rhs in fanout.items())

    def fanin_wr(self, node: AddressableNode | None = None, *, error: bool = False) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_wr_ack"] = "'0"
            fanin["cpuif_wr_err"] = "'0"
            if error:
                fanin["cpuif_wr_ack"] = "'1"
                fanin["cpuif_wr_err"] = "cpuif_wr_sel.cpuif_err"
        else:
            # Read side: ack comes from RVALID; err if RRESP[1] is set (SLVERR/DECERR)
            fanin["cpuif_wr_ack"] = self.signal("BVALID", node, "i")
            fanin["cpuif_wr_err"] = f"{self.signal('BRESP', node, 'i')}[1]"

        return "\n".join(f"{lhs} = {rhs};" for lhs, rhs in fanin.items())

    def fanin_rd(self, node: AddressableNode | None = None, *, error: bool = False) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_ack"] = "'0"
            fanin["cpuif_rd_err"] = "'0"
            fanin["cpuif_rd_data"] = "'0"
            if error:
                fanin["cpuif_rd_ack"] = "'1"
                fanin["cpuif_rd_err"] = "cpuif_rd_sel.cpuif_err"
        else:
            fanin["cpuif_rd_ack"] = self.signal("RVALID", node, "i")
            fanin["cpuif_rd_err"] = f"{self.signal('RRESP', node, 'i')}[1]"
            fanin["cpuif_rd_data"] = self.signal("RDATA", node, "i")

        return "\n".join(f"{lhs} = {rhs};" for lhs, rhs in fanin.items())
