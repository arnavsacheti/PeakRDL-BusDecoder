from textwrap import indent

from peakrdl_busdecoder.body import Body


class InitialBody(Body):
    def __str__(self) -> str:
        return f"""initial begin
{indent(super().__str__(), "    ")}
end"""
