from textwrap import indent

from .body import Body


class StructBody(Body):
    def __init__(self, name: str, packed: bool = True) -> None:
        super().__init__()
        self._name = name
        self._packed = packed

    def __str__(self) -> str:
        return f"""typedef struct {"packed " if self._packed else ""} {{
{indent(super().__str__(), "    ")}
}} {self._name};"""
