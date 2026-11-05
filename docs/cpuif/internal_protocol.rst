.. _cpuif_protocol:

Internal CPUIF Protocol
=======================

Internally, CPU interface adapters use common combinational request-decode
signals and protocol-specific response signals. This layer does not impose a
global one-transaction-in-flight rule. Read and write decode can occur
independently, including in the same cycle.

APB holds one live request through completion. AXI4-Lite uses decode events to
enqueue retained destination and payload metadata in separate bounded read and
write queues; response fanin uses the corresponding queue head, not the current
address. AHB-Lite exposes the live address phase but accepts it only on an
``HREADY``-high edge; responses use the retained preceding data-phase
destination. Its live write data belongs to that preceding write, not the
current address.


Signal Descriptions
-------------------

Request
^^^^^^^
cpuif_req
    Qualifies the direction-specific request enables. It may describe an APB
    request held through completion, an AXI queue insertion, or an AHB address
    phase whose acceptance is additionally gated by ``HREADY``.

cpuif_wr_en
    Qualifies write decoding alongside ``cpuif_req``.

cpuif_rd_en
    Qualifies read decoding alongside ``cpuif_req``. Read and write enables
    are not required to be mutually exclusive.

cpuif_wr_addr / cpuif_rd_addr
    Byte address of the write or read transfer, respectively.

cpuif_wr_data
    Write data for the adapter's current request/data phase. AHB forwards live
    ``HWDATA`` for the preceding accepted write rather than capturing it with
    the address.

cpuif_wr_byte_en
    Active-high byte-enable strobes for writes. Some CPU interfaces do not
    provide byte enables and may drive this as all-ones.


Read Response
^^^^^^^^^^^^^
cpuif_rd_ack
    Read response available from the retained or currently selected target;
    qualifies ``cpuif_rd_err`` and ``cpuif_rd_data`` when the adapter completes
    a read. It is not universally a one-cycle pulse.

cpuif_rd_err
    Indicates that the read transaction failed. The CPU interface should return
    an error response if possible.

cpuif_rd_data
    Read data. Sampled on the same cycle that ``cpuif_rd_ack`` is asserted.


Write Response
^^^^^^^^^^^^^^
cpuif_wr_ack
    Write response available; qualifies ``cpuif_wr_err`` on completion. AXI
    response availability may remain asserted through upstream backpressure.

cpuif_wr_err
    Indicates that the write transaction failed. The CPU interface should return
    an error response if possible.


Transfers
---------

Transfers have the following characteristics:

* Direction-qualified active decode defaults to a local error and clears it on
  each permitted scalar or array-element hit; idle selects/errors remain zero.
* APB selection remains live. AXI queue entries and AHB data-phase state retain
  destinations so a later address cannot redirect an older response.
* Response availability need not be a single-cycle strobe. The external
  protocol's completion handshake determines when retained state advances.
* AXI permits independent read/write traffic and returns local ``DECERR`` in
  per-direction FIFO order; see :ref:`cpuif_axi4lite_response_ordering`.
* AHB uses one shared pipeline and local two-cycle ERROR responses; see
  :ref:`cpuif_ahblite`.
* Both directions share one exported layout. Standalone custom read/write
  layouts are not implemented.
