// Clocked APB transaction/side-effect scoreboard. No C++ assert(), since a
// release simulator build may compile it out. Counters live in the RTL wrapper.
#include "Vapb_buffer_wrapper.h"
#include "verilated.h"
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string>

struct Counts {
    uint32_t reads[2], writes[2], upstream_reads, upstream_writes;
};

class Bench {
public:
    Vapb_buffer_wrapper d;
    bool buffer_in, buffer_out, apb4, gated;
    unsigned failures = 0;
    unsigned cycle = 0;
    std::string label;

    Bench(const std::string& mode, bool is_apb4, bool gate)
        : buffer_in(mode == "in" || mode == "both"),
          buffer_out(mode == "out" || mode == "both"), apb4(is_apb4), gated(gate) {
        d.clk = 0;
        d.rst = 1;
        d.clear_counts = 1;
        d.PSEL = d.PENABLE = d.PWRITE = 0;
        d.PADDR = d.PWDATA = d.PPROT = d.PSTRB = 0;
        d.ready_in_setup = 0;
        d.inject_error = 0;
        for (unsigned i = 0; i < 2; ++i) {
            d.wait_cycles[i] = 0;
            d.data_seed[i] = 0xa5000000u + (i << 16);
        }
        tick();
        d.clear_counts = 0;
        d.rst = 0;
        tick();
    }

    void check(bool condition, const std::string& what) {
        if (!condition) {
            ++failures;
            std::cerr << "FAIL cycle=" << cycle << " " << label << ": " << what << '\n';
        }
    }

    Counts counts() const {
        return {{d.child_reads[0], d.child_reads[1]},
                {d.child_writes[0], d.child_writes[1]}, d.upstream_reads, d.upstream_writes};
    }

    static uint32_t child_total(const Counts& c) {
        return c.reads[0] + c.reads[1] + c.writes[0] + c.writes[1];
    }
    static uint32_t upstream_total(const Counts& c) { return c.upstream_reads + c.upstream_writes; }

    void eval() {
        d.eval();
        check(d.child_clock == (d.clk ? 3 : 0), "child clock/domain connection changed");
        check(d.child_resetn == (d.rst ? 0 : 3), "child reset/domain connection changed");
        if (!d.rst && gated) {
            for (unsigned i = 0; i < 2; ++i) {
                if (!(d.child_psel & (1u << i))) {
                    check(d.child_addr[i] == 0 && d.child_wdata[i] == 0,
                          "unselected address/write data must be gated to zero");
                    check(!apb4 || (d.child_prot[i] == 0 && d.child_strb[i] == 0),
                          "unselected APB4 protection/strobes must be gated to zero");
                }
            }
        }
    }

    void tick() {
        d.clk = 0;
        eval();
        d.clk = 1;
        eval();
        ++cycle;
        d.clk = 0;
        eval();
    }

    void unchanged(const Counts& before, const std::string& what) {
        const auto after = counts();
        check(child_total(after) == child_total(before), what + " caused child completion");
        check(upstream_total(after) == upstream_total(before), what + " caused upstream completion");
    }

    void idle(unsigned clocks = 3) {
        d.PSEL = d.PENABLE = 0;
        const auto before = counts();
        for (unsigned i = 0; i < clocks; ++i) tick();
        unchanged(before, "idle/retirement");
    }

    void setup(unsigned target, bool write, unsigned address, unsigned waits, bool setup_ready = false) {
        d.PSEL = 1;
        d.PENABLE = 0;
        d.PWRITE = write;
        d.PADDR = target * 0x1000 + address;
        d.PWDATA = 0x12340000u + (target << 8) + address;
        d.PPROT = (address >> 2) & 7;
        d.PSTRB = ((address >> 2) & 15) | 1;
        d.wait_cycles[0] = d.wait_cycles[1] = waits;
        d.ready_in_setup = setup_ready;
        d.inject_error = target ? 2 : 1;
        d.data_seed[0] = 0xa5000000u;
        d.data_seed[1] = 0xb6000000u;
        eval();
    }

