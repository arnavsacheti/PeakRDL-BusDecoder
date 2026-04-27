from collections import deque
from typing import ClassVar

from systemrdl.node import AddressableNode

from ...sv_int import SVInt
from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif
from .apb_interface import APBFlatInterface, APBSVInterface


class APBCpuifBase(BaseCpuif):
    """Shared APB3/APB4 cpuif. Variants differ by ``apb_interface_type`` and
    whether ``has_pprot`` / ``has_pstrb`` are set."""

    template_path = "apb_tmpl.sv"

    flat_interface_cls = APBFlatInterface
    sv_interface_cls = APBSVInterface
    slave_name_flat = "s_apb_"
    slave_name_sv = "s_apb"
    master_signal_prefix = "m_apb_"

    apb_interface_type: ClassVar[str] = ""  # set by concrete subclasses
    has_pprot: ClassVar[bool] = False
    has_pstrb: ClassVar[bool] = False

    sv_array_fanin_wr: ClassVar[list[tuple[str, str, str]]] = [
        ("cpuif_wr_ack", "_fanin_ready", "PREADY"),
        ("cpuif_wr_err", "_fanin_err", "PSLVERR"),
    ]
    sv_array_fanin_rd: ClassVar[list[tuple[str, str, str]]] = [
        ("cpuif_rd_ack", "_fanin_ready", "PREADY"),
        ("cpuif_rd_err", "_fanin_err", "PSLVERR"),
        ("cpuif_rd_data", "_fanin_data", "PRDATA"),
    ]

    def fanout(self, node: AddressableNode, array_stack: deque[int]) -> str:
        fanout: dict[str, str] = {}

        addr_width = f"{self.exp.ds.module_name.upper()}_{node.inst_name.upper()}_ADDR_WIDTH"

        sel_path = get_indexed_path(self.exp.ds.top_node, node, "gi")
        sel_expr = f"cpuif_wr_sel.{sel_path}|cpuif_rd_sel.{sel_path}"

        fanout[self.signal("PSEL", node, "gi")] = sel_expr
        fanout[self.signal("PENABLE", node, "gi")] = f"({sel_expr}) & {self.signal('PENABLE')}"
        fanout[self.signal("PWRITE", node, "gi")] = f"cpuif_wr_sel.{sel_path}"

        if self._can_truncate_addr(node, array_stack):
            # Size is a power of 2 and aligned, so we can directly use the address bits as the slave address
            addr_value = f"{self.signal('PADDR')}[{addr_width}-1:0]"
        else:
            addr_comp = [self.signal("PADDR"), f"{SVInt(node.raw_absolute_address, self.addr_width)}"]
            for i, stride in enumerate(array_stack):
                addr_comp.append(f"{self.addr_width}'(gi{i}*{SVInt(stride, self.addr_width)})")
            addr_value = f"{addr_width}'({' - '.join(addr_comp)})"
        fanout[self.signal("PADDR", node, "gi")] = f"({sel_expr}) ? {addr_value} : '0"

        if self.has_pprot:
            fanout[self.signal("PPROT", node, "gi")] = f"({sel_expr}) ? {self.signal('PPROT')} : '0"
        fanout[self.signal("PWDATA", node, "gi")] = f"({sel_expr}) ? cpuif_wr_data : '0"
        if self.has_pstrb:
            fanout[self.signal("PSTRB", node, "gi")] = f"({sel_expr}) ? cpuif_wr_byte_en : '0"

        return "\n".join(f"assign {lhs} = {rhs};" for lhs, rhs in fanout.items())

    def _default_fanin_wr(self, node: AddressableNode | None, *, error: bool) -> str:
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
        return "\n".join(f"{lhs} = {rhs};" for lhs, rhs in fanin.items())

    def _default_fanin_rd(self, node: AddressableNode | None, *, error: bool) -> str:
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
        return "\n".join(f"{lhs} = {rhs};" for lhs, rhs in fanin.items())


class APB3CpuifFlat(APBCpuifBase):
    apb_interface_type = "apb3_intf"


class APB3Cpuif(APB3CpuifFlat):
    use_sv_interface = True


class APB4CpuifFlat(APBCpuifBase):
    apb_interface_type = "apb4_intf"
    has_pprot = True
    has_pstrb = True


class APB4Cpuif(APB4CpuifFlat):
    use_sv_interface = True
