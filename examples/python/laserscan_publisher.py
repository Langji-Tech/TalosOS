#!/usr/bin/env python3
"""仿真 LaserScan 发布 —— 用于 rqt LaserScan 可视化测试。

发布内容：360° 全方位激光扫描，默认 360 条射线，10 Hz。模拟场景：
  * 5 m 远的"房间"墙壁
  * 一个以 0.5 Hz 绕身转动的近物（1.5 m）
  * 一个固定在 +Y 方向的静态物（2.5 m）
话题 `/demo/scan`，话题名匹配 `talos rqt` 的 LaserScan 启发式（`/scan`），
rqt 会自动识别并用极坐标散点显示。

运行：
    python3 examples/python/laserscan_publisher.py
    python3 examples/python/laserscan_publisher.py --topic /demo/scan --hz 20

另起一个终端打开 rqt：
    talos rqt
"""

import argparse
import math
import time

import numpy as np

from talosos.messages import Header, LaserScan, Time
from talosos.runtime import Node, init, ok


def simulate_scan(t: float, n_rays: int) -> np.ndarray:
    """返回长度 n_rays 的 ranges[]，单位米。"""
    angles = np.linspace(-math.pi, math.pi, n_rays, endpoint=False,
                           dtype=np.float32)
    ranges = np.full(n_rays, 5.0, dtype=np.float32)   # 默认墙

    # 旋转的近物：角速度 0.5 Hz，宽 20°，距离 1.5 m
    moving_center = (0.5 * 2 * math.pi * t) % (2 * math.pi) - math.pi
    moving_width  = math.radians(20)
    d = ((angles - moving_center + math.pi) % (2 * math.pi)) - math.pi
    ranges[np.abs(d) < moving_width] = 1.5

    # 固定在 +Y（+π/2）方向的静态物，宽 15°，距离 2.5 m
    static_center = math.pi / 2
    d2 = ((angles - static_center + math.pi) % (2 * math.pi)) - math.pi
    ranges[np.abs(d2) < math.radians(15)] = 2.5

    return ranges


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--topic", default="/demo/scan")
    ap.add_argument("--hz", type=float, default=10.0)
    ap.add_argument("--rays", type=int, default=360)
    ap.add_argument("--frame-id", default="laser")
    args = ap.parse_args()

    init()
    node = Node.create("scan_pub")
    pub = node.advertise(args.topic, LaserScan)
    print(f"publishing {args.rays}-ray scan -> {pub.key} @ {args.hz} Hz")

    period = 1.0 / args.hz
    angle_inc = 2.0 * math.pi / args.rays
    t0 = time.monotonic()
    while ok():
        t = time.monotonic() - t0
        ranges = simulate_scan(t, args.rays).tolist()
        now = time.time_ns()
        msg = LaserScan(
            header=Header(frame_id=args.frame_id,
                            stamp=Time(sec=now // 1_000_000_000,
                                         nanosec=now % 1_000_000_000)),
            angle_min=-math.pi,
            angle_max=math.pi - angle_inc,   # 最后一束射线的实际角度
            angle_increment=angle_inc,
            time_increment=period / args.rays,
            scan_time=period,
            range_min=0.1,
            range_max=10.0,
            ranges=ranges,
            intensities=[],
        )
        pub.publish(msg)
        time.sleep(period)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
