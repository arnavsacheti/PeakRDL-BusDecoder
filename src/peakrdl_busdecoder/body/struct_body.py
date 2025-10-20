from textwrap import indent

from .body import Body


class StructBody(Body):
    def __init__(self, name: str, typedef: bool = False, packed: bool = False) -> None:
        super().__init__()
        self._name = name
        self._typedef = typedef
        self._packed = packed

    @property
    def name(self) -> str:
        return self._name

    def __str__(self) -> str:
        if self._typedef:
            return f"""typedef struct {"packed " if self._packed else ""}{{
{indent(super().__str__(), "    ")}
}} {self._name};"""

        return f"""struct {{
{indent(super().__str__(), "    ")}
}} {self._name};"""
