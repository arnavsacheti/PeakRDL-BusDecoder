import re
from pathlib import Path
from tempfile import TemporaryDirectory

from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb3 import APB3Cpuif
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif
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


def test_unroll_with_axi4lite(sample_rdl: AddrmapNode) -> None:
    """Test that unroll works correctly with AXI4-Lite interface."""
    content, _ = _export(sample_rdl, cpuif_cls=AXI4LiteCpuif, unroll=True)

    # Should have individual AXI4-Lite interfaces
    assert "m_axil_regs_0" in content
    assert "m_axil_regs_1" in content
    assert "m_axil_regs_2" in content
    assert "m_axil_regs_3" in content

    # Should NOT have array interface
    assert "m_axil_regs [4]" not in content

    # Should NOT have array size parameter
    assert "N_REGSS" not in content


# ===========================================================================
# B. Fanout signal generation tests
# ===========================================================================


class TestUnrollFanout:
    """Verify that fanout logic references individual port instances when unrolled."""

    def test_fanout_references_individual_ports(self, sample_rdl: AddrmapNode) -> None:
        """When unrolled, fanout should assign to individual port names, not array-indexed."""
        content, _ = _export(sample_rdl, unroll=True)

        # Each unrolled instance should be referenced individually in the fanout section
        for i in range(4):
            assert f"m_apb_regs_{i}." in content

    def test_fanout_no_array_indexing_on_ports(self, sample_rdl: AddrmapNode) -> None:
        """When unrolled, fanout should NOT use array-indexed port references like m_apb_regs[gi0]."""
        content, _ = _export(sample_rdl, unroll=True)

        # Should NOT have array-indexed references to the master ports
        # (This is a known bug: fanout still uses m_apb_regs[gi0] instead of m_apb_regs_0, etc.)
        assert "m_apb_regs[" not in content

    def test_fanout_disabled_uses_array_indexing(self, sample_rdl: AddrmapNode) -> None:
        """When NOT unrolled, fanout should use array indexing as normal."""
        content, _ = _export(sample_rdl, unroll=False)

        # Should use genvar loop with array indexing
        assert "m_apb_regs[" in content

    def test_fanout_multidim_references_individual_ports(
        self, multidim_array_rdl: AddrmapNode
    ) -> None:
        """When unrolled, multi-dimensional array fanout should reference individual ports."""
        content, _ = _export(multidim_array_rdl, unroll=True)

        # Each unrolled 2D element should be referenced individually
        for i in range(2):
            for j in range(3):
                assert f"m_apb_matrix_{i}_{j}." in content

        # Should NOT have array-indexed references
        assert "m_apb_matrix[" not in content

    def test_fanout_axi4lite_individual_ports(self, sample_rdl: AddrmapNode) -> None:
        """AXI4-Lite fanout should also reference individual ports when unrolled."""
        content, _ = _export(sample_rdl, cpuif_cls=AXI4LiteCpuif, unroll=True)

        for i in range(4):
            assert f"m_axil_regs_{i}." in content

        # Should NOT have array-indexed references
        assert "m_axil_regs[" not in content


# ===========================================================================
# C. Fanin signal generation tests
# ===========================================================================


class TestUnrollFanin:
    """Verify that fanin logic references individual port instances when unrolled."""

    def test_fanin_no_array_indexing_on_ports(self, sample_rdl: AddrmapNode) -> None:
        """When unrolled, fanin should NOT reference array-indexed ports like m_apb_regs[gi0]."""
        content, _ = _export(sample_rdl, unroll=True)

        # The fanin section (and any intermediate signal section) should not use
        # array-indexed references to the master port interfaces.
        # Find all references to master ports after the fanout section
        assert "m_apb_regs[" not in content

    def test_fanin_disabled_uses_array_indexing(self, sample_rdl: AddrmapNode) -> None:
        """When NOT unrolled, fanin should use array indexing normally."""
        content, _ = _export(sample_rdl, unroll=False)

        assert "m_apb_regs[" in content

    def test_fanin_intermediate_signals_not_arrayed(self, sample_rdl: AddrmapNode) -> None:
        """When unrolled, intermediate fanin signals should not be declared as arrays."""
        content, _ = _export(sample_rdl, unroll=True)

        # When ports are individual, intermediate signals (e.g., regs_fanin_ready[4])
        # should also be individual, not arrays.
        # Check that there are no intermediate array declarations for the unrolled instances.
        assert "regs_fanin_ready[4]" not in content
        assert "regs_fanin_err[4]" not in content
        assert "regs_fanin_data[4]" not in content

    def test_fanin_axi4lite_no_array_indexing(self, sample_rdl: AddrmapNode) -> None:
        """AXI4-Lite fanin should also not use array-indexed ports when unrolled."""
        content, _ = _export(sample_rdl, cpuif_cls=AXI4LiteCpuif, unroll=True)

        assert "m_axil_regs[" not in content


