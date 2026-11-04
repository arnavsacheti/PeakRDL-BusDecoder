from collections import deque

from systemrdl.node import AddressableNode
from systemrdl.walker import RDLListener, WalkerAction

from .design_state import DesignState


class BusDecoderListener(RDLListener):
    def __init__(self, ds: DesignState) -> None:
        self._array_stride_stack: deque[int] = deque()  # Tracks nested array strides
        self._ds = ds
        self._depth = 0

    def should_skip_node(self, node: AddressableNode) -> bool:
        """Stop descending when this node is a routed target."""
        return self._ds.is_decode_boundary(node, self._depth)

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        if node.array_dimensions:
            assert node.array_stride is not None, "Array stride should be defined for arrayed components"
            current_stride = node.array_stride
            self._array_stride_stack.append(current_stride)

            # Work backwards from rightmost to leftmost dimension (fastest to slowest changing)
            # Each dimension's stride is the product of its size and the previous dimension's stride
            for dim in node.array_dimensions[-1:0:-1]:
                current_stride = current_stride * dim
                self._array_stride_stack.appendleft(current_stride)

        self._depth += 1

        # Check if we should skip this node's descendants
        if self.should_skip_node(node):
            return WalkerAction.SkipDescendants

        return WalkerAction.Continue

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        if node.array_dimensions:
            for _ in node.array_dimensions:
                self._array_stride_stack.pop()

        self._depth -= 1

    def __str__(self) -> str:
        return ""
