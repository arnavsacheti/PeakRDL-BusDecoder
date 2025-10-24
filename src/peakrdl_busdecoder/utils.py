import re
from re import Match

from systemrdl.node import AddrmapNode, Node
from systemrdl.rdltypes.references import PropertyReference

from .identifier_filter import kw_filter as kwf


def get_indexed_path(
    top_node: Node, target_node: Node, indexer: str = "i", skip_kw_filter: bool = False
) -> str:
    """
    Get the relative path from top_node to target_node, replacing any unknown
    array indexes with incrementing iterators (i0, i1, ...).
    """
    path = target_node.get_rel_path(top_node, empty_array_suffix="[!]")

    # replace unknown indexes with incrementing iterators i0, i1, ...
    class ReplaceUnknown:
        def __init__(self) -> None:
            self.i = 0

        def __call__(self, match: Match[str]) -> str:
            s = f"{indexer}{self.i}"
            self.i += 1
            return s

    path = re.sub(r"!", ReplaceUnknown(), path)

    # Sanitize any SV keywords
    def kw_filter_repl(m: Match[str]) -> str:
        return kwf(m.group(0))

    if not skip_kw_filter:
        path = re.sub(r"\w+", kw_filter_repl, path)

    return path


def clog2(n: int) -> int:
    return (n - 1).bit_length()


def is_pow2(x: int) -> bool:
    return (x > 0) and ((x & (x - 1)) == 0)


def roundup_pow2(x: int) -> int:
    return 1 << (x - 1).bit_length()


def ref_is_internal(top_node: AddrmapNode, ref: Node | PropertyReference) -> bool:
    """
    Determine whether the reference is internal to the top node.

    For the sake of this exporter, root signals are treated as internal.
    """
    current_node: Node | None
    if isinstance(ref, PropertyReference):
        current_node = ref.node
    else:
        current_node = ref

    # pyrefly: ignore[bad-assignment] - false positive due to circular type checking
    while current_node is not None:
        if current_node == top_node:
            # reached top node without finding any external components
            # is internal!
            return True

        if current_node.external:
            # not internal!
            return False

        current_node = current_node.parent

    # A root signal was referenced, which dodged the top addrmap
    # This is considered internal for this exporter
    return True
