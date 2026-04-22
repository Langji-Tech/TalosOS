"""CDR reader mirroring include/talosos/serialization.h bit-for-bit.

Little-endian (representation_id 0x0001) only; strings are length-prefixed with
null terminator; primitives follow standard CDR alignment relative to the
4-byte encapsulation header.
"""


import struct

_ENCAP_HEADER_SIZE = 4


class CdrError(ValueError):
    """Raised on malformed CDR input (too short, bad encoding)."""


class CdrReader:
    __slots__ = ("_buf", "_pos")

    def __init__(self, buf: bytes) -> None:
        if len(buf) < _ENCAP_HEADER_SIZE:
            raise CdrError("buffer too small for encapsulation header")
        self._buf = buf
        self._pos = _ENCAP_HEADER_SIZE

    def _align(self, n: int) -> None:
        body = self._pos - _ENCAP_HEADER_SIZE
        pad = (n - (body % n)) % n
        self._pos += pad

    def _ensure(self, n: int) -> None:
        if self._pos + n > len(self._buf):
            raise CdrError(f"underrun reading {n} byte(s) at {self._pos}")

    def u8(self) -> int:
        self._ensure(1)
        v = self._buf[self._pos]
        self._pos += 1
        return v

    def i8(self) -> int:
        v = self.u8()
        return v - 256 if v >= 128 else v

    def bool_(self) -> bool:
        return self.u8() != 0

    def u16(self) -> int:
        self._align(2)
        self._ensure(2)
        v, = struct.unpack_from("<H", self._buf, self._pos)
        self._pos += 2
        return v

    def i16(self) -> int:
        self._align(2)
        self._ensure(2)
        v, = struct.unpack_from("<h", self._buf, self._pos)
        self._pos += 2
        return v

    def u32(self) -> int:
        self._align(4)
        self._ensure(4)
        v, = struct.unpack_from("<I", self._buf, self._pos)
        self._pos += 4
        return v

    def i32(self) -> int:
        self._align(4)
        self._ensure(4)
        v, = struct.unpack_from("<i", self._buf, self._pos)
        self._pos += 4
        return v

    def u64(self) -> int:
        self._align(8)
        self._ensure(8)
        v, = struct.unpack_from("<Q", self._buf, self._pos)
        self._pos += 8
        return v

    def i64(self) -> int:
        self._align(8)
        self._ensure(8)
        v, = struct.unpack_from("<q", self._buf, self._pos)
        self._pos += 8
        return v

    def f32(self) -> float:
        self._align(4)
        self._ensure(4)
        v, = struct.unpack_from("<f", self._buf, self._pos)
        self._pos += 4
        return v

    def f64(self) -> float:
        self._align(8)
        self._ensure(8)
        v, = struct.unpack_from("<d", self._buf, self._pos)
        self._pos += 8
        return v

    def string(self) -> str:
        n = self.u32()
        if n == 0:
            return ""
        self._ensure(n)
        # Strip trailing NUL.
        raw = self._buf[self._pos:self._pos + n - 1]
        self._pos += n
        return raw.decode("utf-8", errors="replace")

    def bytes_raw(self, n: int) -> bytes:
        self._ensure(n)
        out = self._buf[self._pos:self._pos + n]
        self._pos += n
        return bytes(out)

    def sequence(self, element_reader):
        n = self.u32()
        return [element_reader(self) for _ in range(n)]

    def sequence_u8(self) -> bytes:
        n = self.u32()
        self._ensure(n)
        out = self._buf[self._pos:self._pos + n]
        self._pos += n
        return bytes(out)

    def sequence_i8(self) -> bytes:
        return self.sequence_u8()

    def fixed(self, n: int, element_reader):
        return [element_reader(self) for _ in range(n)]

    @property
    def remaining(self) -> int:
        return len(self._buf) - self._pos
