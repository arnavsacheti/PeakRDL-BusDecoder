"""Test handling of external nested addressable components."""

from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif


def test_external_nested_components_generate_correct_decoder(external_nested_rdl: AddrmapNode) -> None:
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
        assert "typedef struct" in content
        assert "logic multicast;" in content
        assert "logic port[N_PORTS];" in content


def test_external_nested_components_generate_correct_interfaces(external_nested_rdl: AddrmapNode) -> None:
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
        assert "m_apb_port [N_PORTS]" in content or "m_apb_port[N_PORTS]" in content
        # Should NOT have interfaces for nested external children
        assert "m_apb_multicast_common" not in content
        assert "m_apb_multicast_response" not in content
        assert "m_apb_common" not in content
        assert "m_apb_response" not in content


def test_non_external_nested_components_are_descended(compile_rdl: Callable[..., AddrmapNode]) -> None:
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
        # Use depth=0 to descend all the way down to registers
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif, max_decode_depth=0)

        # Read the generated module
        module_file = Path(tmpdir) / "outer_block.sv"
        content = module_file.read_text()

        # Should descend into inner and reference inner_reg
        assert "inner" in content
        assert "inner_reg" in content


def test_max_decode_depth_parameter_exists(compile_rdl: Callable[..., AddrmapNode]) -> None:
    """Test that max_decode_depth parameter can be set."""
    rdl_source = """
    addrmap simple {
        reg {
            field { sw=rw; hw=r; } data[31:0];
        } my_reg @ 0x0;
    };
    """
    top = compile_rdl(rdl_source, top="simple")

    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        # Should not raise an exception
        exporter.export(
            top,
            tmpdir,
            cpuif_cls=APB4Cpuif,
            max_decode_depth=2,
        )

        # Verify output was generated
        module_file = Path(tmpdir) / "simple.sv"
        assert module_file.exists()


def test_unaligned_external_component_supported(compile_rdl: Callable[..., AddrmapNode]) -> None:
    """Test that external components can be at unaligned addresses.

    This test verifies that external components don't need to be aligned
    to a power-of-2 multiple of their size, as the busdecoder supports
    unaligned access.
    """
    rdl_source = """
    mem queue_t {
        name = "Queue";
        mementries = 1024;
        memwidth = 64;
    };

    addrmap buffer_t {
        name = "Buffer";
        desc = "";
        
        external queue_t multicast @ 0x100;  // Not power-of-2 aligned
    };
    """
    top = compile_rdl(rdl_source, top="buffer_t")

    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        # Should not raise an alignment error
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif)

        # Verify output was generated
        module_file = Path(tmpdir) / "buffer_t.sv"
        assert module_file.exists()

        content = module_file.read_text()
        # Verify the external component is in the generated code
        assert "multicast" in content


def test_unaligned_external_component_array_supported(compile_rdl: Callable[..., AddrmapNode]) -> None:
    """Test that external component arrays with non-power-of-2 strides are supported.

    This test verifies that external component arrays can have arbitrary strides,
    not just power-of-2 strides.
    """
    rdl_source = """
    mem queue_t {
        name = "Queue";
        mementries = 256;
        memwidth = 32;
    };

    addrmap buffer_t {
        name = "Buffer";
        desc = "";
        
        external queue_t port[4] @ 0x0 += 0x600;  // Stride of 0x600 (not power-of-2) to test unaligned support
    };
    """
    top = compile_rdl(rdl_source, top="buffer_t")

    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        # Should not raise an alignment error
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif)

        # Verify output was generated
        module_file = Path(tmpdir) / "buffer_t.sv"
        assert module_file.exists()

        content = module_file.read_text()
        # Verify the external component array is in the generated code
        assert "port" in content


def test_unaligned_external_nested_in_addrmap(compile_rdl: Callable[..., AddrmapNode]) -> None:
    """Test that addrmaps containing external components can be at unaligned addresses.

    This verifies that not just external components themselves, but also
    non-external addrmaps/regfiles that contain external components can be
    at unaligned addresses.
    """
    rdl_source = """
    mem queue_t {
        name = "Queue";
        mementries = 512;
        memwidth = 32;
    };

    addrmap inner_block {
        external queue_t ext_queue @ 0x0;
    };

    addrmap outer_block {
        inner_block inner @ 0x150;  // Not power-of-2 aligned
    };
    """
    top = compile_rdl(rdl_source, top="outer_block")

    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        # Should not raise an alignment error
        exporter.export(top, tmpdir, cpuif_cls=APB4Cpuif)

        # Verify output was generated
        module_file = Path(tmpdir) / "outer_block.sv"
        assert module_file.exists()

        content = module_file.read_text()
        # Verify the nested components are in the generated code
        assert "inner" in content
