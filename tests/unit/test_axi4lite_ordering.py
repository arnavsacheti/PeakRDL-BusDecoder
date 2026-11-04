"""Validation boundaries for AXI4-Lite queue configuration."""

from collections.abc import Callable

import pytest
from systemrdl import RDLCompileError
from systemrdl.node import AddrmapNode

from peakrdl_busdecoder.design_state import DesignState


RDL = """
addrmap child {
    reg { field { sw=rw; hw=r; } value[31:0]; } data;
};
addrmap top {
    external child first @ 0x000;
    external child second @ 0x100;
};
"""


@pytest.mark.parametrize("depth", [0, -1])
def test_outstanding_depth_must_be_positive(
    compile_rdl: Callable[..., AddrmapNode], depth: int
) -> None:
    top = compile_rdl(RDL, top="top")
    with pytest.raises(RDLCompileError, match="greater than or equal to 1"):
        DesignState(top, {"axi4lite_max_outstanding": depth})
