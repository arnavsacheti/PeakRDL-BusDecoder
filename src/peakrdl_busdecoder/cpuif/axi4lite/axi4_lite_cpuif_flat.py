from typing import TYPE_CHECKING, overload

from systemrdl.node import AddressableNode

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

    def fanout(self, node: AddressableNode) -> str:
        fanout: dict[str, str] = {}

        wr_sel = f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        rd_sel = f"cpuif_rd_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"

        # Write address channel
        fanout[self.signal("AWVALID", node, "gi")] = wr_sel
        fanout[self.signal("AWADDR", node, "gi")] = self.signal("AWADDR")
        fanout[self.signal("AWPROT", node, "gi")] = self.signal("AWPROT")

        # Write data channel
        fanout[self.signal("WVALID", node, "gi")] = wr_sel
        fanout[self.signal("WDATA", node, "gi")] = "cpuif_wr_data"
        fanout[self.signal("WSTRB", node, "gi")] = "cpuif_wr_byte_en"

        # Write response channel (master -> slave)
        fanout[self.signal("BREADY", node, "gi")] = self.signal("BREADY")

        # Read address channel
        fanout[self.signal("ARVALID", node, "gi")] = rd_sel
        fanout[self.signal("ARADDR", node, "gi")] = self.signal("ARADDR")
        fanout[self.signal("ARPROT", node, "gi")] = self.signal("ARPROT")

        # Read data channel (master -> slave)
        fanout[self.signal("RREADY", node, "gi")] = self.signal("RREADY")

        return "\n".join(f"assign {lhs} = {rhs};" for lhs, rhs in fanout.items())

    def fanin(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_ack"] = "'0"
            fanin["cpuif_rd_err"] = "'0"
        else:
            # Read side: ack comes from RVALID; err if RRESP[1] is set (SLVERR/DECERR)
            fanin["cpuif_rd_ack"] = self.signal("RVALID", node, "i")
            fanin["cpuif_rd_err"] = f"{self.signal('RRESP', node, 'i')}[1]"

        return "\n".join(f"{lhs} = {rhs};" for lhs, rhs in fanin.items())

    def readback(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_data"] = "'0"
        else:
            fanin["cpuif_rd_data"] = self.signal("RDATA", node, "i")

        return "\n".join(f"{lhs} = {rhs};" for lhs, rhs in fanin.items())
