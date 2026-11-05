import re
from pathlib import Path
from tempfile import TemporaryDirectory

from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb.apb_cpuif import APB3Cpuif, APB4Cpuif
from peakrdl_busdecoder.cpuif.axi4lite import AXI4LiteCpuif

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _export(
    rdl_node: AddrmapNode,
    cpuif_cls: type = APB4Cpuif,
    unroll: bool = True,
    **kwargs: object,
) -> tuple[str, str]:
    """Export a design and return (module_content, package_content)."""
    with TemporaryDirectory() as tmpdir:
        exporter = BusDecoderExporter()
        exporter.export(
            rdl_node,
            tmpdir,
            cpuif_cls=cpuif_cls,
            cpuif_unroll=unroll,
            **kwargs,
        )
        module_name = rdl_node.inst_name
        module_content = (Path(tmpdir) / f"{module_name}.sv").read_text()
        package_content = (Path(tmpdir) / f"{module_name}_pkg.sv").read_text()
    return module_content, package_content


def _assert_no_duplicate_localparams(pkg_content: str) -> None:
    """Assert the package contains no duplicate localparam declarations."""
    localparam_lines = [
        line.strip() for line in pkg_content.splitlines() if line.strip().startswith("localparam")
    ]
    localparam_names = []
    for line in localparam_lines:
        parts = line.split()
        if len(parts) >= 2:
            localparam_names.append(parts[1])

    assert len(localparam_names) == len(set(localparam_names)), (
        f"Duplicate localparam declarations found: {localparam_names}"
    )


# ===========================================================================
# A. Port declaration tests
# ===========================================================================


def test_unroll_disabled_creates_array_interface(sample_rdl: AddrmapNode) -> None:
    """Test that with unroll=False, array nodes are kept as arrays."""
    content, _ = _export(sample_rdl, unroll=False)

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
    content, _ = _export(sample_rdl, unroll=True)

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
    content, _ = _export(sample_rdl, cpuif_cls=APB3Cpuif, unroll=True)

    # Should have individual APB3 interfaces
    assert "m_apb_regs_0," in content or "m_apb_regs_0\n" in content
    assert "m_apb_regs_1," in content or "m_apb_regs_1\n" in content
    assert "m_apb_regs_2," in content or "m_apb_regs_2\n" in content
    assert "m_apb_regs_3" in content

    # Should NOT have array dimensions on unrolled interfaces
    assert "m_apb_regs_0 [4]" not in content


def test_unroll_multidimensional_array(multidim_array_rdl: AddrmapNode) -> None:
    """Test that unroll works correctly with multi-dimensional arrays."""
    content, _ = _export(multidim_array_rdl, unroll=True)

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


# ===========================================================================
# B. Package generation tests
# ===========================================================================


class TestUnrollPackage:
    """Verify that the generated package is correct when unrolled."""

    def test_no_duplicate_localparams(self, sample_rdl: AddrmapNode) -> None:
        """When unrolled, the package should not contain duplicate localparam declarations."""
        _, pkg_content = _export(sample_rdl, unroll=True)

        _assert_no_duplicate_localparams(pkg_content)

    def test_no_duplicate_localparams_external_array(self, external_array_rdl: AddrmapNode) -> None:
        """External block arrays should also not produce duplicate localparams when unrolled."""
        _, pkg_content = _export(external_array_rdl, unroll=True)

        _assert_no_duplicate_localparams(pkg_content)

    def test_no_duplicate_localparams_multidim(self, multidim_array_rdl: AddrmapNode) -> None:
        """Multi-dimensional arrays should also not produce duplicate localparams when unrolled."""
        _, pkg_content = _export(multidim_array_rdl, unroll=True)

        _assert_no_duplicate_localparams(pkg_content)

    def test_disabled_has_single_addr_width_param(self, sample_rdl: AddrmapNode) -> None:
        """When NOT unrolled, there should be exactly one addr_width localparam per array."""
        _, pkg_content = _export(sample_rdl, unroll=False)

        count = pkg_content.count("TOP_REGS_ADDR_WIDTH")
        assert count == 1, f"Expected exactly 1 TOP_REGS_ADDR_WIDTH declaration, got {count}"

    def test_multiple_arrays_no_duplicate_localparams(self, multiple_arrays_rdl: AddrmapNode) -> None:
        """Multiple distinct arrays should each have at most one addr_width param when unrolled."""
        _, pkg_content = _export(multiple_arrays_rdl, unroll=True)

        _assert_no_duplicate_localparams(pkg_content)


