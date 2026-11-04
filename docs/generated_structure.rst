.. _generated_decoder_structure:

Generated Decoder Structure by Option
=====================================

The diagrams on this page are rendered from Mermaid source during the Sphinx
build. They show structural relationships in generated RTL, not exact gates or
cycle timing. See :doc:`configuring` for the complete option descriptions.


Common structure
----------------
Every generated decoder has one upstream CPU interface, a shared address-decode
tree, and one downstream interface at each selected decode boundary. The CPU
interface adapter determines how requests are retained and how responses are
returned.

.. mermaid::

    flowchart LR
        U["Upstream CPU interface"] --> A["Protocol adapter"]
        A --> D["Address decoder<br/>direction-qualified selection"]
        D --> S["Protocol-specific retained destination"]
        D --> F["Protocol request fanout"]
        S --> R
        F --> C0["Child 0 interface"]
        F --> C1["Child 1 interface"]
        F --> CN["Child N interface"]
        C0 --> R["Response fanin"]
        C1 --> R
        CN --> R
        R --> A
        D --> E["Local error response"]
        E --> A

APB routes the active transfer, with optional register slices retaining its
payload and selection. AXI4-Lite stores each accepted destination in separate
read and write order queues; the response fanin selection comes from the
appropriate queue head. AHB-Lite retains one shared data-phase destination and
direction when an address phase is accepted with ``HREADY`` high. Its response
does not follow the next live address.

Read/write qualification uses each protocol's request direction: AXI4-Lite has
independent request lanes, whereas APB and AHB-Lite qualify a shared address
with ``PWRITE`` or ``HWRITE``. This is adapter behavior, not a standalone option
for configuring different read and write address layouts.


Which flags change structure?
-----------------------------

.. list-table:: Structural effect of command-line options
    :header-rows: 1
    :widths: 28 18 54

    * - Option
      - Effect
      - Generated change
    * - ``--cpuif``
      - Topology and ports
      - Selects APB3, APB4, AXI4-Lite, or single-manager AHB-Lite protocol logic
        and either interface or flat ports.
    * - ``--clk-src``
      - Ports and state clocking
      - For APB/AXI4-Lite, chooses top-level ``clk``/``rst`` or protocol
        clock/reset members. AHB-Lite always uses ingress ``HCLK``/``HRESETn``.
    * - ``--max-decode-depth``
      - Routing topology
      - Moves the downstream interface boundary through the SystemRDL hierarchy.
    * - ``--unroll``
      - Port topology
      - Replaces a downstream interface array with one named port per element.
    * - ``--axi4lite-max-outstanding``
      - Internal storage
      - Resizes the independent AXI4-Lite read and write order queues.
    * - ``--apb-buffer``
      - Pipeline state
      - Adds an input slice, output slice, both, or neither around the APB decoder.
    * - ``--gate-signals``
      - APB combinational logic
      - Adds per-child masking to otherwise broadcast APB payload signals.
    * - ``--parametrize``
      - Module parameters and loop bounds
      - Makes the active portion of eligible arrays configurable up to a static maximum.
    * - ``--addr-width``
      - Signal width only
      - Widens the upstream address and stored AXI address fields; topology is unchanged.
    * - ``--module-name`` / ``--package-name``
      - Names only
      - Renames generated declarations and files; topology is unchanged.


CPU interface and port style
----------------------------
``--cpuif`` makes two independent choices: protocol behavior and port style.
The address decoder and SystemRDL routing map remain shared.

.. mermaid::

    flowchart TB
        RDL["Compiled SystemRDL address map"] --> CORE["Shared decode tree and child map"]
        CORE --> APB3["APB3 adapter"]
        CORE --> APB4["APB4 adapter"]
        CORE --> AXI["AXI4-Lite adapter<br/>AW/W holds + ordered queues"]
        CORE --> AHB["AHB-Lite adapter<br/>one retained data phase"]
        APB3 --> APB3I["apb3<br/>SystemVerilog interfaces"]
        APB3 --> APB3F["apb3-flat<br/>discrete ports"]
        APB4 --> APB4I["apb4<br/>SystemVerilog interfaces"]
        APB4 --> APB4F["apb4-flat<br/>discrete ports"]
        AXI --> AXII["axi4-lite<br/>SystemVerilog interfaces"]
        AXI --> AXIF["axi4-lite-flat<br/>discrete ports"]
        AHB --> AHBI["ahb-lite<br/>SystemVerilog interfaces"]
        AHB --> AHBF["ahb-lite-flat<br/>discrete ports"]

