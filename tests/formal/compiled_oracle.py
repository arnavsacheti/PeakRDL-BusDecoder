"""Independent decode tables and a clocked, endpoint-accounted AXI4-Lite driver."""

from __future__ import annotations

from textwrap import dedent

from tests.formal.reference_model import Direction, FormalBusDecoderModel, TargetElement

# Values are fixture-owned C++ member expressions with a {name} signal slot.
PortBindings = dict[tuple[str, tuple[int, ...]], str]


def cpp_expected_table(model: FormalBusDecoderModel) -> str:
    """Materialize every byte/direction decision without generator metadata."""
    target_indices = {target: index for index, target in enumerate(model.targets)}
    tables = []
    for direction in (Direction.READ, Direction.WRITE):
        rows = []
        for address in range(model.address_space_size):
            result = model.decode(address, direction)
            assert not result.competing_hits, f"Ambiguous oracle decode: {result}"
            child = -1 if result.hit is None else target_indices[result.hit]
            offset = 0 if result.local_offset is None else result.local_offset
            rows.append(f"        {{{child}, {offset}, {str(result.is_error).lower()}}}")
        tables.append("    {\n" + ",\n".join(rows) + "\n    }")
    return ",\n".join(tables)


def axil_testbench(
    module_name: str, model: FormalBusDecoderModel, bindings: PortBindings
) -> str:
    """Use real edges for independent AW/W/AR, child stalls and held responses.

    There is one transaction in flight, not an approximation of AXIL by a
    combinational request. Both upstream and downstream write-channel orders
    vary. Every child request and response handshake is counted at its edge.
    """
    assert model.data_width == 32
    assert set(bindings) == {(target.target_name, target.indices) for target in model.targets}

    def signal(target: TargetElement, name: str) -> str:
        return "dut." + bindings[target.target_name, target.indices].format(name=name)

    child_inputs = "\n".join(
        f"    {signal(target, name)} = inputs[{index}].{name.lower()};"
        for index, target in enumerate(model.targets)
        for name in ("AWREADY", "WREADY", "BVALID", "BRESP", "ARREADY", "RVALID", "RRESP", "RDATA")
    )
    child_outputs = "\n".join(
        f"    outputs[{index}] = {{"
        + ", ".join(
            signal(target, name)
            for name in (
                "AWVALID", "AWADDR", "AWPROT", "WVALID", "WDATA", "WSTRB", "BREADY",
                "ARVALID", "ARADDR", "ARPROT", "RREADY",
            )
        )
        + "};"
        for index, target in enumerate(model.targets)
    )
    template = dedent(r"""
        #include <cstdint>
        #include <iostream>
        #include "V@MODULE@.h"
        #include "verilated.h"

        static constexpr unsigned kAddressCount = @ADDRESS_COUNT@;
        static constexpr unsigned kChildCount = @CHILD_COUNT@;
        static constexpr unsigned kProfiles = 3;
        struct Expected {
            int child;
            std::uint32_t local_address;
            bool error;
        };
        static constexpr Expected expected[2][kAddressCount] = {
        @EXPECTED@
        };
        struct ChildInputs {
            std::uint32_t awready, wready, bvalid, bresp, arready, rvalid, rresp, rdata;
        };
        struct ChildOutputs {
            std::uint32_t awvalid, awaddr, awprot, wvalid, wdata, wstrb, bready;
            std::uint32_t arvalid, araddr, arprot, rready;
        };
        struct Counts {
            unsigned aw = 0, w = 0, ar = 0, b = 0, r = 0;
        };

        static void drive_children(V@MODULE@& dut, const ChildInputs* inputs) {
        @CHILD_INPUTS@
        }
        static void sample_children(const V@MODULE@& dut, ChildOutputs* outputs) {
        @CHILD_OUTPUTS@
        }
        static void edge(V@MODULE@& dut) {
            dut.clk = 1;
            dut.eval();
            dut.clk = 0;
            dut.eval();
        }
        static void idle_upstream(V@MODULE@& dut) {
            dut.s_axil_AWVALID = 0;
            dut.s_axil_AWADDR = 0;
            dut.s_axil_AWPROT = 0;
            dut.s_axil_WVALID = 0;
            dut.s_axil_WDATA = 0;
            dut.s_axil_WSTRB = 0;
            dut.s_axil_BREADY = 0;
            dut.s_axil_ARVALID = 0;
            dut.s_axil_ARADDR = 0;
            dut.s_axil_ARPROT = 0;
            dut.s_axil_RREADY = 0;
        }

        struct Context {
            unsigned address, direction, profile, cycle;
            bool matches(const char* signal, std::uint32_t actual, std::uint32_t wanted,
                         int child = -1) const {
                if (actual == wanted) return true;
                std::cerr << signal << " mismatch: address=0x" << std::hex << address
                          << std::dec << " direction=" << (direction ? "write" : "read")
                          << " profile=" << profile << " cycle=" << cycle << " child=" << child
                          << " actual=0x" << std::hex << actual << " expected=0x" << wanted
                          << std::dec << std::endl;
                return false;
            }
        };

        static bool transaction(V@MODULE@& dut, unsigned address, unsigned direction,
                                unsigned profile, Counts* endpoints, Counts& upstream) {
            const Expected& oracle = expected[direction][address];
            const bool write = direction != 0;
            const std::uint32_t data = 0x13579BDFu ^ (address * 0x10001u) ^ profile;
            const std::uint32_t strobe = (address + profile) % 15u + 1u;
            const std::uint32_t prot = (address + profile) & 7u;
            const std::uint32_t response = profile == 0 ? 0u : profile == 1 ? 2u : 3u;
            const std::uint32_t read_data = 0x9E3779B9u * (oracle.child + 2u)
                ^ (address * 0x01010101u) ^ (profile * 0x00102041u);
            // AW-first, W-first and simultaneous upstream and downstream cases.
            const unsigned aw_start = profile == 1 ? 3u : 0u;
            const unsigned w_start = profile == 0 ? 3u : 0u;
            const unsigned aw_ready_start = profile == 1 ? 9u : 5u;
            const unsigned w_ready_start = profile == 0 ? 9u : 5u;
            bool up_aw = false, up_w = false, up_ar = false;
            bool child_aw = false, child_w = false, child_ar = false;
            bool child_response = false, upstream_response = false;
            int request_cycle = -1;
            unsigned response_wait = 0;
            ChildInputs inputs[kChildCount] = {};
            ChildOutputs outputs[kChildCount];
            Context context{address, direction, profile, 0};

            for (unsigned cycle = 0; cycle < 80; ++cycle) {
                context.cycle = cycle;
                dut.s_axil_AWVALID = write && !up_aw && cycle >= aw_start;
                dut.s_axil_AWADDR = up_aw ? (address ^ 0x5Du) : address;
                dut.s_axil_AWPROT = up_aw ? (prot ^ 7u) : prot;
                dut.s_axil_WVALID = write && !up_w && cycle >= w_start;
                dut.s_axil_WDATA = up_w ? ~data : data;
                dut.s_axil_WSTRB = up_w ? (strobe ^ 15u) : strobe;
                dut.s_axil_ARVALID = !write && !up_ar;
                dut.s_axil_ARADDR = up_ar ? (address ^ 0xA3u) : address;
                dut.s_axil_ARPROT = up_ar ? (prot ^ 7u) : prot;
                dut.s_axil_BREADY = write && response_wait >= 3u + profile;
                dut.s_axil_RREADY = !write && response_wait >= 3u + profile;
                const bool responding = request_cycle >= 0 && !child_response
                    && cycle >= static_cast<unsigned>(request_cycle) + 2u + profile;
                for (unsigned child = 0; child < kChildCount; ++child) {
                    const bool hit = static_cast<int>(child) == oracle.child;
                    // Even unselected endpoints are ready: stray VALID must not
                    // be hidden by an endpoint that happened to be stalled.
                    inputs[child] = {
                        cycle >= aw_ready_start, cycle >= w_ready_start,
                        hit && write && responding, response,
                        cycle >= 3u + profile, hit && !write && responding, response, read_data
                    };
                }
                drive_children(dut, inputs);
                dut.eval();
                sample_children(dut, outputs);

                // Sample every handshake before the rising edge, never from
                // post-edge READY after the holding/queue state has changed.
                if (dut.s_axil_AWVALID && dut.s_axil_AWREADY) {
                    up_aw = true;
                    ++upstream.aw;
                }
                if (dut.s_axil_WVALID && dut.s_axil_WREADY) {
                    up_w = true;
                    ++upstream.w;
                }
                if (dut.s_axil_ARVALID && dut.s_axil_ARREADY) {
                    up_ar = true;
                    ++upstream.ar;
                }
                for (unsigned child = 0; child < kChildCount; ++child) {
                    const ChildOutputs& out = outputs[child];
                    const ChildInputs& in = inputs[child];
                    const bool hit = static_cast<int>(child) == oracle.child;
                    if (!hit || !write) {
                        if (!context.matches("forbidden child AWVALID", out.awvalid, 0, child)
                            || !context.matches("forbidden child WVALID", out.wvalid, 0, child)
                            || !context.matches("forbidden child BREADY", out.bready, 0, child))
                            return false;
                    }
                    if (!hit || write) {
                        if (!context.matches("forbidden child ARVALID", out.arvalid, 0, child)
                            || !context.matches("forbidden child RREADY", out.rready, 0, child))
                            return false;
                    }
                    if (out.awvalid) {
                        if (!context.matches("duplicate child AW", child_aw, 0, child)
                            || !context.matches("child AWADDR", out.awaddr, oracle.local_address, child)
                            || !context.matches("child AWPROT", out.awprot, prot, child)) return false;
                    }
                    if (out.wvalid) {
                        if (!context.matches("duplicate child W", child_w, 0, child)
                            || !context.matches("child WDATA", out.wdata, data, child)
                            || !context.matches("child WSTRB", out.wstrb, strobe, child)) return false;
                    }
                    if (out.arvalid) {
                        if (!context.matches("duplicate child AR", child_ar, 0, child)
                            || !context.matches("child ARADDR", out.araddr, oracle.local_address, child)
                            || !context.matches("child ARPROT", out.arprot, prot, child)) return false;
                    }
                    if (out.bready && !context.matches("BREADY upstream gating",
                                                       dut.s_axil_BREADY, 1, child)) return false;
                    if (out.rready && !context.matches("RREADY upstream gating",
                                                       dut.s_axil_RREADY, 1, child)) return false;
                    if (out.awvalid && in.awready) {
                        child_aw = true;
                        ++endpoints[child].aw;
                    }
                    if (out.wvalid && in.wready) {
                        child_w = true;
                        ++endpoints[child].w;
                    }
                    if (out.arvalid && in.arready) {
                        child_ar = true;
                        ++endpoints[child].ar;
                    }
                    if (out.bready && in.bvalid) {
                        if (!context.matches("duplicate child B", child_response, 0, child)) return false;
                        child_response = true;
                        ++endpoints[child].b;
                    }
                    if (out.rready && in.rvalid) {
                        if (!context.matches("duplicate child R", child_response, 0, child)) return false;
                        child_response = true;
                        ++endpoints[child].r;
                    }
                }
                if (request_cycle < 0 && (write ? child_aw && child_w : child_ar)) {
                    request_cycle = static_cast<int>(cycle);
                }
                if (!context.matches("opposite upstream response",
                                     write ? dut.s_axil_RVALID : dut.s_axil_BVALID, 0)) return false;
                const bool valid = write ? dut.s_axil_BVALID : dut.s_axil_RVALID;
                const bool ready = write ? dut.s_axil_BREADY : dut.s_axil_RREADY;
                if (valid) {
                    if (!context.matches("upstream request accepted", write ? up_aw && up_w : up_ar, 1)
                        || !context.matches("upstream response", write ? dut.s_axil_BRESP : dut.s_axil_RRESP,
                                            oracle.error ? 3u : response)) return false;
                    if (!write && !context.matches("upstream RDATA", dut.s_axil_RDATA,
                                                    oracle.error ? 0u : read_data)) return false;
                    if (!oracle.error) {
                        if (!context.matches("child request completed", request_cycle >= 0, 1)
                            || !context.matches("child response present",
                                                write ? inputs[oracle.child].bvalid
                                                      : inputs[oracle.child].rvalid, 1)) return false;
                    }
                    ++response_wait;
                    if (ready) {
                        upstream_response = true;
                        if (write) ++upstream.b;
                        else ++upstream.r;
                    }
                } else if (response_wait != 0) {
                    // Once visible, VALID and its payload must survive all
                    // upstream backpressure until the acceptance edge.
                    if (!context.matches("held upstream VALID", valid, 1)) return false;
                }
                edge(dut);
                if (upstream_response) break;
            }
            if (!context.matches("transaction completed before timeout", upstream_response, 1)
                || !context.matches("upstream AW accounting", up_aw, write)
                || !context.matches("upstream W accounting", up_w, write)
                || !context.matches("upstream AR accounting", up_ar, !write)
                || !context.matches("child AW accounting", child_aw, write && !oracle.error)
                || !context.matches("child W accounting", child_w, write && !oracle.error)
                || !context.matches("child AR accounting", child_ar, !write && !oracle.error)
                || !context.matches("child response accounting", child_response, !oracle.error))
                return false;

            idle_upstream(dut);
            for (unsigned child = 0; child < kChildCount; ++child) {
                inputs[child] = {1, 1, 0, 0, 1, 0, 0, 0};
            }
            drive_children(dut, inputs);
            for (unsigned idle = 0; idle < 3; ++idle) {
                dut.eval();
                sample_children(dut, outputs);
                if (!context.matches("idle upstream BVALID", dut.s_axil_BVALID, 0)
                    || !context.matches("idle upstream RVALID", dut.s_axil_RVALID, 0)) return false;
                for (unsigned child = 0; child < kChildCount; ++child) {
                    const ChildOutputs& out = outputs[child];
                    if (!context.matches("idle child AWVALID", out.awvalid, 0, child)
                        || !context.matches("idle child WVALID", out.wvalid, 0, child)
                        || !context.matches("idle child ARVALID", out.arvalid, 0, child)
                        || !context.matches("idle child BREADY", out.bready, 0, child)
                        || !context.matches("idle child RREADY", out.rready, 0, child)) return false;
                }
                edge(dut);
            }
            return true;
        }

        int main(int argc, char** argv) {
            Verilated::commandArgs(argc, argv);
            V@MODULE@ dut;
            dut.clk = 0;
            dut.rst = 1;
            idle_upstream(dut);
            ChildInputs reset_inputs[kChildCount] = {};
            drive_children(dut, reset_inputs);
            dut.eval();
            edge(dut);
            edge(dut);
            dut.rst = 0;
            dut.eval();
            Counts endpoints[kChildCount] = {};
            Counts wanted[kChildCount] = {};
            Counts upstream;
            unsigned transactions = 0;
            for (unsigned address = 0; address < kAddressCount; ++address) {
                for (unsigned direction = 0; direction < 2; ++direction) {
                    for (unsigned profile = 0; profile < kProfiles; ++profile) {
                        if (!transaction(dut, address, direction, profile, endpoints, upstream)) return 1;
                        const Expected& oracle = expected[direction][address];
                        if (!oracle.error) {
                            Counts& count = wanted[oracle.child];
                            if (direction) { ++count.aw; ++count.w; ++count.b; }
                            else { ++count.ar; ++count.r; }
                        }
                        ++transactions;
                    }
                }
            }
            const Context context{0, 0, 0, 0};
            for (unsigned child = 0; child < kChildCount; ++child) {
                if (!context.matches("total endpoint AW", endpoints[child].aw, wanted[child].aw, child)
                    || !context.matches("total endpoint W", endpoints[child].w, wanted[child].w, child)
                    || !context.matches("total endpoint B", endpoints[child].b, wanted[child].b, child)
                    || !context.matches("total endpoint AR", endpoints[child].ar, wanted[child].ar, child)
                    || !context.matches("total endpoint R", endpoints[child].r, wanted[child].r, child)) return 1;
            }
            const unsigned per_direction = kAddressCount * kProfiles;
            if (!context.matches("total upstream AW", upstream.aw, per_direction)
                || !context.matches("total upstream W", upstream.w, per_direction)
                || !context.matches("total upstream B", upstream.b, per_direction)
                || !context.matches("total upstream AR", upstream.ar, per_direction)
                || !context.matches("total upstream R", upstream.r, per_direction)) return 1;
            dut.final();
            std::cout << "AXIL_ORACLE_SWEEP_OK " << transactions << std::endl;
            return 0;
        }
    """)
    return (
        template.replace("@MODULE@", module_name)
        .replace("@ADDRESS_COUNT@", str(model.address_space_size))
        .replace("@CHILD_COUNT@", str(len(model.targets)))
        .replace("@EXPECTED@", cpp_expected_table(model))
        .replace("@CHILD_INPUTS@", child_inputs)
        .replace("@CHILD_OUTPUTS@", child_outputs)
    )
