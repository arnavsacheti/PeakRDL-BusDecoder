.. _cpuif_axi4lite_response_ordering:

AXI4-Lite Ordered Response Design
=================================

Status and terminology
----------------------
This design is implemented by the generated AXI4-Lite adapters. The generated
module exposes an AXI4-Lite **Subordinate** interface (``s_axil``) to the
upstream Manager and one AXI4-Lite **Manager** interface (``m_axil_*``) per
downstream Subordinate. Source identifiers retain the older ``slave`` and
``master`` names.

AXI4-Lite has no transaction IDs, so all reads share one ordering domain and
all writes share another. The behavior sometimes described as "out-of-order
slave ordering" is therefore **same-direction response ordering across
downstream Subordinates**: children may become ready to respond in any order,
but the decoder emits responses in upstream request-acceptance order.


Ordering contract
-----------------
The decoder enforces these rules independently for reads and writes:

* A read enters the order at the upstream ``ARVALID && ARREADY`` handshake.
* ``AW`` and ``W`` are accepted independently and paired in their respective
  acceptance sequence. A write enters the response order when both beats of
  the next pair have been accepted.
* Each accepted transaction retains one decoded destination or a local-error
  marker, plus the request payload required for downstream dispatch.
* If request *i* precedes request *j*, response *j* is not presented upstream
  until response *i* completes its upstream ``VALID && READY`` handshake.
* A presented response and its payload remain stable until that handshake.
* A local ``DECERR`` occupies its normal position. It cannot pass an older
  child response, and a younger child response cannot pass it.
* Reads and writes have no order relative to one another.
* Reset flushes holding registers and both order queues, deasserts upstream
  response ``VALID``, and prevents a stale child response from being consumed.

The same contract covers repeated requests to one child. AXI4-Lite requires
that child to produce its responses in request order; the decoder dispatches
requests FIFO and associates the child's next response with the oldest entry
for that destination.


Response sequence
-----------------
Only the child named by the queue head receives response ``READY``. A faster
later child holds its response until older work completes.

.. mermaid::

    sequenceDiagram
        participant U as Upstream Manager
        participant D as Ordered decoder
        participant A as Child A
        participant B as Child B
        U->>D: Accept request A (order 0)
        D->>A: Issue request A
        U->>D: Accept request B (order 1)
        D->>B: Issue request B
        B-->>D: B VALID first
        D-->>B: B READY remains low
        A-->>D: A VALID
        D-->>A: A READY follows upstream READY
        D-->>U: Response A handshake
        D-->>B: B READY may now assert
        D-->>U: Response B handshake

Head-of-line blocking in this sequence is intentional and required to preserve
AXI4-Lite ordering.


Microarchitecture
-----------------
The implementation has separate circular read and write queues. Each queue has
three logical positions:

* a tail where newly accepted request metadata is stored;
* an issue pointer that holds the current downstream request stable through
  its request-channel handshake; and
* a response head that alone controls the upstream response mux and downstream
  response ``READY``.

The write side additionally has independent one-entry ``AW`` and ``W`` holding
registers. A queue entry records separate downstream ``AW``-sent and ``W``-sent
bits, because the selected child may accept those channels in different
cycles.

Response payload RAM is not required. A non-head child is back-pressured and,
as required by AXI, retains its response ``VALID`` and payload. The response
fanin mux selects the queue-head child; the upstream ``READY`` is propagated
only to that child. Local errors synthesize a head response with ``DECERR``.

.. mermaid::

    stateDiagram-v2
        [*] --> Queued: upstream request accepted
        Queued --> Issuing: mapped destination reaches issue pointer
        Issuing --> Issuing: child READY low / hold request stable
        Issuing --> AwaitResponse: child request handshake complete
        Queued --> AwaitHead: local decode error
        AwaitResponse --> AwaitResponse: not queue head / child READY low
        AwaitResponse --> Visible: queue head and child VALID
        AwaitHead --> Visible: entry reaches queue head
        Visible --> Visible: upstream READY low / hold payload stable
        Visible --> [*]: upstream response handshake


Generated implementation boundaries
-----------------------------------
``cpuif/axi4lite/axi4_lite_tmpl.sv`` owns the holding registers, circular
queues, issue/response pointers, request acceptance, reset, and upstream
responses. ``axi4_lite_cpuif.py`` generates per-child request fanout, selective
response ``READY``, response fanin, and interface-array intermediates. The
existing address decoder produces ``cpuif_sel_t`` destination metadata only at
queue insertion; outstanding requests never depend on a live upstream address.

``--axi4lite-max-outstanding`` selects the fixed queue depth and defaults to
four. The configured capacity is applied independently to the read and write
queues.


Operational constraints
-----------------------
* Request dispatch is FIFO per direction and handles one downstream request at
  a time. Multiple fully issued transactions may await responses concurrently.
* The adapter relies on every child obeying AXI's rule that ``VALID`` and its
  payload remain asserted and stable until ``READY``.
* Reset intentionally abandons pre-reset transactions. The surrounding system
  must reset downstream children consistently so pre-reset responses are not
  reintroduced as post-reset traffic.
* Queue depth bounds accepted work and destination metadata. Full queues
  deassert upstream request ``READY`` until a response is removed.


Verification coverage
---------------------
Focused Cocotb tests cover independently ordered ``AW``/``W`` acceptance,
downstream request wait states, upstream response back-pressure and payload
stability, cross-child and same-child delayed responses, local ``DECERR``,
reset, flat ports, SystemVerilog interfaces, rolled arrays, and variable decode
depth. Randomized smoke traffic varies write channel order and address/child
selection. Generator tests pin the queue-depth API and the separation between
request-issue and response-head selectors.