Interface and flat variants implement the same decode and handshake behavior.
Only the generated port representation changes.


Clock and reset source
----------------------
The decoder always has a selected clock/reset source. APB uses sequential state
only when buffering is enabled; AXI4-Lite always uses sequential state for
holding registers and ordered-response queues. AHB-Lite always uses sequential
state to retain its data phase.

For APB and AXI4-Lite, ``--clk-src design`` (the default) selects explicit
``clk``/``rst`` ports for decoder state. The surrounding design distributes the
same clock domain to the decoder and downstream children.

.. mermaid::

    flowchart LR
        SYS["System clock/reset source"] --> DCLK["Decoder clk / rst ports"]
        SYS --> C0["Child 0 clock/reset"]
        SYS --> C1["Child 1 clock/reset"]
        U["Upstream bus payload ports"] --> D["Generated decoder"]
        DCLK --> D
        D --> C0
        D --> C1

For APB and AXI4-Lite, ``--clk-src cpuif`` instead selects clock/reset from the
upstream protocol interface and omits separate ``clk``/``rst`` ports. Flat
variants expose pass-through clock/reset outputs for each child. SystemVerilog
manager modports declare clock/reset as inputs, so their interface instances
must be connected externally to the same domain as the upstream interface.

.. mermaid::

    flowchart LR
        U["Upstream bus<br/>PCLK/PRESETn or ACLK/ARESETn"] --> D["Generated decoder state"]
        D --> F0["Flat child 0 clock/reset output"]
        D --> F1["Flat child 1 clock/reset output"]
        SYS["Common interface clock source"] -.-> I0["SV child 0 interface clock/reset"]
        SYS -.-> I1["SV child 1 interface clock/reset"]

AHB-Lite always takes ``HCLK`` and active-low ``HRESETn`` from its ingress,
regardless of ``--clk-src``. Neither setting adds separate ``clk``/``rst``
ports or flat child clock/reset outputs. Wire every child externally to that
same domain, for both flat and SystemVerilog interface variants:

.. mermaid::

    flowchart LR
        SYS["Common HCLK / HRESETn source"] --> U["Ingress AHB-Lite clock/reset"]
        U --> D["Retained data-phase state"]
        SYS --> C0["Child 0 clock/reset"]
        SYS --> C1["Child 1 clock/reset"]

These are single-clock-domain adapters, not clock-domain crossings. In
particular, neither stateful AXI4-Lite nor AHB-Lite can omit its clock/reset
source.


Decode depth
------------
``--max-decode-depth`` controls where the generator stops descending and emits
downstream interfaces. Consider a top-level map with two blocks, where block A
contains a register file and block B contains a register:

.. mermaid::

    flowchart TB
        T["top"] --> A["block_a"]
        T --> B["block_b"]
        A --> RF["regfile"]
        RF --> R0["reg_0"]
        RF --> R1["reg_1"]
        B --> R2["reg_2"]

The generated boundary moves with the selected depth:

.. mermaid::

    flowchart LR
        subgraph D1["--max-decode-depth 1 (default)"]
            X1["decoder"] --> A1["m_*_block_a"]
            X1 --> B1["m_*_block_b"]
        end
        subgraph D2["--max-decode-depth 2"]
            X2["decoder"] --> RF2["m_*_regfile"]
            X2 --> R22["m_*_reg_2"]
        end
        subgraph D0["--max-decode-depth 0"]
            X0["decoder"] --> R00["m_*_reg_0"]
            X0 --> R10["m_*_reg_1"]
            X0 --> R20["m_*_reg_2"]
        end

Depth zero means unlimited descent to leaf boundaries. External components and
other enforced decode boundaries can stop descent earlier.

Downstream port names and address-width constants use the same canonical
target identity, allocated by ``DesignState.get_target_name(node)`` for every
protocol. Unique local names are retained; collisions use flattened hierarchy
paths, with suffixes where needed to keep the names unique. The ``m_*`` names
above are schematic, not a separate naming rule.


Rolled and unrolled arrays
--------------------------
By default, an arrayed child remains one arrayed downstream port. ``--unroll``
emits a separately named port for every elaborated element. Address routing is
unchanged.

.. mermaid::

    flowchart LR
        subgraph R["Default rolled array"]
            DR["decoder"] --> AR["m_*_regs [4]"]
        end
        subgraph U["--unroll"]
            DU["decoder"] --> U0["m_*_regs_0"]
            DU --> U1["m_*_regs_1"]
            DU --> U2["m_*_regs_2"]
            DU --> U3["m_*_regs_3"]
        end

