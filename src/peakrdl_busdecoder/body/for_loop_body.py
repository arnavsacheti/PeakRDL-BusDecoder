from textwrap import indent

from .body import Body


class ForLoopBody(Body):
    def __init__(self, type: str, iterator: str, dim: int) -> None:
        super().__init__()
        self._type = type
        self._iterator = iterator
        self._dim = dim

    def __str__(self) -> str:
        return f"""for ({self._type} {self._iterator} = 0; {self._iterator} < {self._dim}; {self._iterator}++) begin
{indent(super().__str__(), "    ")}
end"""
