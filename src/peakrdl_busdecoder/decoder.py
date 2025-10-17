from collections import deque

from systemrdl.node import AddressableNode
from systemrdl.walker import RDLListener, RDLSimpleWalker, WalkerAction

from .body import Body, ForLoopBody, IfBody
from .sv_int import SVInt


class AddressDecode:
    def __init__(self, node: AddressableNode, addr_width: int) -> None:
        self._node = node
        self._addr_width = addr_width

    def walk(self) -> str:
        walker = RDLSimpleWalker()
        dlg = DecodeLogicGenerator(self)
        walker.walk(self._node, dlg, skip_top=True)
        return str(dlg)

    @property
    def node(self) -> AddressableNode:
        return self._node

    @property
    def addr_width(self) -> int:
        return self._addr_width


class DecodeLogicGenerator(RDLListener):
    cpuif_addr_signal = "addr"
    cpuif_sel_prefix = "cpuif_"

    def __init__(
        self,
        address_decoder: AddressDecode,
        max_depth: int = 1,
    ) -> None:
        self._address_decoder = address_decoder
        self._depth = 0
        self._max_depth = max_depth

        self._stack: list[Body] = [IfBody()]
        self._conditions: deque[str] = deque()
        self._select_signal = [f"{self.cpuif_sel_prefix}{address_decoder.node.inst_name}"]

        # Stack to keep track of array strides for nested arrayed components
        self._array_stride_stack: list[int] = []

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        # Generate address bounds
        addr_width = self._address_decoder.addr_width
        l_bound = SVInt(
            node.raw_absolute_address - self._address_decoder.node.raw_absolute_address,
            addr_width,
        )
        u_bound = l_bound + SVInt(node.total_size, addr_width)

        # Handle arrayed components
        l_bound_str = str(l_bound)
        u_bound_str = str(u_bound)
        for i, stride in enumerate(self._array_stride_stack):
            l_bound_str += f" + (({addr_width})'(i{i}) * {SVInt(stride, addr_width)})"
            u_bound_str += f" + (({addr_width})'(i{i}) * {SVInt(stride, addr_width)})"

        # Generate condition string
        condition = (
            f"({self.cpuif_addr_signal} >= ({l_bound_str})) && ({self.cpuif_addr_signal} < ({u_bound_str}))"
        )

        if node.array_dimensions:
            assert node.array_stride is not None, "Array stride should be defined for arrayed components"
            # Collect strides for each array dimension
            current_stride = node.array_stride
            strides: list[int] = []
            for dim in reversed(node.array_dimensions):
                strides.append(current_stride)
                current_stride *= dim
            strides.reverse()
            self._array_stride_stack.extend(strides)

        # Generate condition string and manage stack
        signal = node.inst_name
        if isinstance(self._stack[-1], IfBody) and node.array_dimensions:
            # arrayed component with new if-body
            self._conditions.append(condition)
            for dim in node.array_dimensions:
                fb = ForLoopBody(
                    "int",
                    f"i{self._depth}",
                    dim,
                )
                self._stack.append(fb)
                signal += f"[i{self._depth}]"
                self._depth += 1

            self._stack.append(IfBody())
        elif isinstance(self._stack[-1], IfBody):
            # non-arrayed component with if-body
            with self._stack[-1].cm(condition) as b:
                b += f"{'.'.join([*self._select_signal, signal])} = 1'b1;"
        self._select_signal.append(signal)

        # if node.external:
        #     return WalkerAction.SkipDescendants

        return WalkerAction.Continue

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        self._select_signal.pop()

        if not node.array_dimensions:
            return

        ifb = self._stack.pop()
        self._stack[-1] += ifb

        for _ in node.array_dimensions:
            self._depth -= 1

            b = self._stack.pop()
            if b.lines:
                if isinstance(self._stack[-1], IfBody):
                    with self._stack[-1].cm(self._conditions.pop()) as parent_b:
                        parent_b += b
                else:
                    self._stack[-1] += b

            self._array_stride_stack.pop()

    def __str__(self) -> str:
        return str(self._stack[-1])
