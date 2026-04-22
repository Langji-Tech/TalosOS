#!/usr/bin/env python3
"""Python image publisher — mirror of examples/cpp/image_demo/image_publisher.cc.

Loads a PNG file and publishes it as sensor_msgs::CompressedImage at a fixed
rate. The wire payload is byte-identical to the C++ publisher, so the C++
image_subscriber can consume this publisher's messages transparently (and
vice versa).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from talosos.messages import CompressedImage, Header, Time
from talosos.runtime import Node, init, ok


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path("/home/ubuntu24/Software/TalosOS/image.png")
    hz = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0

    if not path.is_file():
        print(f"error: image not found: {path}", file=sys.stderr)
        return 2

    data = path.read_bytes()
    print(f"loaded {path} ({len(data)} bytes)")

    init()
    node = Node.create("py_image_publisher")
    pub = node.advertise("/camera/image/compressed", CompressedImage)

    msg = CompressedImage(
        header=Header(stamp=Time(), frame_id="camera"),
        format="png",
        data=data,
    )

    period = 1.0 / hz if hz > 0 else 0.5
    i = 0
    while ok():
        now = time.time()
        msg.header.stamp = Time(sec=int(now), nanosec=int((now - int(now)) * 1e9))
        pub.publish(msg)
        print(f"published frame #{i} ({len(data)} bytes)")
        i += 1
        time.sleep(period)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
