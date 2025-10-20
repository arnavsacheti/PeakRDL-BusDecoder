from systemrdl.node import AddressableNode
from systemrdl.walker import WalkerAction

from ..design_state import DesignState
from ..listener import BusDecoderListener
from .base_cpuif import BaseCpuif


class FanoutGenerator(BusDecoderListener):
    def __init__(self, ds: DesignState, cpuif: BaseCpuif) -> None:
        super().__init__(ds)
        self._cpuif = cpuif

    def enter_AddressableComponent(self, node: AddressableNode) -> WalkerAction | None:
        action = super().enter_AddressableComponent(node)
        return action

    def exit_AddressableComponent(self, node: AddressableNode) -> None:
        super().exit_AddressableComponent(node)
