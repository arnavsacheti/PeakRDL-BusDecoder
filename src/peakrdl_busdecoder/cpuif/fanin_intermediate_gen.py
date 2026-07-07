"""Generator for intermediate signals needed for interface array fanin.

When using SystemVerilog interface arrays, we cannot use variable indices
in procedural blocks (like always_comb). This generator creates intermediate
signals that copy from interface arrays using generate loops, which can then
be safely accessed with variable indices in the fanin logic.
"""

import re
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
    """Generates intermediate signals for interface array fanin.

    Declarations and assignments are emitted per *decode boundary* node, sized
    and indexed by every open array dimension (rolled array ancestors' + the
    node's own). Generate loops are opened for every rolled array node on the
    path (ancestors included) so a boundary below array ancestors is copied
    element-by-element with constant (genvar) indices.
    """

    walk_unrolled = True

    def __init__(self, ds: DesignState, cpuif: "BaseCpuif") -> None:
        super().__init__(ds)
        self._cpuif = cpuif
        self._declarations: list[str] = []
        self._stack: deque[Body] = deque()
        self._stack.append(Body())

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        action = super().enter_AddressableComponent(node)
        should_generate = action == WalkerAction.SkipDescendants

        # Only interface-style cpuifs need intermediate copies. For flat cpuifs
        # the fanin logic references the unpacked master arrays directly.
        is_interface = getattr(self._cpuif, "is_interface", False)
        if not is_interface:
            return action

        # Open a generate loop for every rolled array dimension on the path so
        # ancestor dims are covered too. Numbering is positional (single source
        # of truth) so it lines up with get_indexed_path from the top node.
        if self.is_rolled_array(node):
            assert node.array_dimensions is not None
            base = self.loop_base_index(node)
            for i, dim in enumerate(node.array_dimensions, base):
                fb = ForLoopBody(
                    "genvar",
                    f"gi{i}",
                    self._ds.resolve_loop_bound(node, i - base, dim),
                )
                self._stack.append(fb)

        # Declarations/assignments belong to the decode boundary only, and only
        # when it is an interface array (by its own or an ancestor's dims).
        if should_generate and self._cpuif.is_master_array(node):
            self._generate_intermediate_declarations(node)
            self._stack[-1] += self._generate_intermediate_assignments(node)

        return action

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        is_interface = getattr(self._cpuif, "is_interface", False)
        if is_interface and self.is_rolled_array(node):
            assert node.array_dimensions is not None
            for _ in node.array_dimensions:
                b = self._stack.pop()
                if not b:
                    continue
                self._stack[-1] += b

        super().exit_AddressableComponent(node)

    def _open_dim_brackets(self, node: AddressableNode, indexer: str) -> str:
        """Bracket string covering all open dims, e.g. ``[gi0][gi1]``."""
        indexed = get_indexed_path(self._ds.top_node, node, indexer, skip_kw_filter=True)
        return "".join(re.findall(r"\[[^\]]*\]", indexed))

    def _generate_intermediate_declarations(self, node: AddressableNode) -> None:
        """Generate intermediate signal declarations for a boundary node."""
        name = self._ds.master_port_name(node)
        dims = self._cpuif.master_array_dims(node)
        if not dims:
            return

        array_str = "".join(f"[{dim}]" for dim in dims)

        # Signals read back in fanin (APB3/4: PREADY, PSLVERR, PRDATA).
        self._declarations.append(f"logic {name}_fanin_ready{array_str};")
        self._declarations.append(f"logic {name}_fanin_err{array_str};")
        self._declarations.append(f"logic [{self._cpuif.data_width - 1}:0] {name}_fanin_data{array_str};")

        # Allow the cpuif to add extra intermediate declarations (e.g. AXI write
        # response channel), sized by all open dims.
        self._declarations.extend(self._cpuif.fanin_intermediate_declarations(node))

    def _generate_intermediate_assignments(self, node: AddressableNode) -> str:
        """Generate assignments from the interface array to the intermediates."""
        name = self._ds.master_port_name(node)
        dims = self._cpuif.master_array_dims(node)
        if not dims:
            return ""

        interface = getattr(self._cpuif, "_interface", None)
        if interface is None:
            return ""
        master_prefix = interface.get_master_prefix()

        # Same bracket string on both sides: the intermediate net and the master
        # interface element are indexed by every open dimension.
        brackets = self._open_dim_brackets(node, "gi")
        indexed_path = name + brackets

        assignments = self._cpuif.fanin_intermediate_assignments(
            node, name, brackets, master_prefix, indexed_path
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

        output = "\n".join(self._declarations)
        output += "\n\n"

        body_str = "\n".join(map(str, self._stack))
        if body_str and body_str.strip():
            output += body_str

        return output