# ===========================================================================
# C. AXI4-Lite and flat interface tests
# ===========================================================================


class TestUnrollProtocols:
    """Test unroll with different CPU interface protocols."""

    def test_axi4lite_unroll_port_declarations(self, sample_rdl: AddrmapNode) -> None:
        """AXI4-Lite should generate individual interface instances when unrolled."""
        content, _ = _export(sample_rdl, cpuif_cls=AXI4LiteCpuif, unroll=True)

        # Should have individual AXI4-Lite master interfaces
        for i in range(4):
            assert f"m_axil_regs_{i}" in content

        # Should NOT have array interface
        assert "m_axil_regs [4]" not in content

    def test_axi4lite_unroll_no_array_size_param(self, sample_rdl: AddrmapNode) -> None:
        """AXI4-Lite should not have N_XXXS parameter when unrolled."""
        content, _ = _export(sample_rdl, cpuif_cls=AXI4LiteCpuif, unroll=True)

        assert "N_REGSS" not in content

    def test_axi4lite_disabled_creates_array(self, sample_rdl: AddrmapNode) -> None:
        """AXI4-Lite should create array interface when unroll is disabled."""
        content, _ = _export(sample_rdl, cpuif_cls=AXI4LiteCpuif, unroll=False)

        assert "m_axil_regs [4]" in content
        assert "N_REGSS = 4" in content

    def test_apb3_unroll_fanout_individual_ports(self, sample_rdl: AddrmapNode) -> None:
        """APB3 fanout should reference individual ports when unrolled."""
        content, _ = _export(sample_rdl, cpuif_cls=APB3Cpuif, unroll=True)

        for i in range(4):
            assert f"m_apb_regs_{i}." in content

        assert "m_apb_regs[" not in content

    def test_apb3_unroll_no_duplicate_localparams(self, sample_rdl: AddrmapNode) -> None:
        """APB3 package should not have duplicate localparams when unrolled."""
        _, pkg_content = _export(sample_rdl, cpuif_cls=APB3Cpuif, unroll=True)

        _assert_no_duplicate_localparams(pkg_content)

    def test_multidim_axi4lite_unroll(self, multidim_array_rdl: AddrmapNode) -> None:
        """AXI4-Lite should correctly handle multi-dimensional array unrolling."""
        content, _ = _export(multidim_array_rdl, cpuif_cls=AXI4LiteCpuif, unroll=True)

        # Should have individual interfaces for 2x3 matrix
        for i in range(2):
            for j in range(3):
                assert f"m_axil_matrix_{i}_{j}" in content

        # Should NOT have array notation
        assert "m_axil_matrix [" not in content
        assert "m_axil_matrix[" not in content


# ===========================================================================
# D. Edge case tests
# ===========================================================================


