"""Pytest fixtures for unit tests."""

from collections.abc import Callable

import pytest
from systemrdl.node import AddrmapNode


@pytest.fixture
def external_nested_rdl(compile_rdl: Callable[..., AddrmapNode]) -> AddrmapNode:
    """Create an RDL design with external nested addressable components.

    This tests the scenario where an addrmap contains external children
    that themselves have external addressable children.
    The decoder should only generate select signals for the top-level
    external children, not their internal structure.
    """
    rdl_source = """
    mem queue_t {
        name = "Queue";
        mementries = 1024;
        memwidth = 64;
    };

    addrmap port_t {
        name = "Port";
        desc = "";

        external queue_t common[3] @ 0x0 += 0x2000;
        external queue_t response  @ 0x6000;
    };

    addrmap buffer_t {
        name = "Buffer";
        desc = "";

        port_t multicast      @ 0x0;
        port_t port      [16] @ 0x8000 += 0x8000;
    };
    """
    return compile_rdl(rdl_source, top="buffer_t")


@pytest.fixture
def nested_addrmap_rdl(compile_rdl: Callable[..., AddrmapNode]) -> AddrmapNode:
    """Create an RDL design with nested non-external addrmaps for testing depth control."""
    rdl_source = """
    addrmap level2 {
        reg {
            field { sw=rw; hw=r; } data2[31:0];
        } reg2 @ 0x0;
        
        reg {
            field { sw=rw; hw=r; } data2b[31:0];
        } reg2b @ 0x4;
    };

    addrmap level1 {
        reg {
            field { sw=rw; hw=r; } data1[31:0];
        } reg1 @ 0x0;
        
        level2 inner2 @ 0x10;
    };

    addrmap level0 {
        level1 inner1 @ 0x0;
    };
    """
    return compile_rdl(rdl_source, top="level0")
