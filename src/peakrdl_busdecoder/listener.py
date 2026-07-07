from collections import deque

from systemrdl.node import AddressableNode, RegNode
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
        """Check if this node should be skipped (not decoded)."""
        # Check if current depth exceeds max depth
        # max_decode_depth semantics:
        # - 0 means decode all levels (infinite)
        # - 1 means decode only top level (depth 0)
        # - 2 means decode top + 1 level (depth 0 and 1)
        # - N means decode down to depth N-1
        if self._ds.max_decode_depth > 0 and self._depth >= self._ds.max_decode_depth:
            return True

        # Check if this node only contains external addressable children
        if node != self._ds.top_node and not isinstance(node, RegNode):
            if self._ds.node_meta(node).has_only_external_addressable_children:
                return True

        # A leaf addressable node (register, memory, empty block) is always a
        # decode boundary, even when it sits shallower than max_decode_depth.
        if node != self._ds.top_node and not self._ds.node_meta(node).has_addressable_children:
            return True

        return False

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
