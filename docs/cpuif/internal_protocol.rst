.. _cpuif_protocol:

Internal CPUIF Protocol
=======================

Internally, the bus decoder uses a small set of common request/response signals
that each CPU interface adapter drives. The baseline protocol is intentionally
simple and represents one decoded transaction at a time. APB adapters hold this
transaction stable through completion.

The stateful AXI4-Lite adapter uses the request side as a one-cycle decode event:
it latches the resulting child-select metadata and request payload into ordered
queues, then uses a retained queue head for response fanin. It can therefore
support multiple externally outstanding transactions even though the common
decode signals represent only one acceptance event in a cycle.


Signal Descriptions
-------------------

Request
^^^^^^^
cpuif_req
    When asserted, a read or write transfer is being decoded. A simple adapter
    keeps it asserted and stable until completion; a stateful adapter may latch
    the decode result on an acceptance event.

cpuif_wr_en
    When asserted alongside ``cpuif_req``, denotes a write transfer.

cpuif_rd_en
    When asserted alongside ``cpuif_req``, denotes a read transfer.

cpuif_wr_addr / cpuif_rd_addr
    Byte address of the write or read transfer, respectively.

cpuif_wr_data
    Data to be written for the write transfer.

cpuif_wr_byte_en
    Active-high byte-enable strobes for writes. Some CPU interfaces do not
    provide byte enables and may drive this as all-ones.


Read Response
^^^^^^^^^^^^^
cpuif_rd_ack
    Indicates that the selected read response is valid. Qualifies
    ``cpuif_rd_err`` and ``cpuif_rd_data``.

cpuif_rd_err
    Indicates that the read transaction failed. The CPU interface should return
    an error response if possible.

cpuif_rd_data
    Read data. Sampled on the same cycle that ``cpuif_rd_ack`` is asserted.


Write Response
^^^^^^^^^^^^^^
cpuif_wr_ack
    Indicates that the selected write response is valid. Qualifies
    ``cpuif_wr_err``.

cpuif_wr_err
    Indicates that the write transaction failed. The CPU interface should return
    an error response if possible.


Transfers
---------

Transfers have the following characteristics:

* Baseline adapters expose one stable transaction until the corresponding
  ``cpuif_*_ack`` is asserted.
* Stateful adapters may latch destination metadata on a request event and
  manage several external transactions around this decode layer.
* The adapter is responsible for returning external responses in the ordering
  required by its bus protocol. See :ref:`cpuif_axi4lite_response_ordering`.
