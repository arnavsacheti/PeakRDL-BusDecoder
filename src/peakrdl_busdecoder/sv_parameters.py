class SVParameter:
    def __init__(self, name: str, value: int) -> None:
        self.name = name
        self.value = value

    def __str__(self) -> str:
        return f"parameter {self.name} = {self.value}"

    def __repr__(self) -> str:
        return f"SVParameter(name={self.name}, value={self.value})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SVParameter):
            return self.name == other.name and self.value == other.value
        if isinstance(other, SVLocalParam):
            return self.name == other.name and self.value == other.value
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        """
        Less-than comparison for sorting.
        Follows Alhabetic order based on name.
        """
        if isinstance(other, SVParameter):
            return self.name < other.name
        if isinstance(other, SVLocalParam):
            return True
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.name, self.value))


class SVLocalParam:
    def __init__(self, name: str, value: int) -> None:
        self.name = name
        self.value = value

    def __str__(self) -> str:
        return f"localparam {self.name} = {self.value}"

    def __repr__(self) -> str:
        return f"SVLocalParam(name={self.name}, value={self.value})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SVLocalParam):
            return self.name == other.name and self.value == other.value
        if isinstance(other, SVParameter):
            return self.name == other.name and self.value == other.value
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, SVLocalParam):
            return self.name < other.name
        if isinstance(other, SVParameter):
            return False
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.name, self.value))
