from collections import deque
from typing import TYPE_CHECKING

from systemrdl.node import AddressableNode
from systemrdl.walker import WalkerAction

from ..body import Body, ForLoopBody
from ..design_state import DesignState
from ..listener import BusDecoderListener

if TYPE_CHECKING:
    from .base_cpuif import BaseCpuif


class FanoutGenerator(BusDecoderListener):
    walk_unrolled = True

    def __init__(self, ds: DesignState, cpuif: "BaseCpuif") -> None:
        super().__init__(ds)
        self._cpuif = cpuif

        self._stack: deque[Body] = deque()
        self._stack.append(Body())

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        action = super().enter_AddressableComponent(node)

        should_generate = action == WalkerAction.SkipDescendants

        if self.is_rolled_array(node):
            assert node.array_dimensions is not None
            base = self.loop_base_index(node)
            for i, dim in enumerate(node.array_dimensions, base):
                fb = ForLoopBody(
                    "genvar",
                    f"gi{i}",
                    self._ds.resolve_loop_bound(node, i - base, dim),
                )
                self._stack.append(fb)

        if should_generate:
            self._stack[-1] += self._cpuif.fanout(node, self._array_stride_stack)

        return action

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        if self.is_rolled_array(node):
            assert node.array_dimensions is not None
            for _ in node.array_dimensions:
                b = self._stack.pop()
                if not b:
                    continue
                self._stack[-1] += b

        super().exit_AddressableComponent(node)

    def __str__(self) -> str:
        return "\n".join(map(str, self._stack))