    void request_bus(unsigned target, bool write, unsigned address) {
        const unsigned mask = 1u << target;
        check((d.child_psel & ~mask) == 0, "wrong child selected");
        if (d.child_psel & mask) {
            check(bool(d.child_pwrite & mask) == write, "write direction changed");
            check(d.child_addr[target] == address, "child local address changed");
            check(d.child_wdata[target] == d.PWDATA, "write payload changed");
            check(!apb4 || (d.child_prot[target] == d.PPROT && d.child_strb[target] == d.PSTRB),
                  "APB4 request protection/strobes changed");
        }
    }

    void transfer(unsigned target, bool write, unsigned address, unsigned waits = 0,
                  unsigned extra_setup = 0, bool setup_ready = false) {
        label = std::string(write ? "write" : "read") + " target=" + std::to_string(target)
                + " waits=" + std::to_string(waits);
        const auto before = counts();
        setup(target, write, address, waits, setup_ready);
        // Mapped PREADY may legally be high in SETUP. The default unbuffered
        // route must still pass this through instead of forcing phase gating.
        if (setup_ready && !buffer_in && !buffer_out)
            check(d.PREADY, "unbuffered mapped setup PREADY no longer passes through");
        for (unsigned i = 0; i <= extra_setup; ++i) {
            request_bus(target, write, address);
            tick();
            unchanged(before, "SETUP");
        }
        const uint32_t expected_data = d.data_seed[target] + (before.reads[target] << 8) + address;
        const bool expected_error = bool((d.inject_error >> target) & 1) ^ bool(before.reads[target] & 1);
        d.PENABLE = 1;
        unsigned accesses = 0;
        bool accepted = false;
        bool response_mutated = false;
        for (; accesses < 40; ++accesses) {
            eval();
            request_bus(target, write, address);
            const bool ready = d.PREADY;
            if (ready) {
                if (!write) check(d.PRDATA == expected_data,
                                  "read response not retained: got=" + std::to_string(d.PRDATA)
                                  + " expected=" + std::to_string(expected_data));
                check(bool(d.PSLVERR) == expected_error, "response error not retained");
            }
            tick();
            if (ready) {
                accepted = true;
                ++accesses;
                break;
            }
            // Registered responses must survive a child changing both PRDATA
            // and PSLVERR immediately after its side-effecting completion edge.
            if (buffer_out && !response_mutated && child_total(counts()) > child_total(before)) {
                d.data_seed[target] ^= 0x00ff0000u;
                d.inject_error ^= 1u << target;
                eval();
                check(d.PREADY, "completed child response was not made available");
                if (!write) check(d.PRDATA == expected_data, "child data change leaked through output buffer");
                check(bool(d.PSLVERR) == expected_error, "child error change leaked through output buffer");
                check(d.child_psel == 0 && d.child_penable == 0,
                      "completed child remains selected while response awaits upstream");
                response_mutated = true;
            }
        }
        check(accepted, "upstream transfer timed out");
        check(accesses == 1u + buffer_in + buffer_out + waits,
              "ACCESS latency got=" + std::to_string(accesses) + " expected="
              + std::to_string(1u + buffer_in + buffer_out + waits));
        const auto after = counts();
        const uint32_t read_delta = after.reads[target] - before.reads[target];
        const uint32_t write_delta = after.writes[target] - before.writes[target];
        const uint32_t upstream_read_delta = after.upstream_reads - before.upstream_reads;
        const uint32_t upstream_write_delta = after.upstream_writes - before.upstream_writes;
        check(read_delta == unsigned(!write) && write_delta == unsigned(write),
              "side effects child_reads=" + std::to_string(read_delta)
              + " child_writes=" + std::to_string(write_delta)
              + " upstream_reads=" + std::to_string(upstream_read_delta)
              + " upstream_writes=" + std::to_string(upstream_write_delta));
        check(upstream_read_delta == unsigned(!write) && upstream_write_delta == unsigned(write),
              "upstream completion counter mismatch");
        check(child_total(after) - child_total(before) == 1, "extra/wrong child completed");
        check(!d.phase_error, "child ACCESS lacked SETUP or followed a completed ACCESS without SETUP");
        check(!d.hold_error, "child request changed during wait state");
    }

