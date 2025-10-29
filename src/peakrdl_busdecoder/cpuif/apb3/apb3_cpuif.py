from typing import TYPE_CHECKING, overload

from systemrdl.node import AddressableNode

from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif
from .apb3_interface import APB3SVInterface

if TYPE_CHECKING:
    from ...exporter import BusDecoderExporter


class APB3Cpuif(BaseCpuif):
    template_path = "apb3_tmpl.sv"

    def __init__(self, exp: "BusDecoderExporter") -> None:
        super().__init__(exp)
        self._interface = APB3SVInterface(self)

    @property
    def is_interface(self) -> bool:
        return self._interface.is_interface

    @property
    def port_declaration(self) -> str:
        return self._interface.get_port_declaration("s_apb", "m_apb_")

    @overload
    def signal(self, signal: str, node: None = None, indexer: None = None) -> str: ...
    @overload
    def signal(self, signal: str, node: AddressableNode, indexer: str) -> str: ...
    def signal(self, signal: str, node: AddressableNode | None = None, indexer: str | None = None) -> str:
        return self._interface.signal(signal, node, indexer)

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
        fanout[self.signal("PWDATA", node, "gi")] = "cpuif_wr_data"

        return "\n".join(map(lambda kv: f"assign {kv[0]} = {kv[1]};", fanout.items()))

    def fanin(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_ack"] = "'0"
            fanin["cpuif_rd_err"] = "'0"
        else:
            # Use intermediate signals for interface arrays to avoid
            # non-constant indexing of interface arrays in procedural blocks
            if self.is_interface and node.is_array and node.array_dimensions:
                # Generate array index string [i0][i1]... for the intermediate signal
                array_idx = "".join(f"[i{i}]" for i in range(len(node.array_dimensions)))
                fanin["cpuif_rd_ack"] = f"{node.inst_name}_fanin_ready{array_idx}"
                fanin["cpuif_rd_err"] = f"{node.inst_name}_fanin_err{array_idx}"
            else:
                fanin["cpuif_rd_ack"] = self.signal("PREADY", node, "i")
                fanin["cpuif_rd_err"] = self.signal("PSLVERR", node, "i")

        return "\n".join(map(lambda kv: f"{kv[0]} = {kv[1]};", fanin.items()))

    def readback(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_data"] = "'0"
        else:
            # Use intermediate signals for interface arrays to avoid
            # non-constant indexing of interface arrays in procedural blocks
            if self.is_interface and node.is_array and node.array_dimensions:
                # Generate array index string [i0][i1]... for the intermediate signal
                array_idx = "".join(f"[i{i}]" for i in range(len(node.array_dimensions)))
                fanin["cpuif_rd_data"] = f"{node.inst_name}_fanin_data{array_idx}"
            else:
                fanin["cpuif_rd_data"] = self.signal("PRDATA", node, "i")

        return "\n".join(map(lambda kv: f"{kv[0]} = {kv[1]};", fanin.items()))

    def fanin_intermediate_assignments(
        self, node: AddressableNode, inst_name: str, array_idx: str, master_prefix: str, indexed_path: str
    ) -> list[str]:
        """Generate intermediate signal assignments for APB3 interface arrays."""
        return [
            f"assign {inst_name}_fanin_ready{array_idx} = {master_prefix}{indexed_path}.PREADY;",
            f"assign {inst_name}_fanin_err{array_idx} = {master_prefix}{indexed_path}.PSLVERR;",
            f"assign {inst_name}_fanin_data{array_idx} = {master_prefix}{indexed_path}.PRDATA;",
        ]
