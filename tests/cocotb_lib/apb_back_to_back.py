"""Independent logical ledger for the autonomous APB child RTL peripherals."""

from __future__ import annotations

import os
from dataclasses import dataclass
from types import SimpleNamespace

import cocotb
from cocotb.triggers import Timer

from tests.cocotb_lib.protocol_utils import apb_access, apb_setup


@dataclass(frozen=True)
class Transfer:
    address: int
    child: int | None
    local: int = 0
    write: bool = False
    data: int = 0
    strobe: int | None = None
    waits: int = 0
    error: bool = False
    # Literal read results, APB3 then APB4 if the protocols differ.
    read_data: int | tuple[int, int] = 0


# Fixed expected address map: first = [0x20,0x30), second = [0x40,0x50).
# These child/local decisions, waits and read values are NOT exporter metadata
# or response inputs supplied by this driver. The RTL children own all readback.
TRANSFERS = (
    Transfer(0x20, 0, write=True, data=0x11223344),
    Transfer(0x20, 0, read_data=0x11223344),
    Transfer(0x44, 1, 4, write=True, data=0xA1B2C3D4, strobe=0x5, waits=2),
    Transfer(0x24, 0, 4, waits=1, read_data=0x50607080),
    Transfer(0x24, 0, 4, write=True, data=0x89ABCDEF, strobe=0xA, waits=1),
    Transfer(0x24, 0, 4, waits=1, read_data=(0x89ABCDEF, 0x8960CD80)),
    Transfer(0x44, 1, 4, waits=2, read_data=(0xA1B2C3D4, 0xD0B2F0D4)),
    Transfer(0x40, 1, write=True, data=0x55667788),
    Transfer(0x40, 1, write=True, data=0xFFFFFFFF, strobe=0),
    Transfer(0x40, 1, read_data=(0xFFFFFFFF, 0x55667788)),
    Transfer(0x2C, 0, 12, write=True, data=0xDEADBEEF, waits=1, error=True),
    Transfer(0x4C, 1, 12, waits=1, error=True, read_data=0xBAD00001),
    Transfer(0x30, None, write=True, data=0xCAFEBABE, error=True),
    Transfer(0xF0, None, error=True),
    Transfer(0x28, 0, 8, read_data=3),
    Transfer(0x28, 0, 8, read_data=4),
    Transfer(0x48, 1, 8, read_data=2),
    Transfer(0x20, 0, write=True, data=0xDEADBEEF, strobe=0x3),
    Transfer(0x20, 0, read_data=(0xDEADBEEF, 0x1122BEEF)),
    Transfer(0x44, 1, 4, waits=2, read_data=(0xA1B2C3D4, 0xD0B2F0D4)),
)


