// Independent finite-cycle AHB-Lite oracle for spec/ahb-lite.md.
// Only public wrapper pins are observed; no generated hierarchy is inspected.
#include "Vahb_scoreboard_wrapper.h"
#include "verilated.h"

#include <array>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

#ifndef TEST_DATA_WIDTH
#error TEST_DATA_WIDTH must be supplied by the pytest harness
#endif
#ifndef TEST_DENSE_ARRAY
#define TEST_DENSE_ARRAY 0
#endif
#ifndef TEST_REGISTER_OVERLAP
#define TEST_REGISTER_OVERLAP 0
#endif

namespace {
using Data = std::uint64_t;
constexpr Data kMask = UINT64_MAX >> (64 - TEST_DATA_WIDTH);
constexpr unsigned kBytes = TEST_DATA_WIDTH / 8;
constexpr unsigned kBusSize = TEST_DATA_WIDTH == 64 ? 3 : 2;
constexpr std::array<unsigned, 4> kBases = TEST_DENSE_ARRAY
    ? std::array<unsigned, 4>{0x0000, 0x0400, 0x0800, 0x0c00}
    : TEST_REGISTER_OVERLAP
        ? std::array<unsigned, 4>{0x0000, 0x0000, 0x1000, 0x1800}
        : std::array<unsigned, 4>{0x0000, 0x0800, 0x1000, 0x1800};

// This literal address map comes from the fixture contract, not exporter nodes,
// generated selectors, package constants, or the DUT's own address fanout.
int destination(unsigned address, bool write) {
    for (unsigned target = 0; target < kBases.size(); ++target) {
        // The overlap profile has a read-only scalar/array and one write-only
        // scalar. Permission is applied before resolving an address alias.
        if (TEST_REGISTER_OVERLAP && ((write && target != 1) || (!write && target == 1)))
            continue;
        if (address >= kBases[target] && address < kBases[target] + 0x400)
            return static_cast<int>(target);
    }
    return -1;
}

Data pattern(unsigned number) {
    return (UINT64_C(0xd16b3a478205c9ef)
            ^ (UINT64_C(0x0103070b11171d25) * (number + 1))) & kMask;
}

struct Address {
    unsigned address = 0;
    bool selected = true;
    unsigned trans = 2;
    bool write = false;
    unsigned size = kBusSize;
    unsigned burst = 0;
    unsigned prot = 0xb;
    bool lock = false;

    bool active() const { return selected && ((trans & 2) != 0); }
};

Address transfer(unsigned address, bool write = false, unsigned size = kBusSize) {
    Address result;
    result.address = address;
    result.write = write;
    result.size = size;
    result.prot = (address >> 2) & 0xf;
    return result;
}

Address bubble(unsigned address = TEST_DENSE_ARRAY ? 0x0400 : 0x1400, unsigned trans = 0) {
    Address result = transfer(address);
    result.trans = trans;
    return result;
}

struct Response {
    Data data = 0;
    bool ready = true;
    bool error = false;
};

enum class ChildMode { Okay, Wait, ErrorFirst, ErrorSecond };

struct Pending {
    bool valid = false;
    int target = -1;
    bool second_error_cycle = false;
    bool write = false;
};

struct Coverage {
    std::array<unsigned, 4> reads{};
    std::array<unsigned, 4> writes{};
    std::array<unsigned, 4> sizes{};
    unsigned responses = 0;
    unsigned local_first = 0;
    unsigned local_second = 0;
    unsigned child_first = 0;
    unsigned child_second = 0;
    unsigned wait_cycles = 0;
    unsigned external_hold = 0;
    unsigned bubbles = 0;
    unsigned seq = 0;
    unsigned burst = 0;
    unsigned lock = 0;
    unsigned resets = 0;
};

class Bench {
public:
    void scenario(const char* name) { scenario_ = name; }

