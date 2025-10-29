from collections import deque

from systemrdl.node import AddressableNode
from systemrdl.walker import WalkerAction

from .body import Body, StructBody
from .design_state import DesignState
from .identifier_filter import kw_filter as kwf
from .listener import BusDecoderListener


class StructGenerator(BusDecoderListener):
    def __init__(
        self,
        ds: DesignState,
    ) -> None:
        super().__init__(ds)

        self._stack: deque[Body] = deque()
        self._stack.append(StructBody("cpuif_sel_t", True, False))

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        action = super().enter_AddressableComponent(node)

        self._skip = False
        if action == WalkerAction.SkipDescendants:
            self._skip = True

        if node.children():
            # Push new body onto stack
            body = StructBody(f"cpuif_sel_{node.inst_name}_t", True, False)
            self._stack.append(body)

        return action

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        type = "logic"

        if node.children():
            body = self._stack.pop()
            if body and isinstance(body, StructBody) and not self._skip:
                self._stack.appendleft(body)
                type = body.name

        name = kwf(node.inst_name)

        if node.array_dimensions:
            for dim in node.array_dimensions:
                name = f"{name}[{dim}]"

        self._stack[-1] += f"{type} {name};"

        super().exit_AddressableComponent(node)

    def __str__(self) -> str:
        self._stack[-1] += "logic cpuif_err;"
        return "\n".join(map(str, self._stack))
