from systemrdl.udp import UDPDefinition
from .rw_buffering import BufferWrites, WBufferTrigger
from .rw_buffering import BufferReads, RBufferTrigger
from .extended_swacc import ReadSwacc, WriteSwacc
from .fixedpoint import IntWidth, FracWidth
from .signed import IsSigned

ALL_UDPS: list[type[UDPDefinition]] = [
    BufferWrites,
    WBufferTrigger,
    BufferReads,
    RBufferTrigger,
    ReadSwacc,
    WriteSwacc,
    IntWidth,
    FracWidth,
    IsSigned,
]