    bool cycle(const Address& address, Data data, ChildMode mode = ChildMode::Okay,
               bool external_hold = false) {
        last_address_ = address;
        last_data_ = data & kMask;
        for (unsigned target = 0; target < child_.size(); ++target) {
            // Every child has a different, nonzero full-width response. Live
            // address selection therefore cannot masquerade as retained routing.
            child_[target] = {
                pattern(static_cast<unsigned>(cycle_) * 7 + target * 113), true, false
            };
        }
        if (pending_.valid && pending_.target >= 0) {
            auto& selected = child_[static_cast<unsigned>(pending_.target)];
            selected.ready = mode != ChildMode::Wait && mode != ChildMode::ErrorFirst;
            selected.error = mode == ChildMode::ErrorFirst || mode == ChildMode::ErrorSecond;
            if (mode == ChildMode::ErrorFirst) ++coverage_.child_first;
            if (mode == ChildMode::ErrorSecond) ++coverage_.child_second;
        }
        const Response expected = response();
        // Drive legal global timing from the independent oracle, not from the
        // DUT output: an erroneously early completion cannot advance the test.
        const bool global_ready = expected.ready && !external_hold;
        drive(address, last_data_, global_ready);
        dut_.HRESETn = 1;
        dut_.HCLK = 0;
        dut_.eval();
        check(address, last_data_, global_ready, false);

        if (pending_.valid) {
            if (pending_.target < 0) {
                if (pending_.second_error_cycle) ++coverage_.local_second;
                else ++coverage_.local_first;
            }
            if (!global_ready) ++coverage_.wait_cycles;
            if (global_ready) ++coverage_.responses;
        }
        if (external_hold) ++coverage_.external_hold;
        const bool accepted = global_ready && address.active();

        // A local error's first phase advances even during its forced wait;
        // destination replacement, including clearing on a bubble, never does.
        if (pending_.valid && pending_.target < 0 && !pending_.second_error_cycle)
            pending_.second_error_cycle = true;
        if (global_ready) {
            pending_ = {};
            if (address.active()) {
                pending_.valid = true;
                pending_.target = destination(address.address, address.write);
                pending_.write = address.write;
                if (pending_.target >= 0) {
                    const unsigned target = static_cast<unsigned>(pending_.target);
                    if (address.write) ++coverage_.writes[target];
                    else ++coverage_.reads[target];
                    ++coverage_.sizes[address.size];
                    if (address.trans == 3) ++coverage_.seq;
                    if (address.burst != 0) ++coverage_.burst;
                    if (address.lock) ++coverage_.lock;
                }
            } else {
                ++coverage_.bubbles;
            }
        }
        dut_.HCLK = 1;
        dut_.eval();
        dut_.HCLK = 0;
        dut_.eval();
        ++cycle_;
        return accepted;
    }

    void reset(bool hold_global_ready_low = true) {
        // No clock edge is allowed between asserting reset and inspecting the
        // idle response. Also keep HREADY low throughout reset and release.
        const bool global_ready = !hold_global_ready_low && response().ready;
        drive(last_address_, last_data_, global_ready);
        dut_.HCLK = 0;
        dut_.HRESETn = 1;
        dut_.eval();
        if (coverage_.resets != 0)
            check(last_address_, last_data_, global_ready, false);
        dut_.HRESETn = 0;
        dut_.eval();
        pending_ = {};
        check(last_address_, last_data_, global_ready, true);
        dut_.HCLK = 1;
        dut_.eval();
        check(last_address_, last_data_, global_ready, true);
        dut_.HCLK = 0;
        dut_.eval();
        dut_.HRESETn = 1;
        dut_.eval();
        check(last_address_, last_data_, global_ready, false);
        ++coverage_.resets;
    }

    void flush() {
        for (unsigned attempt = 0; attempt < 4 && pending_.valid; ++attempt)
            cycle(bubble(), pattern(900 + attempt));
        require(!pending_.valid, "pending transfer did not flush");
    }

    void offer(const Address& address, Data data) {
        // Only locally generated errors can delay this zero-wait sweep. Keep
        // its next address/control and write data stable until acceptance.
        for (unsigned attempt = 0; attempt < 4; ++attempt) {
            if (cycle(address, data)) return;
        }
        require(false, "address never accepted after bounded local ERROR");
    }

