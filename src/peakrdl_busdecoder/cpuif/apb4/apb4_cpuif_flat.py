from typing import TYPE_CHECKING

from systemrdl.node import AddressableNode

from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif
from .apb4_interface import APB4FlatInterface

if TYPE_CHECKING:
    from ...exporter import BusDecoderExporter


class APB4CpuifFlat(BaseCpuif):
    template_path = "apb4_tmpl.sv"

    def __init__(self, exp: "BusDecoderExporter") -> None:
        super().__init__(exp)
        self._interface = APB4FlatInterface(self)

    @property
    def is_interface(self) -> bool:
        return self._interface.is_interface

    @property
    def port_declaration(self) -> str:
        return self._interface.get_port_declaration("s_apb_", "m_apb_")

    def signal(
        self,
        signal: str,
        node: AddressableNode | None = None,
        idx: str | int | None = None,
    ) -> str:
        return self._interface.signal(signal, node, idx)

    def fanout(self, node: AddressableNode) -> str:
        fanout: dict[str, str] = {}
        fanout[self.signal("PSEL", node, "gi")] = (
            f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}|cpuif_rd_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        )
        fanout[self.signal("PENABLE", node, "gi")] = self.signal("PENABLE")
        fanout[self.signal("PWRITE", node, "gi")] = (
            f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        )
        fanout[self.signal("PADDR", node, "gi")] = self.signal("PADDR")
        fanout[self.signal("PPROT", node, "gi")] = self.signal("PPROT")
        fanout[self.signal("PWDATA", node, "gi")] = "cpuif_wr_data"
        fanout[self.signal("PSTRB", node, "gi")] = "cpuif_wr_byte_en"

        return "\n".join(map(lambda kv: f"assign {kv[0]} = {kv[1]};", fanout.items()))

    def fanin(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_ack"] = "'0"
            fanin["cpuif_rd_err"] = "'0"
        else:
            fanin["cpuif_rd_ack"] = self.signal("PREADY", node, "i")
            fanin["cpuif_rd_err"] = self.signal("PSLVERR", node, "i")

        return "\n".join(map(lambda kv: f"{kv[0]} = {kv[1]};", fanin.items()))

    def readback(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_data"] = "'0"
        else:
            fanin["cpuif_rd_data"] = self.signal("PRDATA", node, "i")

        return "\n".join(map(lambda kv: f"{kv[0]} = {kv[1]};", fanin.items()))
