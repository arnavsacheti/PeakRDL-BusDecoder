from textwrap import indent
from types import EllipsisType

from typing_extensions import Self

from .body import Body, SupportsStr


class IfBody(Body):
    def __init__(self) -> None:
        super().__init__()
        # (None means 'else')
        self._branches: list[tuple[SupportsStr | None, Body]] = []
        self._has_else = False

    # --- Item access: if/else-if via condition; else via Ellipsis/None ---
    def __getitem__(self, condition: SupportsStr | EllipsisType | None) -> Body:
        if self._has_else:
            raise RuntimeError("Cannot add branches after an 'else' branch.")
        if condition is Ellipsis or condition is None:
            if self._has_else:
                raise RuntimeError("Only one 'else' branch is allowed.")
            self._has_else = True
            b = Body()
            self._branches.append((None, b))
            return b
        # conditional branch
        b = Body()
        self._branches.append((condition, b))
        return b

    # --- In-place or: if/else-if via (cond, Body); else via Body ---
    def __ior__(self, other: tuple[SupportsStr, Body] | Body) -> Self:
        if isinstance(other, Body):
            if self._has_else:
                raise RuntimeError("Only one 'else' branch is allowed.")
            if self._has_else or (self._branches and self._branches[-1][0] is None):
                raise RuntimeError("Cannot add branches after an 'else' branch.")
            self._branches.append((None, other))
            self._has_else = True
            return self

        cond, body = other
        if self._has_else:
            raise RuntimeError("Cannot add branches after an 'else' branch.")
        self._branches.append((cond, body))
        return self

    # --- Context manager for a branch ---
    class _BranchCtx:
        def __init__(self, outer: "IfBody", condition: SupportsStr | None) -> None:
            self._outer = outer
            # route through __getitem__ to reuse validation logic
            self._body = outer[Ellipsis if condition is None else condition]

        def __enter__(self) -> Body:
            return self._body

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: object | None,
        ) -> bool:
            return False

    def cm(self, condition: SupportsStr | None) -> "IfBody._BranchCtx":
        """Use with: with ifb.cm('cond') as b: ...  ; use None for else."""
        return IfBody._BranchCtx(self, condition)

    # --- Rendering ---
    def __str__(self) -> str:
        out: list[str] = []
        for i, (cond, body) in enumerate(self._branches):
            if i == 0 and cond is not None:
                out.append(f"if ({cond}) begin")
            elif cond is not None:
                out.append(f"else if ({cond}) begin")
            else:
                out.append("else begin")
            body_str = str(body)
            if body_str:
                out.extend(indent(ln, "    ") for ln in body_str.splitlines())
            out.append("end")
        return "\n".join(out)

    def __len__(self) -> int:
        return len(self._branches)

    def __bool__(self) -> bool:
        return bool(self._branches)
