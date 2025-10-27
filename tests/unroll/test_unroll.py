from pathlib import Path
from tempfile import TemporaryDirectory

from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb3 import APB3Cpuif
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif


def test_unroll_disabled_creates_array_interface(sample_rdl: AddrmapNode) -> None:
    """Test that with unroll=False, array nodes are kept as arrays."""
    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(
            sample_rdl,
            tmpdir,
            cpuif_cls=APB4Cpuif,
            cpuif_unroll=False,
        )

        # Read the generated module
        module_file = Path(tmpdir) / "top.sv"
        content = module_file.read_text()

        # Should have a single array interface with [4] dimension
        assert "m_apb_regs [4]" in content

        # Should have a parameter for array size
        assert "N_REGSS = 4" in content

        # Should NOT have individual indexed interfaces
        assert "m_apb_regs_0" not in content
        assert "m_apb_regs_1" not in content
        assert "m_apb_regs_2" not in content
        assert "m_apb_regs_3" not in content


def test_unroll_enabled_creates_individual_interfaces(sample_rdl: AddrmapNode) -> None:
    """Test that with unroll=True, array elements are unrolled into separate instances."""
    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(
            sample_rdl,
            tmpdir,
            cpuif_cls=APB4Cpuif,
            cpuif_unroll=True,
        )

        # Read the generated module
        module_file = Path(tmpdir) / "top.sv"
        content = module_file.read_text()

        # Should have individual interfaces without array dimensions
        assert "m_apb_regs_0," in content or "m_apb_regs_0\n" in content
        assert "m_apb_regs_1," in content or "m_apb_regs_1\n" in content
        assert "m_apb_regs_2," in content or "m_apb_regs_2\n" in content
        assert "m_apb_regs_3" in content

        # Should NOT have array interface
        assert "m_apb_regs [4]" not in content

        # Should NOT have individual interfaces with array dimensions (the bug we're fixing)
        assert "m_apb_regs_0 [4]" not in content
        assert "m_apb_regs_1 [4]" not in content
        assert "m_apb_regs_2 [4]" not in content
        assert "m_apb_regs_3 [4]" not in content

        # Should NOT have array size parameter when unrolled
        assert "N_REGSS" not in content


def test_unroll_with_apb3(sample_rdl: AddrmapNode) -> None:
    """Test that unroll works correctly with APB3 interface."""
    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(
            sample_rdl,
            tmpdir,
            cpuif_cls=APB3Cpuif,
            cpuif_unroll=True,
        )

        # Read the generated module
        module_file = Path(tmpdir) / "top.sv"
        content = module_file.read_text()

        # Should have individual APB3 interfaces
        assert "m_apb_regs_0," in content or "m_apb_regs_0\n" in content
        assert "m_apb_regs_1," in content or "m_apb_regs_1\n" in content
        assert "m_apb_regs_2," in content or "m_apb_regs_2\n" in content
        assert "m_apb_regs_3" in content

        # Should NOT have array dimensions on unrolled interfaces
        assert "m_apb_regs_0 [4]" not in content


def test_unroll_multidimensional_array(multidim_array_rdl: AddrmapNode) -> None:
    """Test that unroll works correctly with multi-dimensional arrays."""
    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(
            multidim_array_rdl,
            tmpdir,
            cpuif_cls=APB4Cpuif,
            cpuif_unroll=True,
        )

        # Read the generated module
        module_file = Path(tmpdir) / "top.sv"
        content = module_file.read_text()

        # Should have individual interfaces for each element in the 2x3 array
        # Format should be m_apb_matrix_0_0, m_apb_matrix_0_1, ..., m_apb_matrix_1_2
        assert "m_apb_matrix_0_0" in content
        assert "m_apb_matrix_0_1" in content
        assert "m_apb_matrix_0_2" in content
        assert "m_apb_matrix_1_0" in content
        assert "m_apb_matrix_1_1" in content
        assert "m_apb_matrix_1_2" in content

        # Should NOT have array dimensions on any of the unrolled interfaces
        for i in range(2):
            for j in range(3):
                assert f"m_apb_matrix_{i}_{j} [" not in content
