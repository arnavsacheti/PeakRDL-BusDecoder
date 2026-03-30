"""
SystemRDL Parameter extraction for BusDecoder generation.

Monkeypatches the SystemRDL compiler's ParameterRef.get_value() to trace
which root-level addrmap parameters are referenced throughout the component
tree, then identifies address-modifying parameters:

- ADDRESS_MODIFYING: affects array dimensions.  These become enable
  parameters where the runtime value n <= N (elaborated max).

Only address-modifying parameters are relevant to the decoder; non-address
parameters (reset values, field widths, etc.) are silently ignored.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from systemrdl.node import AddressableNode, AddrmapNode, Node

logger = logging.getLogger(__name__)


class ParameterUsage(Enum):
    """How a root-level RDL parameter is used in the design."""

    ADDRESS_MODIFYING = auto()


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
        Extract address-modifying root-level parameters.

        Only parameters that drive array dimensions are relevant to the
        decoder.  Non-address parameters are silently ignored.

        Returns a list of RdlParameter objects for each address-modifying
        parameter found.
        """
        raw_params = self.top_node.parameters
        if not raw_params:
            return []

        # Phase 1: Monkeypatch and trace parameter references
        self._trace_parameter_usage()

        # Phase 2: Pre-collect arrayed addressable nodes (single tree walk)
        self._arrayed_nodes: list[AddressableNode] = [
            node
            for node in self.top_node.descendants()
            if isinstance(node, AddressableNode) and node.is_array and node.array_dimensions
        ]

        # Phase 3: Keep only address-modifying parameters
        result: list[RdlParameter] = []
        for param_name, param_value in raw_params.items():
            param_obj = self.top_node.inst.parameters_dict[param_name]
            array_enables = self._find_array_enables(param_name, param_value)
            if not array_enables:
                continue
            result.append(
                RdlParameter(
                    name=param_name,
                    value=param_value,
                    param_type=param_obj.param_type,
                    usage=ParameterUsage.ADDRESS_MODIFYING,
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

        root_def = self._root_original_def
        usage_map = self._usage_map

        original_param_ref_get_value = ParameterRef.get_value

        def tracked_get_value(
            self_ref: ParameterRef,
            eval_width: int | None = None,
            assignee_node: Node | None = None,
        ) -> Any:  # noqa: ANN401
            if self_ref.ref_root is root_def:
                if assignee_node is not None:
                    usage_map[self_ref.param_name][id(assignee_node)] = assignee_node
            return original_param_ref_get_value(self_ref, eval_width, assignee_node)

        # Install monkeypatch
        ParameterRef.get_value = tracked_get_value  # type: ignore[assignment]  # ty: ignore[invalid-assignment]

        try:
            # Clear all parameter caches to force re-evaluation
            self._clear_parameter_caches()
            # Force re-evaluation by accessing parameters throughout the tree
            self._force_reevaluation()
        finally:
            # Always restore original method
            ParameterRef.get_value = original_param_ref_get_value

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
                        logger.debug(
                            "Could not re-evaluate param %s on %s",
                            param,
                            node,
                            exc_info=True,
                        )

    def _find_array_enables(
        self,
        param_name: str,
        param_value: Any,  # noqa: ANN401
    ) -> list[ArrayEnableInfo]:
        """
        Find array dimensions driven by this parameter.

        Returns a non-empty list if the parameter is address-modifying.
        When the monkeypatch traced specific nodes for this parameter,
        only those nodes (and their descendants) are checked.  When no
        trace data is available (e.g. references were resolved during
        elaboration), a value-match heuristic over all arrayed nodes
        is used as a fallback — but only if the parameter name appears
        in the component definition's original parameter list, reducing
        false positives.
        """
        if not isinstance(param_value, int):
            return []

        array_enables: list[ArrayEnableInfo] = []
        traced_nodes_dict = self._usage_map.get(param_name, {})
        traced_nodes = list(traced_nodes_dict.values())
        traced_node_ids = set(traced_nodes_dict.keys())
        has_trace = bool(traced_nodes_dict)

        # Pre-compute which children reference this param in array dim expressions
        orig_array_children = self._param_in_original_array_dims(param_name) if not has_trace else set()

        for node in self._arrayed_nodes:
            if has_trace:
                # Only consider nodes that were traced or are descendants
                # of traced nodes
                node_is_traced = id(node) in traced_node_ids or any(
                    self._is_ancestor_of(traced, node) for traced in traced_nodes
                )
                if not node_is_traced:
                    continue
            else:
                # Fallback: check the addrmap's original (pre-elaboration) AST
                # to see if this parameter appears in array dimension expressions.
                # This avoids false-positive value matches.
                if node.inst_name not in orig_array_children:
                    continue

            # Match the parameter value to specific array dimensions
            for dim_idx, dim in enumerate(node.array_dimensions or []):
                if dim == param_value:
                    array_enables.append(
                        ArrayEnableInfo(
                            node_path=node.get_rel_path(self.top_node),
                            max_elements=dim,
                            dimension_index=dim_idx,
                        )
                    )

        return array_enables

    def _param_in_original_array_dims(self, param_name: str) -> set[str]:
        """Find child inst_names whose array dims reference this parameter in the original AST."""
        from systemrdl.ast.references import ParameterRef

        orig = self._root_original_def
        matches: set[str] = set()
        for child in getattr(orig, "children", []):
            dims = getattr(child, "array_dimensions", None)
            if not dims:
                continue
            for dim_expr in dims:
                if self._expr_references_param(dim_expr, param_name, ParameterRef):
                    matches.add(child.inst_name)
                    break
        return matches

    @staticmethod
    def _expr_references_param(expr: Any, param_name: str, param_ref_cls: type) -> bool:  # noqa: ANN401
        """Recursively check if an AST expression references a parameter by name."""
        if isinstance(expr, param_ref_cls) and expr.param_name == param_name:
            return True
        # Walk known AST expression attributes
        for attr in ("v", "op_a", "op_b", "n"):
            child = getattr(expr, attr, None)
            if child is not None and hasattr(child, "get_value"):
                if RdlParameterExtractor._expr_references_param(child, param_name, param_ref_cls):
                    return True
        for attr in ("operands",):
            children = getattr(expr, attr, None)
            if children:
                for child in children:
                    if hasattr(child, "get_value"):
                        if RdlParameterExtractor._expr_references_param(child, param_name, param_ref_cls):
                            return True
        return False

    @staticmethod
    def _is_ancestor_of(ancestor: Node, descendant: Node) -> bool:
        """Check if ancestor is an ancestor of descendant in the node tree."""
        current: Node | None = descendant.parent
        while current is not None:
            if current is ancestor:
                return True
            current = current.parent
        return False
