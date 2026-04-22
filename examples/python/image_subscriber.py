#!/usr/bin/env python3
"""Python image subscriber — mirror of examples/cpp/image_demo/image_subscriber.cc.

Receives sensor_msgs::CompressedImage on /camera/image/compressed, prints
metadata + a content hash, and writes the first N frames to
/tmp/py_image_demo_frame_*.png so you can sha256sum them against the source.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

from talosos.messages import CompressedImage
from talosos.runtime import Node, init


def fnv1a(data: bytes) -> int:
    h = 0x811c9dc5
    for b in data:
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def main() -> int:
    dump_n = int(sys.argv[1]) if len(sys.argv) > 1 else 3

    init()
    node = Node.create("py_image_subscriber")

    counter = {"saved": 0}
    lock = threading.Lock()

    def on_image(msg: CompressedImage) -> None:
        h = fnv1a(bytes(msg.data))
        print(f"got frame stamp={msg.header.stamp.sec}.{msg.header.stamp.nanosec:09d} "
              f"frame_id={msg.header.frame_id} format={msg.format} "
              f"bytes={len(msg.data)} hash={h:08x}")
        with lock:
            idx = counter["saved"]
            if idx < dump_n:
                out = Path(f"/tmp/py_image_demo_frame_{idx}.png")
                out.write_bytes(bytes(msg.data))
                counter["saved"] = idx + 1
                print(f"wrote {out}")

    node.subscribe("/camera/image/compressed", CompressedImage, on_image)
    print("py_image_subscriber listening on /camera/image/compressed")
    node.spin()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
