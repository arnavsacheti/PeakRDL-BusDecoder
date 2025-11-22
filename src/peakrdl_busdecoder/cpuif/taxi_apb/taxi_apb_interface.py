"""Taxi APB-specific interface implementations."""

from ..interface import SVInterface


class TaxiAPBSVInterface(SVInterface):
    """Taxi APB SystemVerilog interface."""

    def get_interface_type(self) -> str:
        return "taxi_apb_if"

    def get_slave_name(self) -> str:
        return "s_apb"

    def get_master_prefix(self) -> str:
        return "m_apb_"