    void finish(bool focused_profile = false) {
        flush();
        cycle(bubble(TEST_DENSE_ARRAY ? 0x0ff8 : 0xfff8), pattern(999));
        for (unsigned target = 0; target < 4; ++target) {
            const bool readable = !TEST_REGISTER_OVERLAP || target != 1;
            const bool writable = !TEST_REGISTER_OVERLAP || target == 1;
            require(readable ? coverage_.reads[target] > 0 : coverage_.reads[target] == 0,
                    "read coverage violates target permissions");
            require(writable ? coverage_.writes[target] > 0 : coverage_.writes[target] == 0,
                    "write coverage violates target permissions");
        }
        for (unsigned size = 0; size <= kBusSize; ++size)
            require(coverage_.sizes[size] > 0, "legal HSIZE missing coverage");
        if (!focused_profile) {
            require(coverage_.local_first > 0 && coverage_.local_second > 0,
                    "both local ERROR phases must be observed");
            require(coverage_.child_first >= 4 && coverage_.child_second >= 4,
                    "child ERROR phases missing");
            require(coverage_.seq > 0 && coverage_.burst > 0 && coverage_.lock > 0,
                    "SEQ, HBURST and HMASTLOCK coverage missing");
            require(coverage_.wait_cycles > 4 && coverage_.bubbles > 4
                    && coverage_.external_hold > 0 && coverage_.resets >= 5,
                    "stall, bubble, external hold or reset coverage missing");
        }
        if (TEST_REGISTER_OVERLAP)
            require(coverage_.local_first > 0 && coverage_.local_second > 0
                    && coverage_.child_first > 0 && coverage_.child_second > 0,
                    "permission-denied/error recovery coverage missing");
        std::cout << "AHB-Lite independent cycle scoreboard PASS"
                  << " width=" << TEST_DATA_WIDTH << " cycles=" << cycle_
                  << " responses=" << coverage_.responses
                  << " local_error=" << coverage_.local_first << "/" << coverage_.local_second
                  << " child_error=" << coverage_.child_first << "/" << coverage_.child_second
                  << " waits=" << coverage_.wait_cycles
                  << " resets=" << coverage_.resets << '\n';
        dut_.final();
    }

private:
    Vahb_scoreboard_wrapper dut_;
    Pending pending_;
    std::array<Response, 4> child_{};
    Address last_address_ = bubble();
    Data last_data_ = 0;
    std::uint64_t cycle_ = 0;
    const char* scenario_ = "initial asynchronous reset";
    Coverage coverage_;

    Response response() const {
        if (!pending_.valid) return {};
        if (pending_.target < 0) return {0, pending_.second_error_cycle, true};
        return child_[static_cast<unsigned>(pending_.target)];
    }

    void drive(const Address& address, Data data, bool global_ready) {
        dut_.HSEL = address.selected;
        dut_.HREADY = global_ready;
        dut_.HADDR = address.address;
        dut_.HTRANS = address.trans;
        dut_.HWRITE = address.write;
        dut_.HSIZE = address.size;
        dut_.HBURST = address.burst;
        dut_.HPROT = address.prot;
        dut_.HMASTLOCK = address.lock;
        dut_.HWDATA = data;
        for (unsigned target = 0; target < 4; ++target) {
            dut_.child_HRDATA[target] = child_[target].data;
            dut_.child_HREADYOUT[target] = child_[target].ready;
            dut_.child_HRESP[target] = child_[target].error;
        }
    }

    void equal(const char* signal, std::uint64_t actual, std::uint64_t expected,
               int target = -1) const {
        if (actual == expected) return;
        std::ostringstream message;
        message << scenario_ << ", cycle " << cycle_ << ": ";
        if (target >= 0) message << "child[" << target << "].";
        message << signal << " actual=0x" << std::hex << actual << " expected=0x" << expected
                << " pending=" << std::dec << pending_.valid << "/" << pending_.target
                << " next-address=0x" << std::hex << last_address_.address;
        throw std::runtime_error(message.str());
    }

    void require(bool condition, const char* message) const {
        if (!condition) throw std::runtime_error(std::string(scenario_) + ": " + message);
    }

