// Finite APB checks against a literal maximum-size map, independent of exporter
// metadata. Explicit conditions remain active in release/NDEBUG simulator builds.
#include "Vrdl_params_wrapper.h"
#include "verilated.h"
#include <cstdint>
#include <cstdlib>
#include <iostream>

namespace {
constexpr unsigned kChildren = 9;
constexpr unsigned kWords = 3;
constexpr unsigned kBases[kChildren] = {
    0x000, 0x020, 0x040, 0x060, 0x080, 0x0a0, 0x100, 0x120, 0x180,
};

class Bench {
public:
    Vrdl_params_wrapper d;
    const int rows, columns;
    unsigned cycle = 0, address = 0;
    bool writing = false;
    uint32_t reads[kChildren] = {}, writes[kChildren] = {};
    uint32_t memory[kChildren][kWords] = {};

    Bench(int enabled_rows, int enabled_columns) : rows(enabled_rows), columns(enabled_columns) {
        d.clk = 0;
        d.rst = 1;
        d.PSEL = d.PENABLE = d.PWRITE = 0;
        d.PADDR = d.PWDATA = d.PPROT = d.PSTRB = 0;
        for (unsigned child = 0; child < kChildren; ++child)
            for (unsigned word = 0; word < kWords; ++word)
                memory[child][word] = 0xa5000000u | (child << 12) | (word * 4);
        tick();
        d.rst = 0;
        tick();
        require(static_cast<int32_t>(d.configured_rows) == rows, "N_ROWS override not applied");
        require(static_cast<int32_t>(d.configured_columns) == columns, "N_COLS override not applied");
        check_state();
        idle();
    }

    void require(bool condition, const char* message, int child = -1, int word = -1) const {
        if (condition) return;
        std::cerr << "FAIL rows=" << rows << " columns=" << columns << " cycle=" << cycle
                  << " address=0x" << std::hex << address << std::dec
                  << (writing ? " write" : " read") << " child=" << child << " word=" << word
                  << ": " << message << '\n';
        std::exit(EXIT_FAILURE);
    }

    void tick() {
        d.clk = 0;
        d.eval();
        d.clk = 1;
        d.eval();
        d.clk = 0;
        d.eval();
        ++cycle;
    }

    bool enabled(unsigned child) const {
        if (child < 6) return static_cast<int>(child / 3) < rows && static_cast<int>(child % 3) < columns;
        if (child < 8) return static_cast<int>(child - 6) < rows;
        return true;
    }

    int decode(unsigned absolute_address) const {
        for (unsigned child = 0; child < kChildren; ++child)
            if (enabled(child) && absolute_address >= kBases[child] &&
                absolute_address < kBases[child] + 12)
                return static_cast<int>(child);
        return -1;
    }

    void check_state() const {
        for (unsigned child = 0; child < kChildren; ++child) {
            require(d.child_reads[child] == reads[child], "unexpected child read side effect", child);
            require(d.child_writes[child] == writes[child], "unexpected child write side effect", child);
            for (unsigned word = 0; word < kWords; ++word)
                require(d.child_memory[child][word] == memory[child][word],
                        "wrong child/word state changed", child, word);
        }
    }

    void check_bus(int target, bool access, unsigned offset = 0) const {
        const unsigned mask = target < 0 ? 0 : 1u << target;
        require(d.child_psel == mask, "wrong child select (disabled element or repacked map)");
        require(d.child_penable == (access ? mask : 0), "wrong child ACCESS phase");
        require(d.child_pwrite == (writing ? mask : 0), "wrong child write direction");
        for (unsigned child = 0; child < kChildren; ++child) {
            if (static_cast<int>(child) == target) {
                require(d.child_addr[child] == offset, "wrong child-local offset", child);
                require(d.child_wdata[child] == d.PWDATA, "write payload changed", child);
                require(d.child_prot[child] == d.PPROT, "APB protection changed", child);
                require(d.child_strb[child] == d.PSTRB, "APB byte strobes changed", child);
            } else {
                // gate_signals=True also makes disabled/unselected payloads quiet.
                require(d.child_addr[child] == 0 && d.child_wdata[child] == 0 &&
                            d.child_prot[child] == 0 && d.child_strb[child] == 0,
                        "unselected child has downstream payload activity", child);
            }
        }
    }

    void idle() {
        d.PSEL = d.PENABLE = 0;
        d.eval();
        check_bus(-1, false);
        require(!d.PREADY && !d.PSLVERR, "idle produced an upstream response");
        tick();
        check_state();
    }

    void transfer(unsigned absolute_address, bool write, uint32_t data = 0, unsigned strobes = 0) {
        address = absolute_address;
        writing = write;
        const int target = decode(address);
        const unsigned offset = target < 0 ? 0 : address - kBases[target];
        const unsigned word = offset / 4;
        const uint32_t response = target < 0 ? 0 : memory[target][word] ^ (reads[target] << 16);
        d.PSEL = 1;
        d.PENABLE = 0;
        d.PWRITE = write;
        d.PADDR = address;
        d.PWDATA = data;
        d.PPROT = (address >> 2) & 7;
        d.PSTRB = strobes;
        d.eval();
        check_bus(target, false, offset);
        tick();
        check_state();  // SETUP must have no side effects, even for unmapped writes.

        d.PENABLE = 1;
        d.eval();
        check_bus(target, true, offset);
        require(d.PREADY, "ACCESS did not complete");
        require(bool(d.PSLVERR) == (target < 0), "wrong mapped/disabled error response");
        if (!write) require(d.PRDATA == response, "wrong read response (child/word alias)", target, word);
        if (target >= 0) {
            if (write) {
                ++writes[target];
                for (unsigned lane = 0; lane < 4; ++lane) {
                    if (strobes & (1u << lane)) {
                        const uint32_t mask = 0xffu << (lane * 8);
                        memory[target][word] = (memory[target][word] & ~mask) | (data & mask);
                    }
                }
            } else {
                ++reads[target];
            }
        }
        tick();
        check_state();  // All other children, including disabled ones, stay untouched.
        idle();
    }
};
}  // namespace

int main(int argc, char** argv) {
    if (argc != 3) return EXIT_FAILURE;
    Verilated::commandArgs(argc, argv);
    const int rows = std::atoi(argv[1]);
    const int columns = std::atoi(argv[2]);
    // Flush before first eval: invalid configurations must fail in generated RTL.
    std::cout << "RDL_PARAMS_STARTED rows=" << rows << " columns=" << columns << std::endl;
    Bench bench(rows, columns);
    // Exhaust the 9-bit aligned address space, including disabled words and gaps.
    for (unsigned address = 0; address < 0x200; address += 4) {
        bench.transfer(address, false);
        bench.transfer(address, true, 0x5a000000u ^ (address * 0x010101u), ((address >> 2) % 15) + 1);
        bench.transfer(address, false);
    }
    // Revisit each physical child after all writes to expose any cross-child alias.
    for (unsigned child = 0; child < kChildren; ++child)
        for (unsigned word = 0; word < kWords; ++word)
            bench.transfer(kBases[child] + word * 4, false);
    bench.d.final();
    std::cout << "RDL_PARAMS_SUCCESS" << std::endl;
    return EXIT_SUCCESS;
}
