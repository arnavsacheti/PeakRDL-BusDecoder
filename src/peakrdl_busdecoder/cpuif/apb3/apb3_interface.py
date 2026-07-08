"""Deprecated re-export shim for API stability.

The APB3/APB4 interface implementations were merged into
``cpuif/apb/apb_interface.py``, where the protocol specifics are driven by
class attributes on the cpuif (``apb_interface_type``, ``has_pprot``,
``has_pstrb``). This module keeps the historical
``cpuif.apb3.apb3_interface`` import path working; the classes below pin the
APB3 naming the old hardwired classes used, and otherwise inherit the merged
behavior (including ``clk_src``-conditional clock/reset ports).
"""

import warnings

from ..apb.apb_interface import APBFlatInterface, APBSVInterface

warnings.warn(
    "peakrdl_busdecoder.cpuif.apb3.apb3_interface is deprecated; "
    "use APBSVInterface/APBFlatInterface from "
    "peakrdl_busdecoder.cpuif.apb.apb_interface instead",
    DeprecationWarning,
    stacklevel=2,
)


class APB3SVInterface(APBSVInterface):
    """Deprecated APB3 alias of :class:`APBSVInterface`."""

    def get_interface_type(self) -> str:
        return "apb3_intf"

    def get_slave_name(self) -> str:
        return "s_apb"

    def get_master_prefix(self) -> str:
        return "m_apb_"


class APB3FlatInterface(APBFlatInterface):
    """Deprecated APB3 alias of :class:`APBFlatInterface`."""

    def get_slave_prefix(self) -> str:
        return "s_apb_"

    def get_master_prefix(self) -> str:
        return "m_apb_"


__all__ = ["APB3FlatInterface", "APB3SVInterface"]
