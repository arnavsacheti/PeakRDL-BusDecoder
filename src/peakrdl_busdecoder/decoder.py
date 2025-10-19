from collections import deque
from enum import Enum

from systemrdl.node import AddressableNode
from systemrdl.walker import RDLListener, RDLSimpleWalker, WalkerAction

from .body import Body, ForLoopBody, IfBody
from .design_state import DesignState
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


class AddressDecode:
    def __init__(self, flavor: DecodeLogicFlavor, ds: DesignState) -> None:
        self._flavor = flavor
        self._ds = ds

    def walk(self) -> str:
        walker = RDLSimpleWalker()
        dlg = DecodeLogicGenerator(self._flavor, self._ds)
        walker.walk(self._ds.top_node, dlg, skip_top=True)
        return str(dlg)


class DecodeLogicGenerator(RDLListener):
    def __init__(
        self,
        flavor: DecodeLogicFlavor,
        ds: DesignState,
    ) -> None:
        self._ds = ds
        self._flavor = flavor

        self._decode_stack: deque[Body] = deque()  # Tracks decoder body
        self._cond_stack: deque[str] = deque()  # Tracks conditions nested for loops
        self._array_stride_stack: deque[int] = deque()  # Tracks nested array strids

        # Initial Stack Conditions
        self._decode_stack.append(IfBody())

    def cpuif_addr_predicate(self, node: AddressableNode) -> list[str]:
        # Generate address bounds
        addr_width = self._ds.addr_width
        l_bound = SVInt(
            node.raw_address_offset,
            addr_width,
        )
        u_bound = l_bound + SVInt(node.total_size, addr_width)

        # Handle arrayed components
        l_bound_comp = [str(l_bound)]
        u_bound_comp = [str(u_bound)]
        for i, stride in enumerate(self._array_stride_stack):
            l_bound_comp.append(f"({addr_width}'(i{i})*{SVInt(stride, addr_width)})")
            u_bound_comp.append(f"({addr_width}'(i{i})*{SVInt(stride, addr_width)})")

        # Generate Conditions
        return [
            f"{self._flavor.cpuif_address} >= ({'+'.join(l_bound_comp)})",
            f"{self._flavor.cpuif_address} < ({'+'.join(u_bound_comp)})",
        ]

    def cpuif_prot_predicate(self, node: AddressableNode) -> list[str]:
        if self._flavor == DecodeLogicFlavor.READ:
            # Can we have PROT on read? (axi full?)
            return []

        # TODO: Implement
        return []

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        conditions: list[str] = []
        conditions.extend(self.cpuif_addr_predicate(node))
        conditions.extend(self.cpuif_prot_predicate(node))

        condition = " && ".join(f"({c})" for c in conditions)

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
        if isinstance(self._decode_stack[-1], IfBody) and node.array_dimensions:
            # arrayed component with new if-body
            self._cond_stack.append(condition)
            for i, dim in enumerate(
                node.array_dimensions,
                start=len(self._array_stride_stack) - len(node.array_dimensions),
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
            with self._decode_stack[-1].cm(condition) as b:
                b += f"{self._flavor.cpuif_select}.{get_indexed_path(self._ds.top_node, node)} = 1'b1;"

        # if node.external:
        #     return WalkerAction.SkipDescendants

        return WalkerAction.Continue

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        if not node.array_dimensions:
            return

        ifb = self._decode_stack.pop()
        if ifb:
            self._decode_stack[-1] += ifb
        else:
            self._decode_stack[-1] += (
                f"{self._flavor.cpuif_select}.{get_indexed_path(self._ds.top_node, node)} = 1'b1;"
            )

        for _ in node.array_dimensions:
            b = self._decode_stack.pop()
            if not b:
                continue

            if isinstance(self._decode_stack[-1], IfBody):
                with self._decode_stack[-1].cm(self._cond_stack.pop()) as parent_b:
                    parent_b += b
            else:
                self._decode_stack[-1] += b

            self._array_stride_stack.pop()

    def __str__(self) -> str:
        body = self._decode_stack[-1]
        if isinstance(body, IfBody):
            with body.cm(...) as b:
                b += f"{self._flavor.cpuif_select}.bad_addr = 1'b1;"

        return str(body)