    void check(const Address& address, Data data, bool global_ready, bool reset_asserted) const {
        const Response expected = reset_asserted ? Response{} : response();
        equal("HREADYOUT", dut_.HREADYOUT, expected.ready);
        equal("HRESP", dut_.HRESP, expected.error);
        equal("HRDATA", dut_.HRDATA, expected.data);
        const int selected = address.active() && !reset_asserted
            ? destination(address.address, address.write) : -1;
        for (unsigned target = 0; target < 4; ++target) {
            equal("HSEL", dut_.child_HSEL[target], selected == static_cast<int>(target), target);
            // In particular, HREADY must not be replaced by local READYOUT,
            // gated by this child's HSEL, or ORed with any other child response.
            equal("HREADY", dut_.child_HREADY[target], global_ready, target);
            if (reset_asserted) continue;
            equal("HWDATA", dut_.child_HWDATA[target], data, target);
            if (selected == static_cast<int>(target)) {
                equal("HADDR", dut_.child_HADDR[target], address.address - kBases[target], target);
                equal("HTRANS", dut_.child_HTRANS[target], address.trans, target);
                equal("HWRITE", dut_.child_HWRITE[target], address.write, target);
                equal("HSIZE", dut_.child_HSIZE[target], address.size, target);
                equal("HBURST", dut_.child_HBURST[target], address.burst, target);
                equal("HPROT", dut_.child_HPROT[target], address.prot, target);
                equal("HMASTLOCK", dut_.child_HMASTLOCK[target], address.lock, target);
            }
        }
        if (!reset_asserted && pending_.valid && pending_.target >= 0 && pending_.write) {
            // The address phase deliberately carries unrelated data. The
            // preceding write's live data must survive retargeting and stalls.
            equal("pending-write HWDATA", dut_.child_HWDATA[pending_.target], data);
        }
    }
};

void exercise(Bench& bench) {
    bench.reset();

    bench.scenario("alternating accepted address / preceding data destinations");
    bench.cycle(transfer(0x0010), pattern(0));
    bench.cycle(transfer(0x0820, true), pattern(1));
    bench.cycle(transfer(0x1048), pattern(2));
    bench.cycle(transfer(0x18a0, true), pattern(3));
    bench.cycle(transfer(0x0030, true), pattern(4));
    bench.cycle(transfer(0x0838), pattern(5));
    bench.flush();

    bench.scenario("byte, halfword and full-width lanes with nonzero offsets");
    for (unsigned size = 0; size <= kBusSize; ++size) {
        const unsigned offset = (0x27 + size * 0x29) & ~((1u << size) - 1);
        for (unsigned target = 0; target < 4; ++target) {
            bench.cycle(transfer(kBases[target] + offset, (target & 1) != 0, size),
                        pattern(20 + size * 4 + target));
        }
    }
    bench.flush();

    bench.scenario("NONSEQ/SEQ INCR burst with BUSY bubble and lock");
    Address burst = transfer(0x0200);
    burst.burst = 1;  // INCR, permitted to terminate after any number of beats.
    burst.prot = 0xd;
    burst.lock = true;
    bench.cycle(burst, pattern(40));
    burst.address += kBytes;
    burst.trans = 3;
    bench.cycle(burst, pattern(41));
    Address busy = burst;
    busy.trans = 1;
    bench.cycle(busy, pattern(42));
    burst.address += kBytes;
    bench.cycle(burst, pattern(43));
    bench.flush();

    bench.scenario("all fixed-length burst encodings stay inside their aperture");
    for (unsigned encoding = 2; encoding < 8; ++encoding) {
        const unsigned beats = 4u << ((encoding - 2) / 2);
        const bool wrapping = (encoding & 1) == 0;
        for (unsigned beat = 0; beat < beats; ++beat) {
            const unsigned index = wrapping ? ((2 + beat) % beats) : beat;
            Address item = transfer(0x1200 + index * kBytes, !wrapping);
            item.trans = beat == 0 ? 2 : 3;
            item.burst = encoding;
            item.prot = 0x9;
            item.lock = true;
            bench.cycle(item, pattern(4000 + encoding * 32 + beat));
        }
    }
    bench.flush();

    bench.scenario("retarget during a multi-cycle write data stall");
    bench.cycle(transfer(0x0038, true), pattern(50));
    const Address next = transfer(0x1850);
    const Data stalled_data = pattern(51);
    bench.cycle(next, stalled_data, ChildMode::Wait);
    bench.cycle(next, stalled_data, ChildMode::Wait);
    bench.cycle(next, stalled_data, ChildMode::Wait);
    bench.cycle(next, stalled_data);
    bench.cycle(transfer(0x0860, true), pattern(52));
    bench.flush();

    bench.scenario("external HREADY hold is not local response readiness");
    bench.cycle(transfer(0x1020), pattern(60));
    const Address held_next = transfer(0x0828, true);
    bench.cycle(held_next, pattern(61), ChildMode::Okay, true);
    bench.cycle(held_next, pattern(61), ChildMode::Okay, true);
    bench.cycle(held_next, pattern(61));
    bench.flush();

    bench.scenario("IDLE/BUSY/unselected unmapped traffic and stalled bubbles");
    bench.cycle(transfer(0x0830), pattern(70));
    const Address idle_hole = bubble(0x1400);
    bench.cycle(idle_hole, pattern(71), ChildMode::Wait);
    bench.cycle(idle_hole, pattern(71), ChildMode::Wait);
    bench.cycle(idle_hole, pattern(71));
    bench.cycle(bubble(0x1c00, 1), pattern(72));
    Address unselected = transfer(0x4000, true);
    unselected.selected = false;
    bench.cycle(unselected, pattern(73));
    bench.cycle(bubble(0x4000), pattern(74));

    bench.scenario("local two-cycle ERROR with following-address cancellation");
    for (unsigned miss : {0x0400u, 0x0c00u, 0x1400u, 0x1c00u, 0x4000u, 0xfff8u}) {
        bench.cycle(transfer(miss, (miss & 0x800) != 0), pattern(miss));
        bench.cycle(transfer(0x1800), pattern(miss + 1));  // first ERROR, must wait
        bench.cycle(bubble(0x1800), pattern(miss + 1));   // second ERROR, cancel
        bench.cycle(transfer(0x0800, true), pattern(miss + 2));
        bench.flush();
    }

    bench.scenario("local ERROR second-cycle acceptance and immediate recovery");
    bench.cycle(transfer(0x1400, true), pattern(80));
    bench.cycle(transfer(0x1028), pattern(81));
    bench.cycle(transfer(0x1028), pattern(81));
    bench.cycle(transfer(0x1830, true), pattern(82));
    bench.flush();

    bench.scenario("child two-cycle ERROR is retained across retarget and cancel");
    for (unsigned target = 0; target < 4; ++target) {
        bench.cycle(transfer(kBases[target] + 0x40, (target & 1) != 0), pattern(90 + target));
        const Address following = transfer(kBases[(target + 1) % 4] + 0x48);
        const Data error_data = pattern(100 + target);
        bench.cycle(following, error_data, ChildMode::ErrorFirst);
        bench.cycle(bubble(following.address), error_data, ChildMode::ErrorSecond);
        bench.cycle(following, pattern(110 + target));
        bench.flush();
    }

    bench.scenario("child ERROR second-cycle recovery without cancellation");
    bench.cycle(transfer(0x1848), pattern(120));
    bench.cycle(transfer(0x0050, true), pattern(121), ChildMode::ErrorFirst);
    bench.cycle(transfer(0x0050, true), pattern(121), ChildMode::ErrorSecond);
    bench.cycle(transfer(0x0858), pattern(122));
    bench.flush();

    bench.scenario("asynchronous reset during child stall while HREADY held low");
    bench.cycle(transfer(0x0040, true), pattern(130));
    bench.cycle(transfer(0x0848), pattern(131), ChildMode::Wait);
    bench.reset();
    bench.cycle(bubble(), pattern(132));
    bench.cycle(transfer(0x1048), pattern(133));
    bench.flush();

    bench.scenario("asynchronous reset during first local ERROR response");
    bench.cycle(transfer(0x1400), pattern(140));
    bench.reset();
    bench.cycle(bubble(), pattern(141));

    bench.scenario("asynchronous reset during second local ERROR response");
    bench.cycle(transfer(0x1c00, true), pattern(150));
    bench.cycle(transfer(0x1800), pattern(151));
    bench.reset();
    bench.cycle(bubble(), pattern(152));

    bench.scenario("asynchronous reset during a child ERROR response");
    bench.cycle(transfer(0x0838, true), pattern(160));
    bench.cycle(transfer(0x0030), pattern(161), ChildMode::ErrorFirst);
    bench.reset();
    bench.cycle(transfer(0x1830), pattern(162));
    bench.flush();

    bench.scenario("asynchronous reset while second child ERROR is externally held");
    bench.cycle(transfer(0x1038), pattern(170));
    bench.cycle(transfer(0x0830), pattern(171), ChildMode::ErrorFirst);
    bench.cycle(transfer(0x0830), pattern(171), ChildMode::ErrorSecond, true);
    bench.reset();
    bench.cycle(bubble(), pattern(172));

    bench.scenario("exhaustive full-width word addresses including stride holes");
    for (unsigned address = 0; address < 0x2000; address += kBytes) {
        bench.offer(transfer(address, ((address / kBytes) & 1) != 0), pattern(200 + address));
    }
    bench.finish();
}

void exercise_dense_minimum_width(Bench& bench) {
    bench.scenario("four dense targets exactly fill 12-bit ingress");
    bench.reset();
    // In particular 0xffc must hit the last element, not wrap its upper decode
    // bound to zero. Each next address names a different target from the data.
    for (unsigned target = 0; target < 4; ++target)
        bench.cycle(transfer(kBases[target] + 0x3fc, (target & 1) != 0), pattern(target));
    bench.cycle(transfer(0x0000, true), pattern(5));
    bench.flush();
    for (unsigned size = 0; size <= kBusSize; ++size) {
        const unsigned offset = (0x31 + size * 0x19) & ~((1u << size) - 1);
        for (unsigned target = 0; target < 4; ++target)
            bench.cycle(transfer(kBases[target] + offset, (target & 1) != 0, size),
                        pattern(20 + target * 4 + size));
    }
    bench.flush();
    bench.cycle(transfer(0x0ffc, true), pattern(40));
    bench.cycle(transfer(0x0008), pattern(41), ChildMode::Wait);
    bench.cycle(transfer(0x0008), pattern(41), ChildMode::Wait);
    bench.cycle(transfer(0x0008), pattern(41));
    bench.flush();
    for (unsigned address = 0; address < 0x1000; address += kBytes)
        bench.offer(transfer(address, ((address / kBytes) & 1) != 0), pattern(100 + address));
    bench.finish(true);
}

void exercise_register_overlap(Bench& bench) {
    bench.scenario("RO/WO scalar alias followed by read-only array targets");
    bench.reset();
    for (unsigned repeat = 0; repeat < 8; ++repeat) {
        bench.cycle(transfer(0x0010), pattern(repeat * 4));
        bench.cycle(transfer(0x0010, true), pattern(repeat * 4 + 1));
        bench.cycle(transfer(0x1020), pattern(repeat * 4 + 2));
        bench.cycle(transfer(0x1830), pattern(repeat * 4 + 3));
    }
    bench.flush();
    for (unsigned size = 0; size <= kBusSize; ++size) {
        const unsigned offset = (0x27 + size * 0x29) & ~((1u << size) - 1);
        bench.cycle(transfer(offset, false, size), pattern(40 + size * 2));
        bench.cycle(transfer(offset, true, size), pattern(41 + size * 2));
    }
    bench.flush();

    bench.scenario("retained destination when following HWRITE chooses an address alias");
    bench.cycle(transfer(0x0040), pattern(50));
    bench.cycle(transfer(0x0040, true), pattern(51), ChildMode::Wait);
    bench.cycle(transfer(0x0040, true), pattern(51), ChildMode::Wait);
    bench.cycle(transfer(0x0040, true), pattern(51));
    bench.cycle(transfer(0x0048), pattern(52), ChildMode::Wait);
    bench.cycle(transfer(0x0048), pattern(52), ChildMode::Wait);
    bench.cycle(transfer(0x0048), pattern(52));
    bench.flush();

    bench.scenario("read-only array write denial has no HSEL and recovers to the alias");
    bench.offer(transfer(0x1028, true), pattern(60));
    bench.offer(transfer(0x1830, true), pattern(61));
    bench.offer(transfer(0x0038, true), pattern(62));
    bench.cycle(transfer(0x0038), pattern(63));
    bench.flush();

    bench.scenario("child ERROR recovery accepts the opposite-direction alias");
    bench.cycle(transfer(0x1030), pattern(70));
    bench.cycle(transfer(0x0030, true), pattern(71), ChildMode::ErrorFirst);
    bench.cycle(transfer(0x0030, true), pattern(71), ChildMode::ErrorSecond);
    bench.cycle(transfer(0x0030), pattern(72));
    bench.flush();
    bench.scenario("permission-aware exhaustive word sweep including denied writes");
    for (unsigned address = 0; address < 0x2000; address += kBytes)
        bench.offer(transfer(address, ((address / kBytes) & 1) != 0), pattern(100 + address));
    bench.finish(true);
}
}  // namespace

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    try {
        Bench bench;
        if (TEST_REGISTER_OVERLAP) exercise_register_overlap(bench);
        else if (TEST_DENSE_ARRAY) exercise_dense_minimum_width(bench);
        else exercise(bench);
        return EXIT_SUCCESS;
    } catch (const std::exception& error) {
        std::cerr << "AHB-Lite scoreboard FAILURE: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
