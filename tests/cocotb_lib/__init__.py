"""Manifest of SystemRDL sources used by the cocotb simulations."""

RDL_CASES: list[tuple[str, str]] = [
    ("simple.rdl", "simple_test"),
    ("multiple_reg.rdl", "multi_reg"),
    ("deep_hierarchy.rdl", "deep_hierarchy"),
    ("wide_status.rdl", "wide_status"),
    ("wide_access_64.rdl", "wide_access_64"),
    ("wide_access_128.rdl", "wide_access_128"),
    ("variable_layout.rdl", "variable_layout"),
    ("asymmetric_bus.rdl", "asymmetric_bus"),
    ("array_only.rdl", "decode_repro"),
]
