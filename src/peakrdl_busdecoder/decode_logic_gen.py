from collections import deque
from enum import Enum
from typing import cast

from systemrdl.node import AddressableNode
from systemrdl.walker import WalkerAction

from .body import Body, ForLoopBody, IfBody
from .design_state import DesignState
from .listener import BusDecoderListener
from .sv_int import SVInt
from .utils import get_indexed_path


class DecodeLogicFlavor(Enum):
    READ = "rd"
    WRITE = "wr"

    @property
    def cpuif_address(self) -> str:
        return f"cpuif_{self.value}_addr"

    @property
    def cpuif_select(self) -> str:
        return f"cpuif_{self.value}_sel"


class DecodeLogicGenerator(BusDecoderListener):
    def __init__(
        self,
        ds: DesignState,
        flavor: DecodeLogicFlavor,
    ) -> None:
        super().__init__(ds)
        self._flavor = flavor

        self._decode_stack: deque[Body] = deque()  # Tracks decoder body
        self._cond_stack: deque[str] = deque()  # Tracks conditions nested for loops

        # Initial Stack Conditions
        self._decode_stack.append(IfBody())

    def cpuif_addr_predicate(self, node: AddressableNode, total_size: bool = True) -> list[str]:
        # Generate address bounds
        addr_width = self._ds.addr_width
        l_bound = SVInt(
            node.raw_absolute_address,
            addr_width,
        )
        if total_size:
            u_bound = l_bound + SVInt(node.total_size, addr_width)
        else:
            u_bound = l_bound + SVInt(node.size, addr_width)

        array_stack = list(self._array_stride_stack)
        if total_size and node.array_dimensions:
            array_stack = array_stack[: -len(node.array_dimensions)]

        # Handle arrayed components
        l_bound_comp = [str(l_bound)]
        u_bound_comp = [str(u_bound)]
        for i, stride in enumerate(array_stack):
            l_bound_comp.append(f"({addr_width}'(i{i})*{SVInt(stride, addr_width)})")
            u_bound_comp.append(f"({addr_width}'(i{i})*{SVInt(stride, addr_width)})")

        lower_expr = f"{self._flavor.cpuif_address} >= ({'+'.join(l_bound_comp)})"
        upper_expr = f"{self._flavor.cpuif_address} < ({'+'.join(u_bound_comp)})"

        predicates: list[str] = []
        # Avoid generating a redundant >= 0 comparison, which triggers Verilator warnings.
        if not (l_bound.value == 0 and len(l_bound_comp) == 1):
            predicates.append(lower_expr)
        # Avoid generating a redundant full-width < max comparison, which triggers Verilator warnings.
        if not (u_bound.value == (1 << addr_width) and len(u_bound_comp) == 1):
            predicates.append(upper_expr)

        return predicates

    def cpuif_prot_predicate(self, node: AddressableNode) -> list[str]:
        if self._flavor == DecodeLogicFlavor.READ:
            # Can we have PROT on read? (axi full?)
            return []

        # TODO: Implement
        return []

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        action = super().enter_AddressableComponent(node)

        should_decode = action == WalkerAction.SkipDescendants

        if not should_decode and self._ds.max_decode_depth == 0:
            # When decoding all levels, treat leaf registers as decode boundary
            for child in node.children():
                if isinstance(child, AddressableNode):
                    break
            else:
                should_decode = True

        # Only generate select logic if we're at the decode boundary
        if not should_decode:
            return action

        conditions: list[str] = []
        conditions.extend(self.cpuif_addr_predicate(node))
        conditions.extend(self.cpuif_prot_predicate(node))
        condition = " && ".join(f"({c})" for c in conditions)

        # Generate condition string and manage stack
        if node.array_dimensions:
            # arrayed component with new if-body
            self._cond_stack.append(condition)
            for i, dim in enumerate(
                node.array_dimensions,
            ):
                fb = ForLoopBody(
                    "int",
                    f"i{i}",
                    dim,
                )
                self._decode_stack.append(fb)

            self._decode_stack.append(IfBody())
        elif isinstance(self._decode_stack[-1], IfBody):
            # non-arrayed component with if-body
            ifb = cast(IfBody, self._decode_stack[-1])
            with ifb.cm(condition) as b:
                b += f"{self._flavor.cpuif_select}.{get_indexed_path(self._ds.top_node, node)} = 1'b1;"
        else:
            raise RuntimeError("Invalid decode stack state")

        return action

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        if not node.array_dimensions:
            return

        ifb = self._decode_stack.pop()
        if not ifb and isinstance(ifb, IfBody):
            conditions: list[str] = []
            conditions.extend(self.cpuif_addr_predicate(node, total_size=False))
            condition = " && ".join(f"({c})" for c in conditions)

            with ifb.cm(condition) as b:
                b += f"{self._flavor.cpuif_select}.{get_indexed_path(self._ds.top_node, node)} = 1'b1;"
        self._decode_stack[-1] += ifb

        for _ in node.array_dimensions:
            b = self._decode_stack.pop()
            if not b:
                continue

            if isinstance(self._decode_stack[-1], IfBody):
                ifb = cast(IfBody, self._decode_stack[-1])
                with ifb.cm(self._cond_stack.pop()) as parent_b:
                    parent_b += b
            else:
                self._decode_stack[-1] += b

        super().exit_AddressableComponent(node)

    def __str__(self) -> str:
        body = self._decode_stack[-1]
        if isinstance(body, IfBody):
            if len(body) == 0:
                return f"{self._flavor.cpuif_select}.cpuif_err = 1'b1;"
            with body.cm(...) as b:
                b += f"{self._flavor.cpuif_select}.cpuif_err = 1'b1;"

        return str(body)
