import textwrap

import pytest
from systemrdl.messages import RDLCompileError

from peakrdl_busdecoder.design_state import DesignState
from peakrdl_busdecoder.utils import clog2


def test_minimal_map_infers_width_and_names(rdl_compile):
    top = rdl_compile(
        """
        addrmap minimal {
            reg {
                field {sw=rw; hw=r;} value[31:0] = 0;
            } reg0 @ 0x0;
        };
        """,
        top="minimal",
        inst_name="package",
    )

    ds = DesignState(top, {})

    assert ds.cpuif_data_width == 32
    expected_addr_width = max(clog2(top.size), clog2(ds.cpuif_data_width // 8) + 1)
    assert ds.addr_width == expected_addr_width
    assert ds.module_name == "package_"
    assert ds.package_name == "package__pkg"


def test_external_only_design_uses_warning_defaults(rdl_compile):
    top = rdl_compile(
        """
        addrmap ext_only {
            reg shell_reg {
                field {sw=rw; hw=r;} value[31:0] = 0;
            };

            external shell_reg ext_reg @ 0x0;
            external regfile {
                reg {
                    field {sw=rw; hw=r;} value[31:0] = 0;
                } r0 @ 0x0;
            } ext_rf @ 0x100;

            external addrmap {
                reg {
                    field {sw=rw; hw=r;} value[31:0] = 0;
                } r0 @ 0x0;
            } ext_map @ 0x200;
        };
        """,
        top="ext_only",
    )

    ds = DesignState(top, {})

    assert ds.cpuif_data_width == 32
    assert ds.has_external_addressable is True
    assert ds.has_external_block is True


def test_address_width_override_validation(rdl_compile):
    top = rdl_compile(
        """
        addrmap override_test {
            reg {
                field {sw=rw; hw=r;} value[31:0] = 0;
            } r0 @ 0x0;
            reg {
                field {sw=rw; hw=r;} value[31:0] = 0;
            } r1 @ 0x4;
        };
        """,
        top="override_test",
    )

    base_ds = DesignState(top, {})

    with pytest.raises(RDLCompileError):
        DesignState(top, {"address_width": base_ds.addr_width - 1})

    widened_ds = DesignState(top, {"address_width": base_ds.addr_width + 2})
    assert widened_ds.addr_width == base_ds.addr_width + 2


@pytest.mark.parametrize(
    "external_decl",
    [
        """
        external regfile {
            reg {
                field {sw=rw; hw=r;} value[31:0] = 0;
            } r0 @ 0x0;
        } ext_rf @ 0x100;
        """,
        """
        external addrmap {
            reg {
                field {sw=rw; hw=r;} value[31:0] = 0;
            } r0 @ 0x0;
        } ext_map @ 0x100;
        """,
    ],
    ids=["regfile", "addrmap"],
)
def test_design_scanner_marks_external_blocks(rdl_compile, external_decl):
    external_block = textwrap.indent(textwrap.dedent(external_decl).strip(), "    ")
    source = textwrap.dedent(
        """
        addrmap top {
            reg {
                field {sw=rw; hw=r;} value[31:0] = 0;
            } r0 @ 0x0;
        %s
        };
        """
        % external_block
    )

    top = rdl_compile(source, top="top")
    ds = DesignState(top, {})

    assert ds.has_external_addressable is True
    assert ds.has_external_block is True
