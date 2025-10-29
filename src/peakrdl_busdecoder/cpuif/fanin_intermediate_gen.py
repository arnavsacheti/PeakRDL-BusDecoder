"""Generator for intermediate signals needed for interface array fanin.

When using SystemVerilog interface arrays, we cannot use variable indices
in procedural blocks (like always_comb). This generator creates intermediate
signals that copy from interface arrays using generate loops, which can then
be safely accessed with variable indices in the fanin logic.
"""

from collections import deque
from typing import TYPE_CHECKING

from systemrdl.node import AddressableNode
from systemrdl.walker import WalkerAction

from ..body import Body, ForLoopBody
from ..design_state import DesignState
from ..listener import BusDecoderListener
from ..utils import get_indexed_path

if TYPE_CHECKING:
    from .base_cpuif import BaseCpuif


class FaninIntermediateGenerator(BusDecoderListener):
    """Generates intermediate signals for interface array fanin."""

    def __init__(self, ds: DesignState, cpuif: "BaseCpuif") -> None:
        super().__init__(ds)
        self._cpuif = cpuif
        self._declarations: list[str] = []
        self._stack: deque[Body] = deque()
        self._stack.append(Body())

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        action = super().enter_AddressableComponent(node)

        # Only generate intermediates for interface arrays
        # Check if cpuif has is_interface attribute (some implementations don't)
        is_interface = getattr(self._cpuif, "is_interface", False)
        if not is_interface or not node.array_dimensions:
            return action

        # Generate intermediate signal declarations
        self._generate_intermediate_declarations(node)

        # Generate assignment logic using generate loops
        if node.array_dimensions:
            for i, dim in enumerate(node.array_dimensions):
                fb = ForLoopBody(
                    "genvar",
                    f"gi{i}",
                    dim,
                )
                self._stack.append(fb)

        # Generate assignments from interface array to intermediates
        self._stack[-1] += self._generate_intermediate_assignments(node)

        return action

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        is_interface = getattr(self._cpuif, "is_interface", False)
        if is_interface and node.array_dimensions:
            for _ in node.array_dimensions:
                b = self._stack.pop()
                if not b:
                    continue
                self._stack[-1] += b

        super().exit_AddressableComponent(node)

    def _generate_intermediate_declarations(self, node: AddressableNode) -> None:
        """Generate intermediate signal declarations for a node."""
        inst_name = node.inst_name

        # Array dimensions should be checked before calling this function
        if not node.array_dimensions:
            return

        # Calculate total array size
        array_size = 1
        for dim in node.array_dimensions:
            array_size *= dim

        # Create array dimension string
        array_str = "".join(f"[{dim}]" for dim in node.array_dimensions)

        # Generate declarations for each fanin signal
        # For APB3/4: PREADY, PSLVERR, PRDATA
        # These are the signals read in fanin
        self._declarations.append(f"logic {inst_name}_fanin_ready{array_str};")
        self._declarations.append(f"logic {inst_name}_fanin_err{array_str};")
        self._declarations.append(
            f"logic [{self._cpuif.data_width - 1}:0] {inst_name}_fanin_data{array_str};"
        )

    def _generate_intermediate_assignments(self, node: AddressableNode) -> str:
        """Generate assignments from interface array to intermediate signals."""
        inst_name = node.inst_name
        indexed_path = get_indexed_path(node.parent, node, "gi", skip_kw_filter=True)

        # Get master prefix - use getattr to avoid type errors
        interface = getattr(self._cpuif, "_interface", None)
        if interface is None:
            return ""
        master_prefix = interface.get_master_prefix()

        # Array dimensions should be checked before calling this function
        if not node.array_dimensions:
            return ""

        # Create indexed signal names for left-hand side
        array_idx = "".join(f"[gi{i}]" for i in range(len(node.array_dimensions)))

        # Delegate to cpuif to get the appropriate assignments for this interface type
        assignments = self._cpuif.fanin_intermediate_assignments(
            node, inst_name, array_idx, master_prefix, indexed_path
        )

        return "\n".join(assignments)

    def get_declarations(self) -> str:
        """Get all intermediate signal declarations."""
        if not self._declarations:
            return ""
        return "\n".join(self._declarations)

    def __str__(self) -> str:
        """Get all intermediate signal declarations and assignments."""
        if not self._declarations:
            return ""

        # Output declarations first
        output = "\n".join(self._declarations)
        output += "\n\n"

        # Then output assignments
        body_str = "\n".join(map(str, self._stack))
        if body_str and body_str.strip():
            output += body_str

        return output
