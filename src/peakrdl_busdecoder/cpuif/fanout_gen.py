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
    def __init__(self, ds: DesignState, cpuif: "BaseCpuif") -> None:
        super().__init__(ds)
        self._cpuif = cpuif

        self._stack: deque[Body] = deque()
        self._stack.append(Body())

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
                    "genvar",
                    f"gi{i}",
                    dim,
                )
                self._stack.append(fb)

        self._stack[-1] += self._cpuif.fanout(node)

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
