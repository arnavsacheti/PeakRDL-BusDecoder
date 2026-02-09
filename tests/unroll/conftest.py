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


@pytest.fixture
def mixed_array_rdl(compile_rdl: Callable[..., AddrmapNode]) -> AddrmapNode:
    """Create an RDL design with both arrayed and non-arrayed children."""
    rdl_source = """
    addrmap top {
        reg my_reg {
            field {
                sw=rw;
                hw=r;
            } data[31:0];
        };

        my_reg solo_reg @ 0x0;
        my_reg arr_regs[4] @ 0x100 += 0x4;
    };
    """
    return compile_rdl(rdl_source)


@pytest.fixture
def external_array_rdl(compile_rdl: Callable[..., AddrmapNode]) -> AddrmapNode:
    """Create an RDL design with an array of external address blocks."""
    rdl_source = """
    addrmap child_block {
        reg {
            field { sw=rw; hw=r; } data[31:0];
        } creg @ 0x0;
    };

    addrmap top {
        external child_block blocks[4] @ 0x0 += 0x100;
    };
    """
    return compile_rdl(rdl_source)


@pytest.fixture
def single_element_array_rdl(compile_rdl: Callable[..., AddrmapNode]) -> AddrmapNode:
    """Create an RDL design with a single-element array."""
    rdl_source = """
    addrmap top {
        reg my_reg {
            field {
                sw=rw;
                hw=r;
            } data[31:0];
        };

        my_reg regs[1] @ 0x0 += 0x4;
    };
    """
    return compile_rdl(rdl_source)


@pytest.fixture
def multiple_arrays_rdl(compile_rdl: Callable[..., AddrmapNode]) -> AddrmapNode:
    """Create an RDL design with multiple distinct arrays."""
    rdl_source = """
    addrmap top {
        reg reg_a {
            field { sw=rw; hw=r; } data[31:0];
        };
        reg reg_b {
            field { sw=rw; hw=r; } data[31:0];
        };

        reg_a alpha[2] @ 0x0 += 0x4;
        reg_b beta[3] @ 0x100 += 0x4;
    };
    """
    return compile_rdl(rdl_source)
