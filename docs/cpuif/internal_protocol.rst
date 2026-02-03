.. _cpuif_protocol:

Internal CPUIF Protocol
=======================

Internally, the bus decoder uses a small set of common request/response signals
that each CPU interface adapter must drive. This protocol is intentionally simple
and supports a single outstanding transaction at a time. The CPU interface logic
is responsible for holding request signals stable until the transaction completes.


Signal Descriptions
-------------------

Request
^^^^^^^
cpuif_req
    When asserted, a read or write transfer is in progress. Request signals must
    remain stable until the transfer completes.

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
    Single-cycle strobe indicating a read transfer has completed.
    Qualifies ``cpuif_rd_err`` and ``cpuif_rd_data``.

cpuif_rd_err
    Indicates that the read transaction failed. The CPU interface should return
    an error response if possible.

cpuif_rd_data
    Read data. Sampled on the same cycle that ``cpuif_rd_ack`` is asserted.


Write Response
^^^^^^^^^^^^^^
cpuif_wr_ack
    Single-cycle strobe indicating a write transfer has completed.
    Qualifies ``cpuif_wr_err``.

cpuif_wr_err
    Indicates that the write transaction failed. The CPU interface should return
    an error response if possible.


Transfers
---------

Transfers have the following characteristics:

* Only one outstanding transaction is supported.
* The CPU interface must hold ``cpuif_req`` and request parameters stable until
  the corresponding ``cpuif_*_ack`` is asserted.
* Responses shall arrive in the same order as requests.
