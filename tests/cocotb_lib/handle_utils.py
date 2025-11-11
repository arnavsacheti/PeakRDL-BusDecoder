"""Utilities for resolving cocotb signal handles across simulators."""

from __future__ import annotations

from typing import Any, Iterable


class SignalHandle:
    """
    Wrapper that resolves array elements even when the simulator does not expose
    unpacked arrays through ``handle[idx]``.
    """

    def __init__(self, dut, name: str) -> None:
        self._dut = dut
        self._name = name
        self._base = getattr(dut, name, None)
        self._cache: dict[tuple[int, ...], Any] = {}

    def resolve(self, indices: tuple[int, ...]):
        if not indices:
            return self._base if self._base is not None else self._lookup(tuple())

        if indices not in self._cache:
            self._cache[indices] = self._direct_or_lookup(indices)
        return self._cache[indices]

    def _direct_or_lookup(self, indices: tuple[int, ...]):
        if self._base is not None:
            ref = self._base
            try:
                for idx in indices:
                    ref = ref[idx]
                return ref
            except (IndexError, TypeError, AttributeError):
                pass

        return self._lookup(indices)

    def _lookup(self, indices: tuple[int, ...]):
        suffix = "".join(f"[{idx}]" for idx in indices)
        path = f"{self._name}{suffix}"

        try:
            return getattr(self._dut, path)
        except AttributeError:
            pass

        errors: list[Exception] = []
        for extended in (False, True):
            try:
                return self._dut._id(path, extended=extended)
            except (AttributeError, ValueError) as exc:
                errors.append(exc)

        raise AttributeError(f"Unable to resolve handle '{path}' via dut._id") from errors[-1]


def resolve_handle(handle, indices: Iterable[int]):
    """Resolve either a regular cocotb handle or a ``SignalHandle`` wrapper."""
    index_tuple = tuple(indices)

    if isinstance(handle, SignalHandle):
        return handle.resolve(index_tuple)

    ref = handle
    for idx in index_tuple:
        ref = ref[idx]
    return ref