class TestUnrollEdgeCases:
    """Test edge cases for the unroll feature."""

    def test_single_element_array_unroll(self, single_element_array_rdl: AddrmapNode) -> None:
        """An array of size 1 should unroll to a single non-arrayed interface."""
        content, _ = _export(single_element_array_rdl, unroll=True)

        # Should have the single unrolled instance
        assert "m_apb_regs_0" in content

        # Should NOT have array notation
        assert "m_apb_regs [1]" not in content
        assert "N_REGSS" not in content

        # Fanout should reference the individual port
        assert "m_apb_regs[" not in content

    def test_single_element_array_no_unroll(self, single_element_array_rdl: AddrmapNode) -> None:
        """An array of size 1 without unroll should still be an array."""
        content, _ = _export(single_element_array_rdl, unroll=False)

        assert "m_apb_regs [1]" in content

    def test_mixed_array_and_non_array(self, mixed_array_rdl: AddrmapNode) -> None:
        """A design with both arrayed and non-arrayed children should unroll correctly."""
        content, _ = _export(mixed_array_rdl, unroll=True)

        # The solo (non-array) register should be present as-is
        assert "m_apb_solo_reg" in content

        # The array registers should be unrolled
        for i in range(4):
            assert f"m_apb_arr_regs_{i}" in content

        # No array notation for the unrolled instances
        assert "m_apb_arr_regs [4]" not in content
        assert "m_apb_arr_regs[" not in content

    def test_mixed_disabled(self, mixed_array_rdl: AddrmapNode) -> None:
        """A mixed design without unroll should keep arrays as arrays."""
        content, _ = _export(mixed_array_rdl, unroll=False)

        assert "m_apb_solo_reg" in content
        assert "m_apb_arr_regs [4]" in content
        assert "m_apb_arr_regs_0" not in content

    def test_external_block_array_unroll(self, external_array_rdl: AddrmapNode) -> None:
        """External block arrays should unroll correctly."""
        content, _ = _export(external_array_rdl, unroll=True)

        # Should have individual block interfaces
        for i in range(4):
            assert f"m_apb_blocks_{i}" in content

        # Should NOT have array interface or array-indexed references
        assert "m_apb_blocks [4]" not in content
        assert "m_apb_blocks[" not in content

    def test_external_block_array_no_duplicate_localparams(self, external_array_rdl: AddrmapNode) -> None:
        """External block array package should not have duplicate localparams when unrolled."""
        _, pkg_content = _export(external_array_rdl, unroll=True)

        _assert_no_duplicate_localparams(pkg_content)

    def test_address_width_unaffected_by_unroll(self, sample_rdl: AddrmapNode) -> None:
        """The address width should be the same regardless of the unroll flag."""
        _, pkg_unrolled = _export(sample_rdl, unroll=True)
        _, pkg_normal = _export(sample_rdl, unroll=False)

        def extract_min_addr_width(pkg: str) -> str:
            match = re.search(r"TOP_MIN_ADDR_WIDTH\s*=\s*(\d+)", pkg)
            assert match is not None, "Could not find TOP_MIN_ADDR_WIDTH"
            return match.group(1)

        assert extract_min_addr_width(pkg_unrolled) == extract_min_addr_width(pkg_normal)

    def test_data_width_unaffected_by_unroll(self, sample_rdl: AddrmapNode) -> None:
        """The data width should be the same regardless of the unroll flag."""
        _, pkg_unrolled = _export(sample_rdl, unroll=True)
        _, pkg_normal = _export(sample_rdl, unroll=False)

        def extract_data_width(pkg: str) -> str:
            match = re.search(r"TOP_DATA_WIDTH\s*=\s*(\d+)", pkg)
            assert match is not None, "Could not find TOP_DATA_WIDTH"
            return match.group(1)

        assert extract_data_width(pkg_unrolled) == extract_data_width(pkg_normal)

    def test_both_files_generated_with_unroll(self, sample_rdl: AddrmapNode) -> None:
        """Both the module and package files should be generated when unrolling."""
        with TemporaryDirectory() as tmpdir:
            exporter = BusDecoderExporter()
            exporter.export(
                sample_rdl,
                tmpdir,
                cpuif_cls=APB4Cpuif,
                cpuif_unroll=True,
            )

            assert (Path(tmpdir) / "top.sv").exists()
            assert (Path(tmpdir) / "top_pkg.sv").exists()

    def test_multiple_arrays_unroll(self, multiple_arrays_rdl: AddrmapNode) -> None:
        """Multiple distinct arrays should all be unrolled independently."""
        content, _ = _export(multiple_arrays_rdl, unroll=True)

        # Alpha array (size 2) should be unrolled
        assert "m_apb_alpha_0" in content
        assert "m_apb_alpha_1" in content
        assert "m_apb_alpha [2]" not in content

        # Beta array (size 3) should be unrolled
        assert "m_apb_beta_0" in content
        assert "m_apb_beta_1" in content
        assert "m_apb_beta_2" in content
        assert "m_apb_beta [3]" not in content

        # No array-indexed references to either
        assert "m_apb_alpha[" not in content
        assert "m_apb_beta[" not in content

    def test_multiple_arrays_fanout_all_individual(self, multiple_arrays_rdl: AddrmapNode) -> None:
        """Fanout for multiple arrays should reference all individual ports."""
        content, _ = _export(multiple_arrays_rdl, unroll=True)

        # All individual ports should be referenced
        for i in range(2):
            assert f"m_apb_alpha_{i}." in content
        for i in range(3):
            assert f"m_apb_beta_{i}." in content
