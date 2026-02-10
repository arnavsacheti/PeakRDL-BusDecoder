"""
SystemRDL Parameter extraction and classification for BusDecoder generation.

Monkeypatches the SystemRDL compiler's ParameterRef.get_value() to trace
which root-level addrmap parameters are referenced throughout the component
tree, then classifies each parameter as either:

- ADDRESS_MODIFYING: affects array dimensions, address offsets, or strides.
  These become enable parameters where the runtime value n <= N (elaborated max).
- DIRECT: does not affect the address map layout. These are passed through
  as RTL parameters on the generated module.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

from systemrdl.node import AddressableNode, AddrmapNode, Node

if TYPE_CHECKING:
    pass


class ParameterUsage(Enum):
    """How a root-level RDL parameter is used in the design."""

    ADDRESS_MODIFYING = auto()
    DIRECT = auto()


@dataclass
class ArrayEnableInfo:
    """Records that a root parameter controls the effective count of an array."""

    node_path: str
    max_elements: int
    dimension_index: int


@dataclass
class RdlParameter:
    """A root-level SystemRDL parameter extracted for BusDecoder generation."""

    name: str
    value: Any
    param_type: Any
    usage: ParameterUsage
    array_enables: list[ArrayEnableInfo] = field(default_factory=list)

    @property
    def sv_type(self) -> str:
        """Return the SystemVerilog type string for this parameter."""
        if isinstance(self.value, int):
            return "int"
        if isinstance(self.value, bool):
            return "bit"
        return "int"

    @property
    def sv_value(self) -> str:
        """Return the SystemVerilog default value string."""
        if isinstance(self.value, bool):
            return "1'b1" if self.value else "1'b0"
        return str(self.value)


class RdlParameterExtractor:
    """
    Extracts root-level addrmap parameters and classifies their usage by
    monkeypatching ParameterRef.get_value() to trace references during
    a cache-cleared re-evaluation pass.
    """

    def __init__(self, top_node: AddrmapNode) -> None:
        self.top_node = top_node
        self._root_original_def = top_node.inst.original_def or top_node.inst
        # Map param_name -> dict of id(node) -> node
        # (Node objects are not hashable, so we use id-keyed dicts)
        self._usage_map: dict[str, dict[int, Node]] = defaultdict(dict)

    def extract(self) -> list[RdlParameter]:
        """
        Extract and classify all root-level parameters.

        Returns a list of RdlParameter objects describing each parameter,
        its elaborated value, and how it's used in the design.
        """
        raw_params = self.top_node.parameters
        if not raw_params:
            return []

        # Phase 1: Monkeypatch and trace parameter references
        self._trace_parameter_usage()

        # Phase 2: Classify each parameter
        result: list[RdlParameter] = []
        for param_name, param_value in raw_params.items():
            param_obj = self.top_node.inst.parameters_dict[param_name]
            usage, array_enables = self._classify_parameter(param_name, param_value)
            result.append(
                RdlParameter(
                    name=param_name,
                    value=param_value,
                    param_type=param_obj.param_type,
                    usage=usage,
                    array_enables=array_enables,
                )
            )

        return result

    def _trace_parameter_usage(self) -> None:
        """
        Monkeypatch ParameterRef.get_value() to record which root parameters
        are referenced and from which nodes, then clear caches and force
        re-evaluation to trigger the tracking.
        """
        from systemrdl.ast.references import ParameterRef
        from systemrdl.core.parameter import Parameter

        root_def = self._root_original_def
        usage_map = self._usage_map

        original_param_ref_get_value = ParameterRef.get_value

        def tracked_get_value(
            self_ref: ParameterRef,
            eval_width: int | None = None,
            assignee_node: Node | None = None,
        ) -> Any:
            if self_ref.ref_root is root_def:
                if assignee_node is not None:
                    usage_map[self_ref.param_name][id(assignee_node)] = assignee_node
            return original_param_ref_get_value(self_ref, eval_width, assignee_node)

        # Install monkeypatch
        ParameterRef.get_value = tracked_get_value  # type: ignore[assignment]

        try:
            # Clear all parameter caches to force re-evaluation
            self._clear_parameter_caches()
            # Force re-evaluation by accessing parameters throughout the tree
            self._force_reevaluation()
        finally:
            # Always restore original method
            ParameterRef.get_value = original_param_ref_get_value  # type: ignore[assignment]

    def _clear_parameter_caches(self) -> None:
        """Clear _cached_value on all Parameter objects in the tree."""
        # Clear root parameters
        for param in self.top_node.inst.parameters_dict.values():
            param._cached_value = None

        # Clear descendant parameters
        for node in self.top_node.descendants():
            if hasattr(node.inst, "parameters_dict"):
                for param in node.inst.parameters_dict.values():
                    param._cached_value = None

    def _force_reevaluation(self) -> None:
        """
        Force re-evaluation of all parameter expressions in the tree.

        Walk top-down: evaluate root parameters first (they have no
        dependencies on other params), then descendant parameters which
        may reference root params via ParameterRef expressions.
        """
        # Evaluate root parameters first
        for param in self.top_node.inst.parameters_dict.values():
            param.get_value(self.top_node)

        # Then evaluate all descendants
        for node in self.top_node.descendants():
            if hasattr(node.inst, "parameters_dict"):
                for param in node.inst.parameters_dict.values():
                    try:
                        param.get_value(node)
                    except Exception:
                        # Some parameters may not re-evaluate cleanly
                        # (e.g., if their expressions reference resolved-only state).
                        # That's OK — we've already captured what we need.
                        pass

    def _classify_parameter(
        self, param_name: str, param_value: Any
    ) -> tuple[ParameterUsage, list[ArrayEnableInfo]]:
        """
        Classify a root parameter based on how it's used in the design.

        A parameter is ADDRESS_MODIFYING if its value matches an array
        dimension (or product of dimensions) of any node that the
        monkeypatch traced it to. Otherwise it's DIRECT.
        """
        if not isinstance(param_value, int):
            return ParameterUsage.DIRECT, []

        array_enables: list[ArrayEnableInfo] = []
        traced_nodes_dict = self._usage_map.get(param_name, {})
        traced_nodes = list(traced_nodes_dict.values())
        traced_node_ids = set(traced_nodes_dict.keys())

        # Check all arrayed descendants to see if this parameter drives
        # an array dimension.
        for node in self.top_node.descendants():
            if not isinstance(node, AddressableNode):
                continue
            if not node.is_array or not node.array_dimensions:
                continue

            # Check if this node (or an ancestor that was traced) connects
            # to the root parameter
            node_is_traced = id(node) in traced_node_ids or any(
                self._is_ancestor_of(traced, node) for traced in traced_nodes
            )
            if not node_is_traced:
                # Fallback heuristic: value match on array dimensions
                if param_value not in node.array_dimensions:
                    continue

            # Match the parameter value to specific array dimensions
            for dim_idx, dim in enumerate(node.array_dimensions):
                if dim == param_value:
                    node_path = node.get_rel_path(self.top_node)
                    array_enables.append(
                        ArrayEnableInfo(
                            node_path=node_path,
                            max_elements=dim,
                            dimension_index=dim_idx,
                        )
                    )

        if array_enables:
            return ParameterUsage.ADDRESS_MODIFYING, array_enables

        return ParameterUsage.DIRECT, []

    @staticmethod
    def _is_ancestor_of(ancestor: Node, descendant: Node) -> bool:
        """Check if ancestor is an ancestor of descendant in the node tree."""
        current: Node | None = descendant.parent
        while current is not None:
            if current is ancestor:
                return True
            current = current.parent
        return False
