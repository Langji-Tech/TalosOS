#!/usr/bin/env python3
"""3×3×3 立方点云发布 —— 用于 rqt PointCloud2 可视化测试。

发布内容：27 个点，排成 3×3×3 立方网格，绕 Z 轴慢速自转；话题 `/demo/cloud`。
话题名匹配 `talos rqt` 的 PointCloud2 启发式（`/points|/cloud`），因此打开
rqt 后单击 + 即可直接添加为 3D 点云面板。

运行：
    python3 examples/python/pointcloud_publisher.py
    python3 examples/python/pointcloud_publisher.py --topic /demo/cloud --hz 10

另起一个终端打开 rqt：
    talos rqt
"""

import argparse
import math
import time

import numpy as np

from talosos.messages import Header, PointCloud2, PointField, Time
from talosos.runtime import Node, init, ok


def cube_points(spin_rad: float, side: float = 1.0) -> np.ndarray:
    """27 点 3×3×3 立方，绕 Z 轴旋转 `spin_rad`。"""
    axis = np.linspace(-side / 2, side / 2, 3, dtype=np.float32)
    pts = np.array([(x, y, z) for x in axis for y in axis for z in axis],
                     dtype=np.float32)
    c, s = math.cos(spin_rad), math.sin(spin_rad)
    R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float32)
    return pts @ R.T


def make_cloud(points: np.ndarray, frame_id: str) -> PointCloud2:
    data = np.ascontiguousarray(points.astype("<f4")).tobytes()
    now = time.time_ns()
    return PointCloud2(
        header=Header(frame_id=frame_id,
                        stamp=Time(sec=now // 1_000_000_000,
                                     nanosec=now % 1_000_000_000)),
        height=1,
        width=len(points),
        fields=[
            PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
            PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
            PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
        ],
        is_bigendian=False,
        point_step=12,           # 3 × float32
        row_step=12 * len(points),
        data=data,
        is_dense=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--topic", default="/demo/cloud")
    ap.add_argument("--hz", type=float, default=5.0)
    ap.add_argument("--side", type=float, default=1.0,
                      help="立方边长，单位米（默认 1.0）")
    ap.add_argument("--spin-hz", type=float, default=0.25,
                      help="绕 Z 轴转速（默认 0.25 Hz = 4 秒转一圈）")
    ap.add_argument("--frame-id", default="world")
    args = ap.parse_args()

    init()
    node = Node.create("cube_pub")
    pub = node.advertise(args.topic, PointCloud2)
    print(f"publishing 27-point cube -> {pub.key} @ {args.hz} Hz")

    period = 1.0 / args.hz
    omega = 2.0 * math.pi * args.spin_hz
    t0 = time.monotonic()
    while ok():
        t = time.monotonic() - t0
        pts = cube_points(omega * t, side=args.side)
        pub.publish(make_cloud(pts, frame_id=args.frame_id))
        time.sleep(period)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
