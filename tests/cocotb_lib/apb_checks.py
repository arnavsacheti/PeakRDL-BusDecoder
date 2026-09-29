"""Shared APB3/APB4 response timing checks."""

from __future__ import annotations

from typing import Any

from cocotb.triggers import Timer

from tests.cocotb_lib.protocol_utils import (
    all_index_pairs,
    find_invalid_address,
    get_int,
    set_value,
    start_clock,
)


async def check_invalid_address_response(
    dut, slave, masters: dict[str, dict[str, Any]], config: dict[str, Any]
) -> None:
    """Check error phases and back-to-back recovery for reads and writes."""
    invalid_addr = find_invalid_address(config)
    if invalid_addr is None:
        dut._log.warning("No unmapped address found; skipping invalid address test")
        return

    await start_clock(slave.PCLK)
    if slave.PRESETn is not None:
        slave.PRESETn.value = 1
    slave.PSEL.value = 0
    slave.PENABLE.value = 0
    slave.PWRITE.value = 0
    slave.PADDR.value = invalid_addr
    slave.PWDATA.value = 0
    if hasattr(slave, "PPROT"):
        slave.PPROT.value = 0
    if hasattr(slave, "PSTRB"):
        slave.PSTRB.value = 0

    # A peripheral may hold PREADY high even in setup. Its response must not
    # leak into unmapped or unselected transfers.
    for master_name, index in all_index_pairs(masters):
        inputs = masters[master_name]["inputs"]
        set_value(inputs["PREADY"], index, 1)
        set_value(inputs["PSLVERR"], index, 0)
        set_value(inputs["PRDATA"], index, 0)

    async def check_phase(
        phase: str, ready: int, error: int, selected: tuple[str, tuple[int, ...]] | None = None
    ) -> None:
        # The decoder is combinational; allow all fanout/fanin logic to settle.
        await Timer(1, unit="ns")
        assert int(slave.PREADY.value) == ready, f"{phase}: unexpected PREADY"
        assert int(slave.PSLVERR.value) == error, f"{phase}: unexpected PSLVERR"
        for master_name, index in all_index_pairs(masters):
            outputs = masters[master_name]["outputs"]
            is_selected = (master_name, index) == selected
            assert get_int(outputs["PSEL"], index) == int(is_selected), (
                f"{phase}: unexpected PSEL on {master_name}{index}"
            )
            if is_selected:
                assert get_int(outputs["PENABLE"], index) == int(slave.PENABLE.value), (
                    f"{phase}: selected peripheral must receive PENABLE"
                )
                assert get_int(outputs["PWRITE"], index) == int(slave.PWRITE.value), (
                    f"{phase}: selected peripheral must receive PWRITE"
                )
            else:
                assert get_int(outputs["PENABLE"], index) == 0, (
                    f"{phase}: unselected peripheral {master_name}{index} must hold PENABLE low"
                )

    valid_txn = config["transactions"][0]
    valid_target = (valid_txn["master"], tuple(valid_txn["index"]))
    addr_mask = (1 << config["address_width"]) - 1

    for write in (0, 1):
        operation = "write" if write else "read"
        slave.PADDR.value = invalid_addr
        slave.PWRITE.value = write
        slave.PWDATA.value = (0xCAFE_BABE & ((1 << config["data_width"]) - 1)) if write else 0
        if hasattr(slave, "PSTRB"):
            slave.PSTRB.value = ((1 << config["byte_width"]) - 1) if write else 0

        # PENABLE can be high while this decoder is unselected on a shared bus.
        slave.PSEL.value = 0
        for enable in (0, 1):
            slave.PENABLE.value = enable
            await check_phase(f"{operation} unselected, PENABLE={enable}", 0, 0)

        slave.PSEL.value = 1
        # Keep PSEL asserted across two invalid transfers to catch errors left
        # asserted in the next setup phase.
        for transfer in range(2):
            slave.PENABLE.value = 0
            await check_phase(f"{operation} invalid {transfer} setup", 0, 0)
            slave.PENABLE.value = 1
            await check_phase(f"{operation} invalid {transfer} access", 1, 1)

        # Follow the error immediately with a mapped transfer. Its PSEL must
        # assert in setup, and its PREADY must pass through without gating.
        slave.PADDR.value = valid_txn["address"] & addr_mask
        slave.PENABLE.value = 0
        await check_phase(f"{operation} valid setup after error", 1, 0, valid_target)
        slave.PENABLE.value = 1
        await check_phase(f"{operation} valid access after error", 1, 0, valid_target)

        slave.PSEL.value = 0
        slave.PENABLE.value = 0
        await check_phase(f"{operation} idle after completion", 0, 0)
