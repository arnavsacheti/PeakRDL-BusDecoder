"""Generate selected downstream request-channel READY fanin.

AXI4-Lite request dispatch uses a latched destination that is independent of
the response-queue head. This generator mirrors :mod:`fanin_gen`, but selects
the child currently receiving a request and folds back AWREADY/WREADY/ARREADY.
"""

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


class ReadyFaninGenerator(BusDecoderListener):
    """Fold READY from the selected downstream AXI4-Lite request target."""

    walk_unrolled = True

    def __init__(self, ds: DesignState, cpuif: "BaseCpuif") -> None:
        super().__init__(ds)
        self._cpuif = cpuif
        self._stack: deque[Body] = deque()
        cb = CombinationalBody()
        cb += cpuif.ready_fanin_wr()
        cb += cpuif.ready_fanin_rd()
        self._stack.append(cb)

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        action = super().enter_AddressableComponent(node)
        should_generate = action == WalkerAction.SkipDescendants

        if self.is_rolled_array(node):
            assert node.array_dimensions is not None
            base = self.loop_base_index(node)
            for i, dim in enumerate(node.array_dimensions, base):
                self._stack.append(
                    ForLoopBody(
                        "int",
                        f"i{i}",
                        self._ds.resolve_loop_bound(node, i - base, dim),
                    )
                )

        if should_generate:
            path = get_indexed_path(self._cpuif.exp.ds.top_node, node)

            wr_if = IfBody()
            with wr_if.cm(f"axil_wr_issue_sel.{path}") as body:
                body += self._cpuif.ready_fanin_wr(node)
            self._stack[-1] += wr_if

            rd_if = IfBody()
            with rd_if.cm(f"axil_rd_issue_sel.{path}") as body:
                body += self._cpuif.ready_fanin_rd(node)
            self._stack[-1] += rd_if

        return action

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        if self.is_rolled_array(node):
            assert node.array_dimensions is not None
            for _ in node.array_dimensions:
                body = self._stack.pop()
                if body:
                    self._stack[-1] += body
        super().exit_AddressableComponent(node)

    def __str__(self) -> str:
        return "\n".join(map(str, self._stack))
