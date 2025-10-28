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
        self._created_struct_stack: deque[bool] = deque()  # Track if we created a struct for each node

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        action = super().enter_AddressableComponent(node)

        skip = action == WalkerAction.SkipDescendants

        # Only create nested struct if we're not skipping and node has children
        if node.children() and not skip:
            # Push new body onto stack
            body = StructBody(f"cpuif_sel_{node.inst_name}_t", True, False)
            self._stack.append(body)
            self._created_struct_stack.append(True)
        else:
            self._created_struct_stack.append(False)

        return action

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        type = "logic"

        # Pop the created_struct flag
        created_struct = self._created_struct_stack.pop()

        # Only pop struct body if we created one
        if created_struct:
            body = self._stack.pop()
            if body and isinstance(body, StructBody):
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
