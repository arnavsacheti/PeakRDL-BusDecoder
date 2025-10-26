"""Test handling of external nested addressable components."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif


@pytest.fixture
def external_nested_rdl(compile_rdl):
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


def test_external_nested_components_generate_correct_decoder(external_nested_rdl):
    """Test that external nested components generate correct decoder logic.
    
    The decoder should:
    - Generate select signals for multicast and port[16]
    - NOT generate select signals for multicast.common[] or multicast.response
    - NOT generate invalid paths like multicast.common[i0]
    """
    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(
            external_nested_rdl,
            tmpdir,
            cpuif_cls=APB4Cpuif,
        )
        
        # Read the generated module
        module_file = Path(tmpdir) / "buffer_t.sv"
        content = module_file.read_text()
        
        # Should have correct select signals
        assert "cpuif_wr_sel.multicast = 1'b1;" in content
        assert "cpuif_wr_sel.port[i0] = 1'b1;" in content
        
        # Should NOT have invalid nested paths
        assert "cpuif_wr_sel.multicast.common" not in content
        assert "cpuif_wr_sel.multicast.response" not in content
        assert "cpuif_rd_sel.multicast.common" not in content
        assert "cpuif_rd_sel.multicast.response" not in content
        
        # Verify struct is flat (no nested structs for external children)
        assert "typedef struct packed" in content
        assert "logic multicast;" in content
        assert "logic [15:0]port;" in content


def test_external_nested_components_generate_correct_interfaces(external_nested_rdl):
    """Test that external nested components generate correct interface ports.
    
    The module should have:
    - One master interface for multicast
    - Array of 16 master interfaces for port[]
    - NO interfaces for internal components like common[] or response
    """
    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(
            external_nested_rdl,
            tmpdir,
            cpuif_cls=APB4Cpuif,
        )
        
        # Read the generated module
        module_file = Path(tmpdir) / "buffer_t.sv"
        content = module_file.read_text()
        
        # Should have master interfaces for top-level external children
        assert "m_apb_multicast" in content
        assert "m_apb_port [16]" in content or "m_apb_port[16]" in content
        
        # Should NOT have interfaces for nested external children
        assert "m_apb_multicast_common" not in content
        assert "m_apb_multicast_response" not in content
        assert "m_apb_common" not in content
        assert "m_apb_response" not in content


def test_non_external_nested_components_are_descended(compile_rdl):
    """Test that non-external nested components are still descended into.
    
    This is a regression test to ensure we didn't break normal nested
    component handling.
    """
    rdl_source = """
    addrmap inner_block {
        reg {
            field {
                sw=rw;
                hw=r;
            } data[31:0];
        } inner_reg @ 0x0;
    };
    
    addrmap outer_block {
        inner_block inner @ 0x0;
    };
    """
    top = compile_rdl(rdl_source, top="outer_block")
    
    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif)
        
        # Read the generated module
        module_file = Path(tmpdir) / "outer_block.sv"
        content = module_file.read_text()
        
        # Should descend into inner and reference inner_reg
        assert "inner" in content
        assert "inner_reg" in content
