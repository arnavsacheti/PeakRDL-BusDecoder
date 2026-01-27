from collections import deque
from typing import TYPE_CHECKING

from systemrdl.node import AddressableNode

from ...body import SupportsStr
from ...sv_assertion import Operator, SVAssertion
from ...sv_int import SVInt
from ...utils import clog2, get_indexed_path
from ..base_cpuif import BaseCpuif
from .apb3_interface import APB3FlatInterface

if TYPE_CHECKING:
    from ...exporter import BusDecoderExporter


class APB3CpuifFlat(BaseCpuif):
    template_path = "apb3_tmpl.sv"

    def __init__(self, exp: "BusDecoderExporter") -> None:
        super().__init__(exp)
        self._interface = APB3FlatInterface(self)

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

    def fanout(self, node: AddressableNode, array_stack: deque[int]) -> str:
        fanout: dict[str, str] = {}
        addr_comp = [f"{self.signal('PADDR')}"]
        for i, stride in enumerate(array_stack):
            addr_comp.append(f"(gi{i}*{SVInt(stride, self.addr_width)})")

        idx = "gi" if self.check_is_array(node) else None
        fanout[self.signal("PSEL", node, idx)] = (
            f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}|cpuif_rd_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        )
        fanout[self.signal("PENABLE", node, idx)] = self.signal("PENABLE")
        fanout[self.signal("PWRITE", node, idx)] = f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        fanout[self.signal("PADDR", node, idx)] = f"{{{'-'.join(addr_comp)}}}[{clog2(node.size) - 1}:0]"
        fanout[self.signal("PWDATA", node, idx)] = "cpuif_wr_data"

        return "\n".join(f"assign {kv[0]} = {kv[1]};" for kv in fanout.items())

    def fanin(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_ack"] = "'0"
            fanin["cpuif_rd_err"] = "'0"
        else:
            idx = "i" if self.check_is_array(node) else None
            fanin["cpuif_rd_ack"] = self.signal("PREADY", node, idx)
            fanin["cpuif_rd_err"] = self.signal("PSLVERR", node, idx)

        return "\n".join(f"{kv[0]} = {kv[1]};" for kv in fanin.items())

    def readback(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_data"] = "'0"
        else:
            idx = "i" if self.check_is_array(node) else None
            fanin["cpuif_rd_data"] = self.signal("PRDATA", node, idx)

        return "\n".join(f"{kv[0]} = {kv[1]};" for kv in fanin.items())

    def get_initial_assertions(self) -> list[SupportsStr]:
        """
        Optional list of initial assertions to include in the CPU interface module
        """
        initial_assertions = super().get_initial_assertions()

        # Bad Address Width Assertion for APB4
        initial_assertions.append(
            SVAssertion(
                f"$bits({self.signal('PADDR')})",
                f"{self.exp.ds.package_name}::{self.exp.ds.module_name.upper()}_MIN_ADDR_WIDTH",
                operator=Operator.GREATER_EQUAL,
                name="assert_apb4_addr_width",
                message="APB4 address width is less than the minimum required width.",
            )
        )

        # Bad Data Width Assertion for APB4
        initial_assertions.append(
            SVAssertion(
                f"$bits({self.signal('PWDATA')})",
                f"{self.exp.ds.package_name}::{self.exp.ds.module_name.upper()}_DATA_WIDTH",
                operator=Operator.EQUAL,
                name="assert_apb4_data_width",
                message="APB4 data width is not equal to the required width.",
            )
        )

        return initial_assertions
