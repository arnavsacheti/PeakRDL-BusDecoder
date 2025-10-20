from textwrap import indent

from .body import Body


class CombinationalBody(Body):
    def __str__(self) -> str:
        return f"""always_comb begin
{indent(super().__str__(), "    ")}
end"""
