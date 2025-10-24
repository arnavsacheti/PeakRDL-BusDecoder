from collections import deque

from systemrdl.node import AddressableNode
from systemrdl.walker import RDLListener, WalkerAction

from .design_state import DesignState


class BusDecoderListener(RDLListener):
    def __init__(self, ds: DesignState) -> None:
        self._array_stride_stack: deque[int] = deque()  # Tracks nested array strides
        self._ds = ds
        self._depth = 0

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        if node.array_dimensions:
            assert node.array_stride is not None, "Array stride should be defined for arrayed components"
            # Calculate stride for each dimension
            # For multi-dimensional arrays like [2][3], array_stride gives the stride of the
            # rightmost (fastest-changing) dimension. We need to calculate strides for all dimensions.
            strides = []
            current_stride = node.array_stride
            strides.append(current_stride)
            
            # Work backwards from rightmost dimension to calculate other strides
            for i in range(len(node.array_dimensions) - 1, 0, -1):
                current_stride = current_stride * node.array_dimensions[i]
                strides.insert(0, current_stride)
            
            self._array_stride_stack.extend(strides)

        self._depth += 1

        if self._depth > 1:
            return WalkerAction.SkipDescendants
        return WalkerAction.Continue

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        if node.array_dimensions:
            for _ in node.array_dimensions:
                self._array_stride_stack.pop()

        self._depth -= 1

    def __str__(self) -> str:
        return ""
