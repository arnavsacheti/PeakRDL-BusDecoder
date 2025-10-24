from typing import Protocol

from typing_extensions import Self


class SupportsStr(Protocol):
    def __str__(self) -> str: ...


class Body:
    def __init__(self) -> None:
        self.lines: list[SupportsStr] = []

    def __str__(self) -> str:
        return "\n".join(map(str, self.lines))

    def __add__(self, other: SupportsStr) -> Self:
        self.lines.append(other)
        return self

    def __bool__(self) -> bool:
        return bool(self.lines)
