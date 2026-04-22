#!/usr/bin/env python3
"""Python service server — addition using inline-declared messages.

Demonstrates the TALOS_MESSAGE_FIELDS equivalent in Python: a dataclass with a
`.read(CdrReader)` class method. The runtime auto-serializes it back out
through talosos.runtime._encode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from talosos.cdr import CdrReader
from talosos.runtime import Node, init


@dataclass
class AddTwoIntsRequest:
    a: int = 0
    b: int = 0
    TYPE_NAME: ClassVar[str] = "AddTwoIntsRequest"

    @classmethod
    def read(cls, r: CdrReader) -> "AddTwoIntsRequest":
        return cls(a=r.i64(), b=r.i64())


@dataclass
class AddTwoIntsResponse:
    sum: int = 0
    TYPE_NAME: ClassVar[str] = "AddTwoIntsResponse"

    @classmethod
    def read(cls, r: CdrReader) -> "AddTwoIntsResponse":
        return cls(sum=r.i64())


# Teach talosos.runtime how to encode these two.
from talosos.runtime import _WRITERS_BY_CLASS, _CdrWriter  # type: ignore


def _write_request(w: _CdrWriter, v: AddTwoIntsRequest) -> None:
    w.i64(v.a); w.i64(v.b)


def _write_response(w: _CdrWriter, v: AddTwoIntsResponse) -> None:
    w.i64(v.sum)


_WRITERS_BY_CLASS[AddTwoIntsRequest] = _write_request
_WRITERS_BY_CLASS[AddTwoIntsResponse] = _write_response


def main() -> int:
    init()
    node = Node.create("py_add_two_ints_server")

    def handler(req: AddTwoIntsRequest) -> AddTwoIntsResponse:
        resp = AddTwoIntsResponse(sum=req.a + req.b)
        print(f"service {req.a} + {req.b} = {resp.sum}")
        return resp

    svc = node.advertise_service(
        "/add_two_ints", AddTwoIntsRequest, AddTwoIntsResponse, handler)
    print(f"ready at {svc._raw.key}")
    node.spin()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