@cocotb.test()
async def stateful_back_to_back(dut) -> None:
    """Every transfer has one SETUP edge; ACCESS may have real wait edges."""
    apb4 = os.environ["APB_TEST_PROTOCOL"] == "apb4"
    signals = ("PSEL", "PENABLE", "PWRITE", "PADDR", "PWDATA", "PRDATA", "PREADY", "PSLVERR")
    if apb4:
        signals += ("PPROT", "PSTRB")
    slave = SimpleNamespace(**{name: getattr(dut, f"s_apb_{name}") for name in signals})

    def number(handle) -> int:
        return int(handle.value)

    def child_signal(child: int, signal: str):
        return getattr(dut, f"child{child}_{signal}")

    async def edge() -> None:
        dut.clk.value = 1
        await Timer(1, unit="ns")
        dut.clk.value = 0
        await Timer(1, unit="ns")

    # Expected architectural state starts from literal peripheral reset values.
    expected = [
        dict(completions=0, errors=0, read_effects=0, write_effects=0,
             memory0=0x10203040, memory1=0x50607080),
        dict(completions=0, errors=0, read_effects=0, write_effects=0,
             memory0=0x90A0B0C0, memory1=0xD0E0F000),
    ]
    accepted = 0
    returned_errors = 0

    def check_state(context: str) -> None:
        assert number(dut.accepted) == accepted, f"{context}: upstream acceptance count"
        assert number(dut.returned_errors) == returned_errors, f"{context}: upstream error count"
        for child, state in enumerate(expected):
            for name, value in state.items():
                actual = number(child_signal(child, name))
                assert actual == value, (
                    f"{context}: child{child} {name}: actual={actual:#x}, expected={value:#x}"
                )

    dut.clk.value = 0
    dut.resetn.value = 0
    for name in ("PSEL", "PENABLE", "PWRITE", "PADDR", "PWDATA"):
        getattr(slave, name).value = 0
    if apb4:
        slave.PSTRB.value = 0
        slave.PPROT.value = 0
    await Timer(1, unit="ns")
    await edge()
    await edge()
    dut.resetn.value = 1
    await Timer(1, unit="ns")
    check_state("reset")

    for ordinal, txn in enumerate(TRANSFERS):
        context = f"transfer {ordinal} address={txn.address:#x}"
        strobe = (0xF if txn.strobe is None else txn.strobe) if txn.write else 0
        protection = ordinal & 7

        def check_bus(phase: str, enabled: bool, ready: bool) -> None:
            assert number(slave.PSEL) == 1, f"{context}: PSEL must stay high between transfers"
            assert number(slave.PENABLE) == enabled, f"{context}: {phase} PENABLE"
            assert number(slave.PREADY) == ready, f"{context}: {phase} PREADY"
            assert number(slave.PSLVERR) == (txn.error and ready), f"{context}: {phase} PSLVERR"
            for child in range(2):
                hit = child == txn.child
                for signal, value in (("PSEL", hit), ("PENABLE", hit and enabled),
                                      ("PWRITE", hit and txn.write)):
                    assert number(child_signal(child, signal)) == value, (
                        f"{context}: {phase} child{child} {signal}"
                    )
                if hit:
                    assert number(child_signal(child, "PADDR")) == txn.local, (
                        f"{context}: {phase} selected local address"
                    )
                # Payload is broadcast even to unselected children; it must not
                # become stale or acquire PSEL/PWRITE-based sanitization.
                assert number(child_signal(child, "PWDATA")) == txn.data, (
                    f"{context}: {phase} child{child} write-data forwarding"
                )
                if apb4:
                    actual = number(child_signal(child, "PSTRB"))
                    assert actual == strobe, (
                        f"{context}: {phase} child{child} PSTRB={actual:#x}, expected={strobe:#x}; "
                        "read PSTRB must be zero throughout SETUP/ACCESS/waits"
                    )
                    assert number(child_signal(child, "PPROT")) == protection
            if ready:
                read_data = txn.read_data
                if isinstance(read_data, tuple):
                    read_data = read_data[1 if apb4 else 0]
                wanted = 0 if txn.write else read_data
                assert number(slave.PRDATA) == wanted, f"{context}: {phase} independent readback"

        # The real shared helper is deliberately used here: before issue82's
        # correction its default read PSTRB is full, observed at child SETUP.
        await apb_setup(slave, txn.address, txn.write, txn.data, strobe_mask=txn.strobe)
        if apb4:
            slave.PPROT.value = protection
            await Timer(1, unit="ns")
        check_bus("SETUP", False, txn.child is not None and txn.waits == 0)
        check_state(f"{context} before SETUP edge")
        await edge()
        check_state(f"{context} after SETUP edge (no side effects)")

        await apb_access(slave)
        for wait in range(txn.waits + 1):
            ready = wait == txn.waits
            phase = f"ACCESS {wait}"
            check_bus(phase, True, ready)
            check_state(f"{context} before {phase} edge")
            if ready:
                # Commit the independent logical transaction, never the DUT's
                # child select, address, payload, counters, or response values.
                accepted += 1
                returned_errors += int(txn.error)
                if txn.child is not None:
                    state = expected[txn.child]
                    state["completions"] += 1
                    if txn.error:
                        state["errors"] += 1
                    elif txn.write:
                        effective_strobe = strobe if apb4 else 0xF
                        if effective_strobe:
                            state["write_effects"] += 1
                            if txn.local in (0, 4):
                                word = f"memory{txn.local // 4}"
                                for lane in range(4):
                                    if effective_strobe & (1 << lane):
                                        mask = 0xFF << (8 * lane)
                                        state[word] = (state[word] & ~mask) | (txn.data & mask)
                    else:
                        state["read_effects"] += 1
            await edge()
            check_state(f"{context} after {phase} edge")

    # Verify direct idle payload forwarding and shared-bus PENABLE isolation.
    # No selected child may complete or replay the final transfer on these edges.
    slave.PSEL.value = 0
    slave.PWRITE.value = 1
    slave.PWDATA.value = 0xC001CAFE
    if apb4:
        slave.PSTRB.value = 0x5
    for enable in (0, 1, 0):
        slave.PENABLE.value = enable
        await Timer(1, unit="ns")
        assert number(slave.PREADY) == number(slave.PSLVERR) == number(slave.PRDATA) == 0
        for child in range(2):
            for signal in ("PSEL", "PENABLE", "PWRITE"):
                assert number(child_signal(child, signal)) == 0
            assert number(child_signal(child, "PWDATA")) == 0xC001CAFE
            if apb4:
                assert number(child_signal(child, "PSTRB")) == 0x5
        await edge()
        check_state("idle after final acceptance")

    # Fixed final maps additionally pin the ledger's byte-lane calculation.
    final_memory = ((0x1122BEEF, 0x8960CD80), (0x55667788, 0xD0B2F0D4)) if apb4 else (
        (0xDEADBEEF, 0x89ABCDEF), (0xFFFFFFFF, 0xA1B2C3D4)
    )
    for child, words in enumerate(final_memory):
        assert tuple(number(child_signal(child, f"memory{word}")) for word in range(2)) == words
    assert number(dut.accepted) == 20
    assert number(dut.returned_errors) == 4
    assert tuple(number(child_signal(child, "completions")) for child in range(2)) == (10, 8)
    assert tuple(number(child_signal(child, "errors")) for child in range(2)) == (1, 1)
    assert tuple(number(child_signal(child, "read_effects")) for child in range(2)) == (6, 4)
    assert tuple(number(child_signal(child, "write_effects")) for child in range(2)) == (3, 2 if apb4 else 3)
    dut._log.info("APB_B2B_OK: 20 upstream transfers, 18 child handshakes, 4 errors")