# ===========================================================================
# D. Package generation tests
# ===========================================================================


class TestUnrollPackage:
    """Verify that the generated package is correct when unrolled."""

    def test_no_duplicate_localparams(self, sample_rdl: AddrmapNode) -> None:
        """When unrolled, the package should not contain duplicate localparam declarations."""
        _, pkg_content = _export(sample_rdl, unroll=True)

        # Count occurrences of each localparam declaration
        # There should be no duplicate localparam names
        localparam_lines = [
            line.strip()
            for line in pkg_content.splitlines()
            if line.strip().startswith("localparam")
        ]
        localparam_names = []
        for line in localparam_lines:
            # Extract the parameter name (second token after "localparam")
            parts = line.split()
            if len(parts) >= 2:
                localparam_names.append(parts[1])

        # No duplicate names
        assert len(localparam_names) == len(set(localparam_names)), (
            f"Duplicate localparam declarations found: {localparam_names}"
        )

    def test_no_duplicate_localparams_external_array(self, external_array_rdl: AddrmapNode) -> None:
        """External block arrays should also not produce duplicate localparams when unrolled."""
        _, pkg_content = _export(external_array_rdl, unroll=True)

        localparam_lines = [
            line.strip()
            for line in pkg_content.splitlines()
            if line.strip().startswith("localparam")
        ]
        localparam_names = []
        for line in localparam_lines:
            parts = line.split()
            if len(parts) >= 2:
                localparam_names.append(parts[1])

        assert len(localparam_names) == len(set(localparam_names)), (
            f"Duplicate localparam declarations found: {localparam_names}"
        )

    def test_no_duplicate_localparams_multidim(self, multidim_array_rdl: AddrmapNode) -> None:
        """Multi-dimensional arrays should also not produce duplicate localparams when unrolled."""
        _, pkg_content = _export(multidim_array_rdl, unroll=True)

        localparam_lines = [
            line.strip()
            for line in pkg_content.splitlines()
            if line.strip().startswith("localparam")
        ]
        localparam_names = []
        for line in localparam_lines:
            parts = line.split()
            if len(parts) >= 2:
                localparam_names.append(parts[1])

        assert len(localparam_names) == len(set(localparam_names)), (
            f"Duplicate localparam declarations found: {localparam_names}"
        )

    def test_disabled_has_single_addr_width_param(self, sample_rdl: AddrmapNode) -> None:
        """When NOT unrolled, there should be exactly one addr_width localparam per array."""
        _, pkg_content = _export(sample_rdl, unroll=False)

        count = pkg_content.count("TOP_REGS_ADDR_WIDTH")
        assert count == 1, (
            f"Expected exactly 1 TOP_REGS_ADDR_WIDTH declaration, got {count}"
        )

    def test_multiple_arrays_no_duplicate_localparams(
        self, multiple_arrays_rdl: AddrmapNode
    ) -> None:
        """Multiple distinct arrays should each have at most one addr_width param when unrolled."""
        _, pkg_content = _export(multiple_arrays_rdl, unroll=True)

        localparam_lines = [
            line.strip()
            for line in pkg_content.splitlines()
            if line.strip().startswith("localparam")
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
# E. Struct generation tests
# ===========================================================================


class TestUnrollStruct:
    """Verify the cpuif_sel_t struct generated for unrolled designs."""

    def test_unroll_struct_individual_fields_or_consistent_array(
        self, sample_rdl: AddrmapNode
    ) -> None:
        """When unrolled, the struct should either use individual fields or an internal array
        that is consistently referenced throughout the generated code.

        The key requirement is that all references to the struct fields must be valid.
        If the struct uses `logic regs[4]`, the fanout/fanin must also use array indexing
        that maps correctly to the individual ports.
        """
        content, _ = _export(sample_rdl, unroll=True)

        # Extract the struct definition
        struct_match = re.search(
            r"typedef struct \{(.*?)\} cpuif_sel_t;", content, re.DOTALL
        )
        assert struct_match is not None, "cpuif_sel_t struct not found in output"
        struct_body = struct_match.group(1)

        # The struct must contain fields that cover all 4 array elements.
        # Either as individual fields (regs_0, regs_1, ...) or as an array (regs[4]).
        has_array_field = "regs[4]" in struct_body
        has_individual_fields = all(
            f"regs_{i}" in struct_body for i in range(4)
        )

        assert has_array_field or has_individual_fields, (
            f"Struct must have either 'regs[4]' or individual 'regs_0..regs_3' fields, "
            f"got: {struct_body.strip()}"
        )

    def test_disabled_struct_has_array_field(self, sample_rdl: AddrmapNode) -> None:
        """When NOT unrolled, the struct should use array notation."""
        content, _ = _export(sample_rdl, unroll=False)

        struct_match = re.search(
            r"typedef struct \{(.*?)\} cpuif_sel_t;", content, re.DOTALL
        )
        assert struct_match is not None
        struct_body = struct_match.group(1)

        assert "regs[4]" in struct_body


# ===========================================================================
# F. Decode logic tests
# ===========================================================================


class TestUnrollDecodeLogic:
    """Verify the address decode logic generated for unrolled designs."""

    def test_decode_logic_covers_all_elements(self, sample_rdl: AddrmapNode) -> None:
        """When unrolled, the decode logic must cover all array elements.

        This can be done either with individual if-statements per element,
        or with for-loops that reference the internal struct array.
        Either way, each element must be decoded correctly.
        """
        content, _ = _export(sample_rdl, unroll=True)

        # The write and read decoders must reference all 4 elements
        # They should appear as either regs[0]..regs[3] or regs_0..regs_3
        for flavor in ("wr_sel", "rd_sel"):
            element_refs = []
            for i in range(4):
                # Check for array or individual references
                has_array_ref = f"cpuif_{flavor}.regs[{i}]" in content
                has_indexed_ref = f"cpuif_{flavor}.regs[i" in content  # for loop
                has_individual_ref = f"cpuif_{flavor}.regs_{i}" in content
                element_refs.append(has_array_ref or has_indexed_ref or has_individual_ref)

            assert all(element_refs), (
                f"Decode logic for {flavor} does not cover all 4 elements"
            )

    def test_decode_logic_disabled_uses_for_loops(self, sample_rdl: AddrmapNode) -> None:
        """When NOT unrolled, the decode logic should use for-loops for arrays."""
        content, _ = _export(sample_rdl, unroll=False)

        # Should have a for-loop construct in the decoder
        assert "for (int i0 = 0; i0 < 4; i0++)" in content


# ===========================================================================
# G. AXI4-Lite and flat interface tests
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

        localparam_lines = [
            line.strip()
            for line in pkg_content.splitlines()
            if line.strip().startswith("localparam")
        ]
        localparam_names = [line.split()[1] for line in localparam_lines if len(line.split()) >= 2]

        assert len(localparam_names) == len(set(localparam_names)), (
            f"Duplicate localparam declarations found: {localparam_names}"
        )

    def test_apb4_unroll_all_signals_consistent(self, sample_rdl: AddrmapNode) -> None:
        """APB4 should have consistent signal references throughout when unrolled.

        All references to master ports should use individual instance names,
        never array-indexed names.
        """
        content, _ = _export(sample_rdl, cpuif_cls=APB4Cpuif, unroll=True)

        # Collect all references to master APB port signals
        # They should all be individual (m_apb_regs_N.signal), never array-indexed
        array_refs = re.findall(r"m_apb_regs\[\w+\]", content)
        assert len(array_refs) == 0, (
            f"Found array-indexed master port references when unrolled: {array_refs}"
        )

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
# H. Edge case tests
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

    def test_external_block_array_no_duplicate_localparams(
        self, external_array_rdl: AddrmapNode
    ) -> None:
        """External block array package should not have duplicate localparams when unrolled."""
        _, pkg_content = _export(external_array_rdl, unroll=True)

        localparam_lines = [
            line.strip()
            for line in pkg_content.splitlines()
            if line.strip().startswith("localparam")
        ]
        localparam_names = [line.split()[1] for line in localparam_lines if len(line.split()) >= 2]

        assert len(localparam_names) == len(set(localparam_names)), (
            f"Duplicate localparam declarations found: {localparam_names}"
        )

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

    def test_multiple_arrays_fanout_all_individual(
        self, multiple_arrays_rdl: AddrmapNode
    ) -> None:
        """Fanout for multiple arrays should reference all individual ports."""
        content, _ = _export(multiple_arrays_rdl, unroll=True)

        # All individual ports should be referenced
        for i in range(2):
            assert f"m_apb_alpha_{i}." in content
        for i in range(3):
            assert f"m_apb_beta_{i}." in content


# ===========================================================================
# I. Consistency tests
# ===========================================================================


class TestUnrollConsistency:
    """End-to-end consistency checks for unrolled designs."""

    def test_no_undefined_signal_references(self, sample_rdl: AddrmapNode) -> None:
        """When unrolled, there should be no references to the base array name
        as an array (which would be undefined since ports are individual instances).
        """
        content, _ = _export(sample_rdl, unroll=True)

        # Collect all signal references that look like array accesses to the master ports.
        # Pattern: m_apb_<name>[ (with square bracket, indicating array access)
        # This should not appear since ports are individual.
        array_access_pattern = re.compile(r"m_apb_regs\[")
        matches = array_access_pattern.findall(content)
        assert len(matches) == 0, (
            f"Found {len(matches)} array-indexed references to 'm_apb_regs[' "
            f"which is undefined when ports are unrolled"
        )

    def test_port_names_match_body_references(self, sample_rdl: AddrmapNode) -> None:
        """Every master port declared in the module header should be referenced
        somewhere in the module body (fanout/fanin).
        """
        content, _ = _export(sample_rdl, unroll=True)

        # Extract the module header (everything between "module top (" and ");")
        header_match = re.search(r"module top\s*\((.*?)\);", content, re.DOTALL)
        assert header_match is not None
        header = header_match.group(1)

        # Find all master port names in the header
        master_port_pattern = re.compile(r"m_apb_regs_(\d+)")
        master_ports = master_port_pattern.findall(header)
        assert len(master_ports) == 4, f"Expected 4 master ports, found {len(master_ports)}"

        # Each port should be referenced in the body
        body = content[header_match.end() :]
        for idx in master_ports:
            port_name = f"m_apb_regs_{idx}"
            assert port_name in body, (
                f"Master port '{port_name}' declared in header but never referenced in body"
            )

    def test_unrolled_output_structurally_valid(self, sample_rdl: AddrmapNode) -> None:
        """Basic structural checks on unrolled output: module/endmodule present,
        import statement, etc.
        """
        content, pkg_content = _export(sample_rdl, unroll=True)

        assert "module top" in content
        assert "endmodule" in content
        assert "import top_pkg::*" in content

        assert "package top_pkg" in pkg_content
        assert "endpackage" in pkg_content

    def test_multidim_port_names_match_body_references(
        self, multidim_array_rdl: AddrmapNode
    ) -> None:
        """For multi-dimensional arrays, every declared port should be referenced in the body."""
        content, _ = _export(multidim_array_rdl, unroll=True)

        # All 6 ports (2x3) should be in the header and referenced in the body
        header_match = re.search(r"module top\s*\((.*?)\);", content, re.DOTALL)
        assert header_match is not None

        body = content[header_match.end() :]
        for i in range(2):
            for j in range(3):
                port_name = f"m_apb_matrix_{i}_{j}"
                assert port_name in body, (
                    f"Master port '{port_name}' declared in header but never referenced in body"
                )
