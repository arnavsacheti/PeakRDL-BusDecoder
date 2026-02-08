from collections import deque
from typing import TYPE_CHECKING

from systemrdl.node import AddressableNode

from ...sv_int import SVInt
from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif
from .apb4_interface import APB4FlatInterface, APB4SVInterface

if TYPE_CHECKING:
    from ...exporter import BusDecoderExporter


class APB4CpuifFlat(BaseCpuif):
    template_path = "apb4_tmpl.sv"

    def __init__(self, exp: "BusDecoderExporter") -> None:
        super().__init__(exp)

        self._interface = APB4FlatInterface(self)

    @property
    def is_interface(self) -> bool:
        """
        Returns True if the CPU interface is an interface, False if it is a module.
        """
        return self._interface.is_interface

    @property
    def port_declaration(self) -> str:
        """
        Returns the port declaration for the APB4 interface.
        """
        return self._interface.get_port_declaration("s_apb_", "m_apb_")

    def signal(
        self,
        signal: str,
        node: AddressableNode | None = None,
        idx: str | int | None = None,
    ) -> str:
        return self._interface.signal(signal, node, idx)

    def fanout(self, node: AddressableNode, array_stack: deque[int]) -> str:
        fanout: dict[str, str] = {}

        addr_width = f"{self.exp.ds.module_name.upper()}_{node.inst_name.upper()}_ADDR_WIDTH"

        fanout[self.signal("PSEL", node, "gi")] = (
            f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}|cpuif_rd_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        )
        fanout[self.signal("PENABLE", node, "gi")] = self.signal("PENABLE")
        fanout[self.signal("PWRITE", node, "gi")] = (
            f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        )
        if self._can_truncate_addr(node, array_stack):
            # Size is a power of 2 and aligned, so we can directly use the address bits as the slave address
            fanout[self.signal("PADDR", node, "gi")] = f"{self.signal('PADDR')}[{addr_width}-1:0]"
        else:
            addr_comp = [f"{self.signal('PADDR')}", f"{SVInt(node.raw_absolute_address, self.addr_width)}"]
            for i, stride in enumerate(array_stack):
                addr_comp.append(f"{self.addr_width}'(gi{i}*{SVInt(stride, self.addr_width)})")

            fanout[self.signal("PADDR", node, "gi")] = f"{addr_width}'({' - '.join(addr_comp)})"
        fanout[self.signal("PPROT", node, "gi")] = self.signal("PPROT")
        fanout[self.signal("PWDATA", node, "gi")] = "cpuif_wr_data"
        fanout[self.signal("PSTRB", node, "gi")] = "cpuif_wr_byte_en"

        return "\n".join(f"assign {kv[0]} = {kv[1]};" for kv in fanout.items())

    def fanin_wr(self, node: AddressableNode | None = None, *, error: bool = False) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_wr_ack"] = "'0"
            fanin["cpuif_wr_err"] = "'0"
            if error:
                fanin["cpuif_wr_ack"] = "'1"
                fanin["cpuif_wr_err"] = "cpuif_wr_sel.cpuif_err"
        else:
            fanin["cpuif_wr_ack"] = self.signal("PREADY", node, "i")
            fanin["cpuif_wr_err"] = self.signal("PSLVERR", node, "i")
        return "\n".join(f"{kv[0]} = {kv[1]};" for kv in fanin.items())

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
            fanin["cpuif_rd_ack"] = self.signal("PREADY", node, "i")
            fanin["cpuif_rd_err"] = self.signal("PSLVERR", node, "i")
            fanin["cpuif_rd_data"] = self.signal("PRDATA", node, "i")

        return "\n".join(f"{kv[0]} = {kv[1]};" for kv in fanin.items())


class APB4Cpuif(APB4CpuifFlat):
    def __init__(self, exp: "BusDecoderExporter") -> None:
        super().__init__(exp)
        self._interface = APB4SVInterface(self)

    @property
    def port_declaration(self) -> str:
        """
        Returns the port declaration for the APB4 interface.
        """
        return self._interface.get_port_declaration("s_apb", "m_apb_")

    def fanin_wr(self, node: AddressableNode | None = None, *, error: bool = False) -> str:
        fanin_wr = super().fanin_wr(node, error=error)
        if node is not None and self.is_interface and node.is_array and node.array_dimensions:
            fanin: dict[str, str] = {}
            # Generate array index string [i0][i1]... for the intermediate signal
            array_idx = "".join(f"[i{i}]" for i in range(len(node.array_dimensions)))
            fanin["cpuif_wr_ack"] = f"{node.inst_name}_fanin_ready{array_idx}"
            fanin["cpuif_wr_err"] = f"{node.inst_name}_fanin_err{array_idx}"

            fanin_wr += "\n" + "\n".join(f"{kv[0]} = {kv[1]};" for kv in fanin.items())
        return fanin_wr

    def fanin_rd(self, node: AddressableNode | None = None, *, error: bool = False) -> str:
        fanin_rd = super().fanin_rd(node, error=error)
        if node is not None and self.is_interface and node.is_array and node.array_dimensions:
            fanin: dict[str, str] = {}
            # Generate array index string [i0][i1]... for the intermediate signal
            array_idx = "".join(f"[i{i}]" for i in range(len(node.array_dimensions)))
            fanin["cpuif_rd_ack"] = f"{node.inst_name}_fanin_ready{array_idx}"
            fanin["cpuif_rd_err"] = f"{node.inst_name}_fanin_err{array_idx}"
            fanin["cpuif_rd_data"] = f"{node.inst_name}_fanin_data{array_idx}"
            fanin_rd = "\n" + "\n".join(f"{kv[0]} = {kv[1]};" for kv in fanin.items()) + "\n" + fanin_rd
        return fanin_rd

    def fanin_intermediate_assignments(
        self, node: AddressableNode, inst_name: str, array_idx: str, master_prefix: str, indexed_path: str
    ) -> list[str]:
        """Generate intermediate signal assignments for APB4 interface arrays."""
        return [
            f"assign {inst_name}_fanin_ready{array_idx} = {master_prefix}{indexed_path}.PREADY;",
            f"assign {inst_name}_fanin_err{array_idx} = {master_prefix}{indexed_path}.PSLVERR;",
            f"assign {inst_name}_fanin_data{array_idx} = {master_prefix}{indexed_path}.PRDATA;",
        ]
