from typing import TYPE_CHECKING

from systemrdl.node import AddressableNode, AddrmapNode, Node, RegfileNode, RegNode, SignalNode
from systemrdl.rdltypes.references import PropertyReference
from systemrdl.walker import RDLListener, RDLWalker, WalkerAction

from .utils import ref_is_internal

if TYPE_CHECKING:
    from .exporter import BusDecoderExporter


class DesignValidator(RDLListener):
    """
    Performs additional rule-checks on the design that check for limitations
    imposed by this exporter.
    """

    def __init__(self, exp: "BusDecoderExporter") -> None:
        self.exp = exp
        self.ds = exp.ds
        self.msg = self.top_node.env.msg

        self._contains_external_block_stack: list[bool] = []
        self.contains_external_block = False

    @property
    def top_node(self) -> "AddrmapNode":
        return self.ds.top_node

    def do_validate(self) -> None:
        reset = self.top_node.cpuif_reset
        if reset is not None and not reset.get_path().startswith(self.top_node.get_path() + "."):
            self._check_cpuif_reset(reset)
        RDLWalker().walk(self.top_node, self)
        self._check_unique_target_ports()
        if self.msg.had_error:
            self.msg.fatal("Unable to export due to previous errors")

    def _check_unique_target_ports(self) -> None:
        """Reject collisions introduced by concrete public-port index suffixes.

        Base identifiers already share DesignState's collision-free naming;
        unrolling can still make ``target[0]`` overlap a literal ``target_0``.
        """
        seen: dict[str, AddressableNode] = {}
        for child in self.ds.get_addressable_children_at_depth(unroll=self.ds.cpuif_unroll):
            name = self.ds.get_target_name(child)
            indices = self.ds.unrolled_indices(child)
            if indices:
                name += "_" + "_".join(map(str, indices))

            other = seen.get(name)
            if other is not None:
                self.msg.error(
                    f"Instances '{other.get_rel_path(self.top_node)}' and "
                    f"'{child.get_rel_path(self.top_node)}' both resolve to master port "
                    f"name '{name}' even after path qualification. Rename one of the "
                    "instances, or lower max_decode_depth so the decode boundary stops "
                    "above them.",
                    child.inst.inst_src_ref,
                )
            else:
                seen[name] = child

    def enter_Component(self, node: "Node") -> WalkerAction | None:
        if node.external and (node != self.top_node):
            # Do not inspect external components. None of my business
            return WalkerAction.SkipDescendants

        # Check if any property references reach across the internal/external boundary
        for prop_name in node.list_properties():
            value = node.get_property(prop_name)
            if isinstance(value, (PropertyReference, Node)):
                if not ref_is_internal(self.top_node, value):
                    if isinstance(value, PropertyReference):
                        src_ref = value.src_ref
                        target = f"{value.node.get_path()}->{value.name}"
                    else:
                        src_ref = node.inst.property_src_ref.get(prop_name, node.inst.inst_src_ref)
                        target = value.get_path()
                    self.msg.error(
                        f"Property '{prop_name}' of '{node.get_path()}' references '{target}', "
                        f"which is not internal to the busdecoder '{self.top_node.get_path()}'. "
                        "Make the reference target internal to the exported addrmap or remove the "
                        "cross-boundary property assignment.",
                        src_ref,
                    )
        return None

    def enter_Signal(self, node: "SignalNode") -> None:
        self._check_cpuif_reset(node)

    def _check_cpuif_reset(self, node: SignalNode) -> None:
        fixed_reset = self.exp.cpuif.fixed_reset
        if not node.get_property("cpuif_reset") or fixed_reset is None:
            return
        port, active_low = fixed_reset
        if (
            node.parent == self.top_node
            and node.inst_name == port
            and not node.get_property("sync", default=False)
            and node.get_property("async", default=True)
            and not node.get_property("activehigh" if active_low else "activelow")
        ):
            # Matching metadata does not misrepresent the generated port.
            return
        polarity = "active-low" if active_low else "active-high"
        self.msg.warning(
            f"cpuif_reset signal '{node.get_path()}' does not configure the built-in "
            f"{type(self.exp.cpuif).__name__} adapter. It uses {polarity} asynchronous "
            f"reset port '{port}'; connect that port with the required polarity instead.",
            node.inst.inst_src_ref,
        )

    def enter_AddressableComponent(self, node: "AddressableNode") -> None:
        # All registers must be aligned to the internal data bus width
        alignment = self.exp.cpuif.data_width_bytes
        if (node.raw_address_offset % alignment) != 0:
            self.msg.error(
                f"Unaligned address offset {node.raw_address_offset} bytes for "
                f"'{node.get_path()}'; it must be a multiple of {alignment} bytes. "
                "Move the component to an aligned address.",
                node.inst.inst_src_ref,
            )
        if node.is_array and (
            node.array_stride is not None and (node.array_stride % alignment) != 0
        ):  # is_array implies stride is not none
            assert node.array_dimensions is not None
            stride = node.array_stride
            dimensions = []
            for index in reversed(range(len(node.array_dimensions))):
                count = node.array_dimensions[index]
                if stride % alignment:
                    dimensions.append(f"dimension {index} (size {count}): {stride} bytes")
                stride *= count
            self.msg.error(
                f"Unaligned array stride for '{node.get_path()}': "
                + ", ".join(reversed(dimensions))
                + f". Each stride must be a multiple of {alignment} bytes; "
                "adjust the array's += stride.",
                node.inst.inst_src_ref,
            )

        if not isinstance(node, RegNode):
            # Entering a block-like node
            if node == self.top_node:
                # Ignore top addrmap's external property when entering
                self._contains_external_block_stack.append(False)
            else:
                self._contains_external_block_stack.append(node.external)

    def enter_Regfile(self, node: RegfileNode) -> None:
        self._check_sharedextbus(node)

    def enter_Addrmap(self, node: AddrmapNode) -> None:
        self._check_sharedextbus(node)

    def _check_sharedextbus(self, node: RegfileNode | AddrmapNode) -> None:
        if node.get_property("sharedextbus"):
            self.msg.error(
                "This exporter does not support enabling the 'sharedextbus' property yet.",
                node.inst.property_src_ref.get("sharedextbus", node.inst.inst_src_ref),
            )

    def enter_Reg(self, node: "RegNode") -> None:
        # accesswidth of wide registers must be consistent within the register block
        accesswidth = node.get_property("accesswidth")
        regwidth = node.get_property("regwidth")

        if accesswidth < regwidth:
            # register is 'wide'
            if accesswidth != self.exp.cpuif.data_width:
                self.msg.error(
                    f"Multi-word registers that have an accesswidth ({accesswidth}) "
                    "that are inconsistent with this busdecoder's CPU bus width "
                    f"({self.exp.cpuif.data_width}) are not supported.",
                    node.inst.inst_src_ref,
                )

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        if not isinstance(node, RegNode):
            # Exiting block-like node
            contains_external_block = self._contains_external_block_stack.pop()

            if self._contains_external_block_stack:
                # Still in the design. Update stack
                self._contains_external_block_stack[-1] |= contains_external_block
            else:
                # Exiting top addrmap. Resolve final answer
                self.contains_external_block = contains_external_block
