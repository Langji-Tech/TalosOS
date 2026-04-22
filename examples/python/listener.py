#!/usr/bin/env python3
"""Minimal Python subscriber — mirror of examples/cpp/listener.cc.

Pairs with talker.py (same process) or the C++ talker (cross-process).
"""

from __future__ import annotations

from talosos.messages import String
from talosos.runtime import Node, init


def main() -> int:
    init()
    node = Node.create("py_listener")

    def on_message(msg: String) -> None:
        print(f"received: {msg.data}")

    node.subscribe("/py_talker/chatter", String, on_message)
    print("py_listener listening on /py_talker/chatter")
    node.spin()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
