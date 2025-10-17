from textwrap import indent
from .body import Body


class WhileLoopBody(Body):
    def __init__(self, condition: str):
        super().__init__()
        self._condition = condition

    def __str__(self) -> str:
        return f"""while ({self._condition}) begin
            {indent(super().__str__(), "\t")}
        end"""
