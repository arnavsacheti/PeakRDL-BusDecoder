from typing import TYPE_CHECKING, overload

from systemrdl.node import AddressableNode

from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif
from .taxi_apb_interface import TaxiAPBSVInterface

if TYPE_CHECKING:
    from ...exporter import BusDecoderExporter


class TaxiAPBCpuif(BaseCpuif):
    template_path = "taxi_apb_tmpl.sv"

    def __init__(self, exp: "BusDecoderExporter") -> None:
        super().__init__(exp)
        self._interface = TaxiAPBSVInterface(self)
        self._interface.master_modport_name = "mst"
        self._interface.slave_modport_name = "slv"

    @property
    def is_interface(self) -> bool:
        return self._interface.is_interface

    @property
    def port_declaration(self) -> str:
        """Returns the port declaration for the APB4 interface."""
        return self._interface.get_port_declaration("s_apb", "m_apb_")

    @overload
    def signal(self, signal: str, node: None = None, indexer: None = None) -> str: ...
    @overload
    def signal(self, signal: str, node: AddressableNode, indexer: str) -> str: ...
    def signal(self, signal: str, node: AddressableNode | None = None, indexer: str | None = None) -> str:
        return self._interface.signal(signal, node, indexer)

    def fanout(self, node: AddressableNode) -> str:
        fanout: dict[str, str] = {}
        fanout[self.signal("psel", node, "gi")] = (
            f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}|cpuif_rd_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        )
        fanout[self.signal("penable", node, "gi")] = self.signal("penable")
        fanout[self.signal("pwrite", node, "gi")] = (
            f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        )
        fanout[self.signal("paddr", node, "gi")] = self.signal("paddr")
        fanout[self.signal("pprot", node, "gi")] = self.signal("pprot")
        fanout[self.signal("pwdata", node, "gi")] = "cpuif_wr_data"
        fanout[self.signal("pstrb", node, "gi")] = "cpuif_wr_byte_en"
        # no user?

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
                fanin["cpuif_rd_ack"] = self.signal("pready", node, "i")
                fanin["cpuif_rd_err"] = self.signal("pslverr", node, "i")

        # no user?
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
                fanin["cpuif_rd_data"] = self.signal("prdata", node, "i")

        return "\n".join(map(lambda kv: f"{kv[0]} = {kv[1]};", fanin.items()))

    def fanin_intermediate_assignments(
        self, node: AddressableNode, inst_name: str, array_idx: str, master_prefix: str, indexed_path: str
    ) -> list[str]:
        """Generate intermediate signal assignments for APB4 interface arrays."""
        return [
            f"assign {inst_name}_fanin_ready{array_idx} = {master_prefix}{indexed_path}.pready;",
            f"assign {inst_name}_fanin_err{array_idx} = {master_prefix}{indexed_path}.pslverr;",
            f"assign {inst_name}_fanin_data{array_idx} = {master_prefix}{indexed_path}.prdata;",
        ]