For multidimensional arrays, unrolled names contain one numeric suffix per
dimension, such as ``m_*_matrix_1_2``.


AHB-Lite address and data phases
--------------------------------
AHB-Lite supports one upstream manager and one shared read/write pipeline,
not multi-manager arbitration or independent read/write queues. Address decode
can present the following transfer while the retained data phase is waiting:

.. mermaid::

    flowchart LR
        A["Live HADDR / HWRITE / HTRANS / HSEL"] --> DEC["Address-phase decode"]
        DEC --> CHILD["Child address/control"]
        DEC --> HOLD["Retain destination + direction<br/>only when HREADY is high"]
        WD["Live HWDATA<br/>preceding accepted write"] --> CHILD
        CHILD --> RESP["Child HREADYOUT / HRESP / HRDATA"]
        HOLD --> MUX["Data-phase response mux"]
        RESP --> MUX
        HOLD --> ERR["Local miss: two-cycle ERROR"]
        ERR --> MUX
        MUX --> UP["Upstream data-phase response"]

During a wait, the retained destination and direction remain unchanged;
``HWDATA`` is not captured with the new address, since it belongs to the
preceding accepted write. A local decode miss returns not-ready/ERROR followed
by ready/ERROR. Mapped child responses, including errors and wait states, pass
through unchanged. See :doc:`cpuif/ahblite` for the handshake and aperture rules.



AXI4-Lite outstanding depth
---------------------------
``--axi4lite-max-outstanding N`` sets the fixed capacity of each order queue.
It does not change the AXI ports or add transaction IDs. The read and write
directions remain independent, and the write side keeps its separate one-entry
``AW`` and ``W`` holding registers.

.. mermaid::

    flowchart LR
        AR["Accepted AR"] --> RQ["Read order queue<br/>N entries"]
        RQ --> RI["FIFO AR issue"]
        RI --> RH["Head-selected R response"]
        AW["Accepted AW"] --> AWH["AW holding register"]
        W["Accepted W"] --> WH["W holding register"]
        AWH --> PAIR["Pair AW + W"]
        WH --> PAIR
        PAIR --> WQ["Write order queue<br/>N entries"]
        WQ --> WI["FIFO AW/W issue"]
        WI --> WHD["Head-selected B response"]

When a queue contains ``N`` accepted transactions, its upstream request
``READY`` is deasserted until the oldest response is removed. Increasing the
depth increases destination/request storage but does not remove intentional
head-of-line response ordering.


APB buffering and signal gating
-------------------------------
``--apb-buffer`` places optional one-entry slices around the APB routing core.
The four settings are structural combinations of the same two slices:

.. mermaid::

    flowchart LR
        U["Upstream APB"] --> IN["Input slice<br/>in or both"]
        IN --> D["APB decode + fanout/fanin"]
        D --> OUT["Output slice<br/>out or both"]
        OUT --> U
        U -.->|none/out bypass input slice| D
        D -.->|none/in bypass output slice| U

``--gate-signals`` changes the downstream APB payload path rather than its
interface topology:

.. mermaid::

    flowchart LR
        P["Broadcast APB payload"] --> DIRECT["Default: direct fanout"]
        DIRECT --> C0["Child 0"]
        DIRECT --> C1["Child 1"]
        P --> MASK["--gate-signals:<br/>mask with each child select"]
        S["Per-child PSEL"] --> MASK
        MASK --> G0["Selected payload or zero"]
        MASK --> G1["Selected payload or zero"]

Buffering requires ``--clk-src design``. Gating is combinational and does not
change the APB transfer phases.


Parameterized array extent
--------------------------
With ``--parametrize``, an address-modifying root parameter controls the active
loop bound while ports, select structs, and address space remain sized for the
compiled maximum.

.. mermaid::

    flowchart LR
        P["Module parameter<br/>N_ACTIVE = 3, maximum = 8"] --> L["Decode/fanout/fanin loop bound"]
        L --> A0["element 0 active"]
        L --> A1["element 1 active"]
        L --> A2["element 2 active"]
        MAX["Static ports and select storage [8]"] --> A0
        MAX --> A1
        MAX --> A2
        MAX -.-> I["elements 3..7 present but inactive"]

This is elaboration-time configurability, not runtime address-map resizing.
See :doc:`parameters` for extraction rules and generated assertions.
