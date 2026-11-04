from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NodeMeta:
    has_only_external_addressable_children: bool
    has_addressable_children: bool
    array_strides: tuple[int, ...] | None
    rel_path: str
