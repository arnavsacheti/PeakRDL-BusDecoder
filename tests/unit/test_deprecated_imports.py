"""The pre-0.7.0b4 import paths must keep working (with a DeprecationWarning)."""

import importlib
import sys

import pytest

from peakrdl_busdecoder.cpuif.apb.apb_interface import APBFlatInterface, APBSVInterface

_DEPRECATED_INTERFACE_MODULES = [
    "peakrdl_busdecoder.cpuif.apb3.apb3_interface",
    "peakrdl_busdecoder.cpuif.apb4.apb4_interface",
]


@pytest.mark.parametrize("module_name", _DEPRECATED_INTERFACE_MODULES)
def test_deprecated_interface_module_warns(module_name: str) -> None:
    sys.modules.pop(module_name, None)
    with pytest.warns(DeprecationWarning, match="is deprecated"):
        importlib.import_module(module_name)


def test_apb3_interface_aliases() -> None:
    from peakrdl_busdecoder.cpuif.apb3.apb3_interface import (
        APB3FlatInterface,
        APB3SVInterface,
    )

    assert issubclass(APB3SVInterface, APBSVInterface)
    assert issubclass(APB3FlatInterface, APBFlatInterface)
    assert APB3SVInterface.get_interface_type(object.__new__(APB3SVInterface)) == "apb3_intf"


def test_apb4_interface_aliases() -> None:
    from peakrdl_busdecoder.cpuif.apb4.apb4_interface import (
        APB4FlatInterface,
        APB4SVInterface,
    )

    assert issubclass(APB4SVInterface, APBSVInterface)
    assert issubclass(APB4FlatInterface, APBFlatInterface)
    assert APB4SVInterface.get_interface_type(object.__new__(APB4SVInterface)) == "apb4_intf"


def test_cpuif_shim_paths_still_work() -> None:
    """The silent cpuif re-export shims from #66 must also keep resolving."""
    from peakrdl_busdecoder.cpuif.apb.apb_cpuif import APB3Cpuif as NewAPB3
    from peakrdl_busdecoder.cpuif.apb.apb_cpuif import APB4Cpuif as NewAPB4
    from peakrdl_busdecoder.cpuif.apb3 import APB3Cpuif
    from peakrdl_busdecoder.cpuif.apb3.apb3_cpuif import APB3CpuifFlat  # noqa: F401
    from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif
    from peakrdl_busdecoder.cpuif.apb4.apb4_cpuif import APB4CpuifFlat  # noqa: F401

    assert APB3Cpuif is NewAPB3
    assert APB4Cpuif is NewAPB4