    void unmapped(bool write) {
        label = write ? "unmapped write" : "unmapped read";
        const auto before = counts();
        d.PSEL = 1;
        d.PENABLE = 0;
        d.PWRITE = write;
        d.PADDR = 0x800;
        eval();
        check(!d.PREADY && !d.PSLVERR, "local error must not complete in SETUP");
        tick();
        d.PENABLE = 1;
        bool accepted = false;
        unsigned accesses = 0;
        for (; accesses < 20; ++accesses) {
            eval();
            const bool ready = d.PREADY;
            check(d.child_psel == 0 && d.child_penable == 0, "unmapped transfer selected child");
            if (ready) check(d.PSLVERR && d.PRDATA == 0, "unmapped response must be error/zero data");
            tick();
            if (ready) { accepted = true; ++accesses; break; }
        }
        check(accepted, "unmapped request timed out");
        check(accesses == 1u + buffer_in + buffer_out, "unmapped pipeline latency mismatch");
        check(child_total(counts()) == child_total(before), "unmapped request caused child side effect");
        check(upstream_total(counts()) == upstream_total(before) + 1, "unmapped upstream count mismatch");
        idle();
    }

    void abort_with_reset(bool after_child_completion) {
        label = after_child_completion ? "reset pending response" : "reset stalled request";
        const auto before = counts();
        setup(0, !after_child_completion, 0x38, after_child_completion ? 0 : 7);
        tick();
        d.PENABLE = 1;
        for (unsigned i = 0; i < 10; ++i) {
            eval();
            if (after_child_completion) {
                if (child_total(counts()) > child_total(before)) break;
            } else if (d.child_psel && d.child_penable) {
                tick(); // At least one actual downstream wait edge before reset.
                break;
            }
            tick();
        }
        const auto at_reset = counts();
        check(upstream_total(at_reset) == upstream_total(before), "aborted request already acknowledged upstream");
        check(child_total(at_reset) == child_total(before) + unsigned(after_child_completion),
              "unexpected side effects before reset");
        d.rst = 1;
        eval();
        if (buffer_in || buffer_out) {
            check(d.child_psel == 0 && d.child_penable == 0, "async reset did not suppress child request");
            check(!d.PREADY, "async reset did not discard response readiness");
        }
        tick();
        d.rst = 0;
        if (buffer_in || buffer_out) {
            // An old ACCESS held across reset is not a new request; only a new
            // upstream SETUP may rearm a buffered transaction.
            tick();
            tick();
            check(d.child_psel == 0 && !d.PREADY, "stale ACCESS replayed after reset");
            unchanged(at_reset, "aborted epoch after reset");
        }
        d.PSEL = d.PENABLE = 0;
        tick();
        unchanged(at_reset, "reset retirement");
        // Deliberately use a local delta here, not lifetime child==upstream:
        // a reset can discard a response but cannot undo its child's side effect.
        transfer(1, false, 0x2c);
        idle();
    }
};

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    if (argc != 4) return 2;
    Bench b(argv[1], std::atoi(argv[2]) != 0, std::atoi(argv[3]) != 0);
    // Keep these first two independent cases as the exact original regression:
    // legal no-wait child PREADY=PENABLE, clocked write/read side effects.
    b.transfer(0, true, 0x24);
    b.idle();
    b.transfer(0, false, 0x28);
    b.idle();
    // Back-to-back upstream transfers keep PSEL high, including target/direction
    // switches. Each transfer still presents the mandatory downstream SETUP.
    for (unsigned i = 0; i < 12; ++i)
        b.transfer(i & 1, bool(i & 2), 0x10 + 4 * (i % 8), i % 4);
    b.idle(4);
    b.transfer(1, false, 0x34, 2, 2); // Extended upstream SETUP cannot cause early completion.
    b.idle();
    b.transfer(0, false, 0x3c, 0, 0, true); // Child legally asserts ready during SETUP.
    b.idle();
    b.unmapped(false);
    b.unmapped(true);
    b.abort_with_reset(false);
    if (b.buffer_out) b.abort_with_reset(true);
    if (b.failures) {
        std::cerr << "APB_BUFFER_FAILURES=" << b.failures
                  << " child_reads=" << b.d.child_reads[0] + b.d.child_reads[1]
                  << " child_writes=" << b.d.child_writes[0] + b.d.child_writes[1]
                  << " upstream_reads=" << b.d.upstream_reads
                  << " upstream_writes=" << b.d.upstream_writes << '\n';
        return 1;
    }
    std::cout << "APB_BUFFER_SUCCESS mode=" << argv[1] << " cycles=" << b.cycle << '\n';
    return 0;
}
