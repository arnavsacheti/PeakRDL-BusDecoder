from collections import deque

from systemrdl.node import AddressableNode
from systemrdl.walker import WalkerAction

from .body import StructBody
from .design_state import DesignState
from .identifier_filter import kw_filter as kwf
from .listener import BusDecoderListener


class StructGenerator(BusDecoderListener):
    def __init__(
        self,
        ds: DesignState,
    ) -> None:
        super().__init__(ds)

        self._stack: list[StructBody] = [StructBody("cpuif_sel_t", True, False)]
        self._struct_defs: list[StructBody] = []
        self._created_struct_stack: deque[bool] = deque()  # Track if we created a struct for each node

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        action = super().enter_AddressableComponent(node)

        skip = action == WalkerAction.SkipDescendants

        # Only create nested struct if we're not skipping and node has addressable children
        has_addressable_children = any(isinstance(child, AddressableNode) for child in node.children())
        if has_addressable_children and not skip:
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
            if body:
                self._struct_defs.append(body)
                type = body.name

        name = kwf(node.inst_name)

        if node.array_dimensions:
            for dim in node.array_dimensions:
                name = f"{name}[{dim}]"

        self._stack[-1] += f"{type} {name};"

        super().exit_AddressableComponent(node)

    def __str__(self) -> str:
        if "logic cpuif_err;" not in self._stack[-1].lines:
            self._stack[-1] += "logic cpuif_err;"
        bodies = [str(body) for body in self._struct_defs]
        bodies.append(str(self._stack[-1]))
        return "\n".join(bodies)
