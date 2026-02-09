from collections import deque
from typing import TYPE_CHECKING

from systemrdl.node import AddressableNode
from systemrdl.walker import WalkerAction

from ..body import Body, CombinationalBody, ForLoopBody, IfBody
from ..design_state import DesignState
from ..listener import BusDecoderListener
from ..utils import get_indexed_path

if TYPE_CHECKING:
    from .base_cpuif import BaseCpuif


class FaninGenerator(BusDecoderListener):
    def __init__(self, ds: DesignState, cpuif: "BaseCpuif") -> None:
        super().__init__(ds)
        self._cpuif = cpuif

        self._stack: deque[Body] = deque()
        cb = CombinationalBody()
        cb += cpuif.fanin_wr()
        cb += cpuif.fanin_rd()
        self._stack.append(cb)

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        action = super().enter_AddressableComponent(node)

        is_unrolled_elem = self._ds.cpuif_unroll and getattr(node, "current_idx", None) is not None
        should_generate = action == WalkerAction.SkipDescendants

        if not should_generate and self._ds.max_decode_depth == 0:
            for child in node.children():
                if isinstance(child, AddressableNode):
                    break
            else:
                should_generate = True

        if node.array_dimensions and not is_unrolled_elem:
            for i in range(len(node.array_dimensions)):
                fb = ForLoopBody(
                    "int",
                    f"i{i}",
                    f"N_{node.inst_name.upper()}S_{i}"
                    if len(node.array_dimensions) > 1
                    else f"N_{node.inst_name.upper()}S",
                )
                self._stack.append(fb)

        if should_generate:
            ifb = IfBody()
            with ifb.cm(f"cpuif_wr_sel.{get_indexed_path(self._cpuif.exp.ds.top_node, node)}") as b:
                b += self._cpuif.fanin_wr(node)
            self._stack[-1] += ifb

            ifb = IfBody()
            with ifb.cm(f"cpuif_rd_sel.{get_indexed_path(self._cpuif.exp.ds.top_node, node)}") as b:
                b += self._cpuif.fanin_rd(node)
            self._stack[-1] += ifb

        return action

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        is_unrolled_elem = self._ds.cpuif_unroll and getattr(node, "current_idx", None) is not None
        if node.array_dimensions and not is_unrolled_elem:
            for _ in node.array_dimensions:
                b = self._stack.pop()
                if not b:
                    continue
                self._stack[-1] += b

        super().exit_AddressableComponent(node)

    def __str__(self) -> str:
        wr_ifb = IfBody()
        with wr_ifb.cm("cpuif_wr_sel.cpuif_err") as b:
            b += self._cpuif.fanin_wr(error=True)
        self._stack[-1] += wr_ifb

        rd_ifb = IfBody()
        with rd_ifb.cm("cpuif_rd_sel.cpuif_err") as b:
            b += self._cpuif.fanin_rd(error=True)
        self._stack[-1] += rd_ifb

        return "\n".join(map(str, self._stack))
