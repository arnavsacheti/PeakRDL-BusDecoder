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
        cb += cpuif.fanin()
        cb += cpuif.readback()
        self._stack.append(cb)

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        action = super().enter_AddressableComponent(node)

        should_generate = action == WalkerAction.SkipDescendants
        if not should_generate and self._ds.max_decode_depth == 0:
            for child in node.children():
                if isinstance(child, AddressableNode):
                    break
            else:
                should_generate = True

        if not should_generate:
            return action

        if node.array_dimensions:
            for i, dim in enumerate(node.array_dimensions):
                fb = ForLoopBody(
                    "int",
                    f"i{i}",
                    dim,
                )
                self._stack.append(fb)

        ifb = IfBody()
        with ifb.cm(
            f"cpuif_rd_sel.{get_indexed_path(self._cpuif.exp.ds.top_node, node)} || cpuif_wr_sel.{get_indexed_path(self._cpuif.exp.ds.top_node, node)}"
        ) as b:
            b += self._cpuif.fanin(node)
        self._stack[-1] += ifb

        ifb = IfBody()
        with ifb.cm(f"cpuif_rd_sel.{get_indexed_path(self._cpuif.exp.ds.top_node, node)}") as b:
            b += self._cpuif.readback(node)
        self._stack[-1] += ifb

        return action

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        if node.array_dimensions:
            for _ in node.array_dimensions:
                b = self._stack.pop()
                if not b:
                    continue
                self._stack[-1] += b

        super().exit_AddressableComponent(node)

    def __str__(self) -> str:
        return "\n".join(map(str, self._stack))
