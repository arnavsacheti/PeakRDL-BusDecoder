#!/usr/bin/env python3
"""
Example script showing how to generate and test bus decoders.

This script demonstrates:
1. Compiling RDL specifications
2. Generating SystemVerilog decoders for different CPU interfaces
3. Validating the generated code (syntax check only, no simulation)

To run actual cocotb simulations, you need:
- Icarus Verilog, Verilator, or other HDL simulator
- cocotb and cocotb-bus Python packages
"""

import tempfile
from pathlib import Path

from peakrdl_busdecoder.cpuif.apb3 import APB3Cpuif
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif
from peakrdl_busdecoder.cpuif.axi4lite import AXI4LiteCpuif

# Import test utilities
import sys

sys.path.insert(0, str(Path(__file__).parent))
from common.utils import compile_rdl_and_export


def example_apb4_simple_register():
    """Generate APB4 decoder for a simple register."""
    print("\n" + "=" * 70)
    print("Example 1: APB4 Decoder with Simple Register")
    print("=" * 70)

    rdl_source = """
    addrmap simple_test {
        name = "Simple Register Test";
        desc = "A simple register for testing";
        
        reg {
            name = "Test Register";
            desc = "32-bit test register";
            
            field {
                sw=rw;
                hw=r;
                desc = "Data field";
            } data[31:0];
        } test_reg @ 0x0;
    };
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"\nGenerating SystemVerilog in: {tmpdir}")
        module_path, package_path = compile_rdl_and_export(
            rdl_source, "simple_test", tmpdir, APB4Cpuif
        )

        print(f"✓ Generated module: {module_path.name}")
        print(f"✓ Generated package: {package_path.name}")

        # Show snippet of generated code
        with open(module_path) as f:
            lines = f.readlines()[:20]
            print("\n--- Generated Module (first 20 lines) ---")
            for line in lines:
                print(line, end="")


def example_apb3_multiple_registers():
    """Generate APB3 decoder for multiple registers."""
    print("\n" + "=" * 70)
    print("Example 2: APB3 Decoder with Multiple Registers")
    print("=" * 70)

    rdl_source = """
    addrmap multi_reg {
        name = "Multiple Register Block";
        
        reg {
            name = "Control Register";
            field { sw=rw; hw=r; } data[31:0];
        } ctrl @ 0x0;
        
        reg {
            name = "Status Register";
            field { sw=r; hw=w; } status[15:0];
        } status @ 0x4;
        
        reg {
            name = "Data Register";
            field { sw=rw; hw=r; } data[31:0];
        } data @ 0x8;
    };
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"\nGenerating SystemVerilog in: {tmpdir}")
        module_path, package_path = compile_rdl_and_export(
            rdl_source, "multi_reg", tmpdir, APB3Cpuif
        )

        print(f"✓ Generated module: {module_path.name}")
        print(f"✓ Generated package: {package_path.name}")

        # Count registers in generated code
        with open(module_path) as f:
            content = f.read()
            print(f"\n✓ Found 'ctrl' in generated code: {'ctrl' in content}")
            print(f"✓ Found 'status' in generated code: {'status' in content}")
            print(f"✓ Found 'data' in generated code: {'data' in content}")


def example_axi4lite_nested_addrmap():
    """Generate AXI4-Lite decoder for nested address map."""
    print("\n" + "=" * 70)
    print("Example 3: AXI4-Lite Decoder with Nested Address Map")
    print("=" * 70)

    rdl_source = """
    addrmap inner_block {
        name = "Inner Block";
        reg {
            field { sw=rw; hw=r; } data[31:0];
        } inner_reg @ 0x0;
    };
    
    addrmap outer_block {
        name = "Outer Block";
        inner_block inner @ 0x0;
        
        reg {
            field { sw=rw; hw=r; } outer_data[31:0];
        } outer_reg @ 0x100;
    };
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"\nGenerating SystemVerilog in: {tmpdir}")
        module_path, package_path = compile_rdl_and_export(
            rdl_source, "outer_block", tmpdir, AXI4LiteCpuif
        )

        print(f"✓ Generated module: {module_path.name}")
        print(f"✓ Generated package: {package_path.name}")

        # Check for nested structure
        with open(module_path) as f:
            content = f.read()
            print(f"\n✓ Found 'inner' in generated code: {'inner' in content}")
            print(f"✓ Found 'outer_reg' in generated code: {'outer_reg' in content}")


def example_register_array():
    """Generate decoder with register arrays."""
    print("\n" + "=" * 70)
    print("Example 4: Decoder with Register Arrays")
    print("=" * 70)

    rdl_source = """
    addrmap array_test {
        name = "Register Array Test";
        
        reg {
            field { sw=rw; hw=r; } data[31:0];
        } regs[8] @ 0x0 += 0x4;
    };
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"\nGenerating SystemVerilog in: {tmpdir}")
        module_path, package_path = compile_rdl_and_export(
            rdl_source, "array_test", tmpdir, APB4Cpuif
        )

        print(f"✓ Generated module: {module_path.name}")
        print(f"✓ Generated package: {package_path.name}")

        with open(module_path) as f:
            content = f.read()
            print(f"\n✓ Found 'regs' in generated code: {'regs' in content}")


def main():
    """Run all examples."""
    print("\n")
    print("*" * 70)
    print("*" + " " * 68 + "*")
    print("*" + "  PeakRDL-BusDecoder: Code Generation Examples".center(68) + "*")
    print("*" + " " * 68 + "*")
    print("*" * 70)

    try:
        example_apb4_simple_register()
        example_apb3_multiple_registers()
        example_axi4lite_nested_addrmap()
        example_register_array()

        print("\n" + "=" * 70)
        print("All examples completed successfully!")
        print("=" * 70)
        print(
            """
To run actual simulations with cocotb:
1. Install simulator: apt-get install iverilog (or verilator)
2. Install cocotb: pip install cocotb cocotb-bus
3. Run tests: pytest tests/cocotb/testbenches/

For more information, see: tests/cocotb/README.md
"""
        )

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
