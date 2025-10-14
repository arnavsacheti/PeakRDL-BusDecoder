from typing import TYPE_CHECKING
from systemrdl.node import AddrmapNode, FieldNode, RegNode, AddressableNode

if TYPE_CHECKING:
    from .exporter import BusDecoderExporter, DesignState
    from .addr_decode import AddressDecode


class Dereferencer:
    """
    This class provides an interface to convert conceptual SystemRDL references
    into Verilog identifiers
    """

    def __init__(self, exp: "BusDecoderExporter"):
        self.exp = exp

    @property
    def address_decode(self) -> "AddressDecode":
        return self.exp.address_decode

    @property
    def ds(self) -> "DesignState":
        return self.exp.ds

    @property
    def top_node(self) -> AddrmapNode:
        return self.exp.ds.top_node

    def get_access_strobe(self, obj: RegNode | FieldNode, reduce_substrobes: bool = True) -> str:
        """
        Returns the Verilog string that represents the register's access strobe
        """
        return self.address_decode.get_access_strobe(obj, reduce_substrobes)

    def get_external_block_access_strobe(self, obj: "AddressableNode") -> str:
        """
        Returns the Verilog string that represents the external block's access strobe
        """
        return self.address_decode.get_external_block_access_strobe(obj)
