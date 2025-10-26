from typing import TYPE_CHECKING, overload

from systemrdl.node import AddressableNode

from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif
from .axi4lite_interface import AXI4LiteFlatInterface

if TYPE_CHECKING:
    from ...exporter import BusDecoderExporter


class AXI4LiteCpuifFlat(AXI4LiteCpuif):
    """Verilator-friendly variant that flattens the AXI4-Lite interface ports."""

    template_path = "axi4lite_tmpl.sv"

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
    def signal(self, signal: str, node: AddressableNode, indexer: str) -> str: ...
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
            return f"s_axil_{signal}"

        base = f"m_axil_{node.inst_name}_{signal}"
        if not self.check_is_array(node):
            if node.current_idx is not None:
                return f"{base}_{'_'.join(map(str, node.current_idx))}"
            return base

        if indexer is None:
            return f"{base}[N_{node.inst_name.upper()}S]"
        return f"{base}[{indexer}]"
