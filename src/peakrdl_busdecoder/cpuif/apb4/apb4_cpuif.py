"""Thin re-export shim for API stability.

The APB4 cpuif now lives in the shared ``cpuif/apb`` package. This module
keeps the historical ``cpuif.apb4.apb4_cpuif`` import path working.
"""

from ..apb.apb_cpuif import APB4Cpuif, APB4CpuifFlat

__all__ = ["APB4Cpuif", "APB4CpuifFlat"]
