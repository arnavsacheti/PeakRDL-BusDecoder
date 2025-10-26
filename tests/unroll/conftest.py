from collections.abc import Callable

import pytest
from systemrdl.node import AddrmapNode


@pytest.fixture
def sample_rdl(compile_rdl: Callable[..., AddrmapNode]) -> AddrmapNode:
    """Create a simple RDL design with an array."""
    rdl_source = """
    addrmap top {
        reg my_reg {
            field {
                sw=rw;
                hw=r;
            } data[31:0];
        };
        
        my_reg regs[4] @ 0x0 += 0x4;
    };
    """
    return compile_rdl(rdl_source)


@pytest.fixture
def multidim_array_rdl(compile_rdl: Callable[..., AddrmapNode]) -> AddrmapNode:
    """Create an RDL design with a multi-dimensional array."""
    rdl_source = """
    addrmap top {
        reg my_reg {
            field {
                sw=rw;
                hw=r;
            } data[31:0];
        };
        
        my_reg matrix[2][3] @ 0x0 += 0x4;
    };
    """
    return compile_rdl(rdl_source)
