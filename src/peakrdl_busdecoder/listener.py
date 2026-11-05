from collections import deque

from systemrdl.node import AddressableNode
from systemrdl.walker import RDLListener, WalkerAction

from .design_state import DesignState


class BusDecoderListener(RDLListener):
    # When True and the design is exported with cpuif_unroll, the exporter
    # walks this listener with arrays unrolled so each element is visited as
    # an individual (scalar) master.
    walk_unrolled = False

    def __init__(self, ds: DesignState) -> None:
        self._array_stride_stack: deque[int] = deque()  # Tracks nested array strides
        self._ds = ds
        self._depth = 0

    def is_rolled_array(self, node: AddressableNode) -> bool:
        """True for an arrayed node visited rolled-up (not an unrolled element)."""
        return bool(node.array_dimensions) and node.current_idx is None

    def loop_base_index(self, node: AddressableNode) -> int:
        """First loop-variable number for this node's own array dimensions.

        Single source of truth for ``i{k}`` / ``gi{k}`` numbering. The open-dim
        stride stack holds exactly one entry per currently-open loop dimension
        (ancestors' dims first, then this node's dims, outermost-first), so this
        must be called *after* the base ``enter_AddressableComponent`` pushed
        this node's own dims. The result is the count of enclosing ancestor loop
        dimensions -- which is also the index where this node's brackets begin
        in ``get_indexed_path(top_node, node)``.
        """
        own = len(node.array_dimensions) if node.array_dimensions else 0
        return len(self._array_stride_stack) - own

    def should_skip_node(self, node: AddressableNode) -> bool:
        """Stop descending when this node is a routed target."""
        return self._ds.is_decode_boundary(node, self._depth)

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        meta = self._ds.node_meta(node)
        if meta.array_strides is not None and self.is_rolled_array(node):
            # Strides are stored outermost-first; append in order so the stack
            # stays outer-to-inner across the whole open path (see
            # loop_base_index).
            self._array_stride_stack.extend(meta.array_strides)

        self._depth += 1

        # Check if we should skip this node's descendants
        if self.should_skip_node(node):
            return WalkerAction.SkipDescendants

        return WalkerAction.Continue

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        if self.is_rolled_array(node):
            assert node.array_dimensions is not None
            for _ in node.array_dimensions:
                self._array_stride_stack.pop()

        self._depth -= 1

    def __str__(self) -> str:
        return ""
