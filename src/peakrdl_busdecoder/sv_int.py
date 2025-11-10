from typing import Literal


class SVInt:
    def __init__(self, value: int, width: int | None = None) -> None:
        self.value = value
        self.width = width

    def __str__(self) -> str:
        if self.width is not None:
            # Explicit width
            return f"{self.width}'h{self.value:x}"
        elif self.value.bit_length() > 32:
            # SV standard only enforces that unsized literals shall be at least 32-bits
            # To support larger literals, they need to be sized explicitly
            return f"{self.value.bit_length()}'h{self.value:x}"
        else:
            return f"'h{self.value:x}"

    def __add__(self, other: "SVInt") -> "SVInt":
        if self.width is not None and other.width is not None:
            return SVInt(self.value + other.value, max(self.width, other.width))
        else:
            return SVInt(self.value + other.value, None)

    def __sub__(self, other: "SVInt") -> "SVInt":
        if self.width is not None and other.width is not None:
            return SVInt(self.value - other.value, max(self.width, other.width))
        else:
            return SVInt(self.value - other.value, None)

    def __len__(self) -> int:
        if self.width is not None:
            return self.width
        else:
            return self.value.bit_length()

    def to_bytes(self, byteorder: Literal["little", "big"] = "little") -> bytes:
        byte_length = (self.value.bit_length() + 7) // 8
        return self.value.to_bytes(byte_length, byteorder)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SVInt):
            return NotImplemented
        return self.value == other.value and self.width == other.width

    def __hash__(self) -> int:
        return hash((self.value, self.width))
