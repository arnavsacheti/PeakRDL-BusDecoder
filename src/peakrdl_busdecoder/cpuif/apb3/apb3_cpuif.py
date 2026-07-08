"""Thin re-export shim for API stability.

The APB3 cpuif now lives in the shared ``cpuif/apb`` package. This module
keeps the historical ``cpuif.apb3.apb3_cpuif`` import path working.
"""

from ..apb.apb_cpuif import APB3Cpuif, APB3CpuifFlat

__all__ = ["APB3Cpuif", "APB3CpuifFlat"]
