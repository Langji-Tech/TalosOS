#!/usr/bin/env python3
"""随机 OccupancyGrid 地图发布器 —— 用于 viz XOY 栅格面板回归。

发布到 `/map`（默认），匹配 `talos viz` 的 OccupancyGrid 启发式，在 rqt/viz
里自动识别为 OccupancyGrid 图层。

数据约定（与 ROS 一致）：
  * `-1` = 未知（viz 显示为深蓝灰半透）
  * `0`  = 自由空间（近白）
  * `1..100` = 占据概率（值越大越深）

运行：
    python3 examples/python/random_gridmap_publisher.py
    python3 examples/python/random_gridmap_publisher.py --size 200 --res 0.05
    python3 examples/python/random_gridmap_publisher.py --walls --animate

另起一个终端：
    talos viz      # 双击 /map 添加到 3D 场景；贴图铺在 XOY 平面
"""

import argparse
import math
import random
import time

import numpy as np

from talosos.messages import Header, MapMetaData, OccupancyGrid, Point, Pose, Time as TMsg
from talosos.runtime import Node, init, ok


def make_random_grid(w: int, h: int,
                     obstacle_prob: float = 0.03,
                     unknown_prob: float = 0.02,
                     draw_walls: bool = True) -> np.ndarray:
    """返回 HxW int8 矩阵。默认：稀疏障碍物 + 可选四周墙 + 少量未知区域。"""
    grid = np.zeros((h, w), dtype=np.int8)

    # 随机散布的墙块（3×3~5×5 小团）
    n_blobs = max(1, int(w * h * obstacle_prob / 12))
    for _ in range(n_blobs):
        cx = random.randint(3, w - 4)
        cy = random.randint(3, h - 4)
        rx = random.randint(1, 3); ry = random.randint(1, 3)
        grid[max(0, cy - ry):cy + ry + 1,
             max(0, cx - rx):cx + rx + 1] = 100

    # 未知区域（模拟未扫描）
    um = np.random.rand(h, w) < unknown_prob
    grid[um] = -1

    if draw_walls:
        grid[0, :] = 100; grid[-1, :] = 100
        grid[:, 0] = 100; grid[:, -1] = 100

    # 几条随机直线作为走廊墙（一半障碍，偶尔穿断）
    for _ in range(random.randint(1, 3)):
        if random.random() < 0.5:
            y = random.randint(h // 4, 3 * h // 4)
            x0 = random.randint(0, w // 3)
            x1 = random.randint(2 * w // 3, w - 1)
            grid[y, x0:x1] = 100
            # 随机开门
            gate = random.randint(x0 + 1, x1 - 2)
            grid[y, gate:gate + 2] = 0
        else:
            x = random.randint(w // 4, 3 * w // 4)
            y0 = random.randint(0, h // 3)
            y1 = random.randint(2 * h // 3, h - 1)
            grid[y0:y1, x] = 100
            gate = random.randint(y0 + 1, y1 - 2)
            grid[gate:gate + 2, x] = 0

    return grid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--topic", default="/map")
    ap.add_argument("--frame-id", default="map")
    ap.add_argument("--size", type=int, default=100,
                      help="正方形栅格边长（cell 数，默认 100）")
    ap.add_argument("--res", type=float, default=0.1,
                      help="cell 分辨率（米，默认 0.1）")
    ap.add_argument("--hz", type=float, default=1.0,
                      help="发布频率（默认 1）")
    ap.add_argument("--obstacle-prob", type=float, default=0.03)
    ap.add_argument("--unknown-prob",  type=float, default=0.02)
    ap.add_argument("--walls", action="store_true", help="画四周墙")
    ap.add_argument("--animate", action="store_true",
                      help="每帧重新随机生成（便于看 viz 实时刷新）")
    ap.add_argument("--origin", nargs=2, type=float, default=None,
                      help="OccupancyGrid 左下角世界坐标（米，默认以中心对齐原点）")
    args = ap.parse_args()

    if args.origin is None:
        ox = -0.5 * args.size * args.res
        oy = -0.5 * args.size * args.res
    else:
        ox, oy = args.origin

    init()
    node = Node.create("gridmap_pub")
    pub = node.advertise(args.topic, OccupancyGrid)
    print(f"publishing OccupancyGrid -> {pub.key} @ {args.hz} Hz  "
          f"size {args.size}x{args.size}  res {args.res} m  "
          f"origin ({ox:.2f}, {oy:.2f})  animate={args.animate}")

    period = 1.0 / args.hz
    grid = make_random_grid(args.size, args.size,
                              args.obstacle_prob, args.unknown_prob,
                              args.walls)

    while ok():
        if args.animate:
            grid = make_random_grid(args.size, args.size,
                                      args.obstacle_prob, args.unknown_prob,
                                      args.walls)
        now = time.time_ns()
        msg = OccupancyGrid(
            header=Header(frame_id=args.frame_id,
                            stamp=TMsg(sec=now // 1_000_000_000,
                                         nanosec=now % 1_000_000_000)),
            info=MapMetaData(
                map_load_time=TMsg(sec=now // 1_000_000_000,
                                    nanosec=now % 1_000_000_000),
                resolution=float(args.res),
                width=int(args.size), height=int(args.size),
                origin=Pose(position=Point(x=float(ox), y=float(oy), z=0.0))),
            data=bytes(grid.astype(np.int8).tobytes()),
        )
        pub.publish(msg)
        time.sleep(period)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
