from enum import Enum


class Operator(Enum):
    EQUAL = "=="
    NOT_EQUAL = "!="
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="


class SVAssertion:
    def __init__(
        self,
        left_expr: str,
        right_expr: str,
        operator: Operator = Operator.EQUAL,
        *,
        name: str = "",
        message: str = "",
    ) -> None:
        self._left_expr = left_expr
        self._right_expr = right_expr
        self._operator = operator
        self._name = name
        self._message = message

    def __str__(self) -> str:
        assertion_str = ""
        if self._name:
            assertion_str += f"{self._name}: "
        assertion_str += f"assert ({self._left_expr} {self._operator.value} {self._right_expr})"
        if self._message:
            assertion_str += f'\n\telse $error("{self._message}")'
        return assertion_str + ";"
