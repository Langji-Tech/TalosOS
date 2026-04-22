#!/usr/bin/env python3
"""Python service client — calls /add_two_ints.

CDR bytes are wire-compatible with the C++ add_two_ints_server example, so you
can run either server and either client interchangeably.
"""

from __future__ import annotations

import sys

from talosos.runtime import Node, init

# Re-use the dataclasses defined in the server example so we stay in one
# source of truth — they register their own CDR writers on import.
from add_two_ints_server import AddTwoIntsRequest, AddTwoIntsResponse  # noqa: F401


def main() -> int:
    a = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    b = int(sys.argv[2]) if len(sys.argv) > 2 else 35

    init()
    node = Node.create("py_add_two_ints_client")
    client = node.create_service_client(
        "/add_two_ints", AddTwoIntsRequest, AddTwoIntsResponse)

    resp = client.call(AddTwoIntsRequest(a=a, b=b), timeout_ms=3000)
    if resp is None:
        print("service call timed out", file=sys.stderr)
        return 1
    print(f"{a} + {b} = {resp.sum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
