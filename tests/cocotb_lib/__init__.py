"""Manifest of SystemRDL sources used by the cocotb simulations."""

RDL_CASES: list[tuple[str, str]] = [
    ("simple.rdl", "simple_test"),
    ("multiple_reg.rdl", "multi_reg"),
    ("deep_hierarchy.rdl", "deep_hierarchy"),
    ("wide_status.rdl", "wide_status"),
    ("variable_layout.rdl", "variable_layout"),
    ("asymmetric_bus.rdl", "asymmetric_bus"),
]
