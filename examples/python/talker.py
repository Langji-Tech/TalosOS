#!/usr/bin/env python3
"""Minimal Python publisher — mirror of examples/cpp/talker.cc.

Run with:
    source /opt/talosos/setup.bash
    python3 examples/python/talker.py
"""

from __future__ import annotations

import time

from talosos.messages import String
from talosos.runtime import Node, init, ok


def main() -> int:
    init()
    node = Node.create("py_talker")
    pub = node.advertise("chatter", String)   # relative name -> py_talker/chatter

    i = 0
    while ok():
        msg = String(data=f"hello from py_talker #{i}")
        pub.publish(msg)
        print(f"publish '{msg.data}' -> {pub.key}")
        i += 1
        time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
