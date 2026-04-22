#!/usr/bin/env python3
"""随机八叉树 Octomap 发布器 —— 用于 viz 3D 立方体体素面板回归。

用 Python 递归随机生成一棵八叉树：每个节点以概率 `--p-split` 细分；到最大
深度或未细分的节点以概率 `--p-occupied` 标占据。叶子体素连同边长打包发
出。

data 载荷格式（demo 自定义，`id = "talos_voxels_v1"`）：
  * 连续的 `float32(x) float32(y) float32(z) float32(size)`，每记录 16 字节
  * `x,y,z` 是体素中心坐标，`size` 是边长
  * viz 侧的 _OctomapLayer 识别到同样的 `id` 后用 GLMeshItem 批量画立方体

运行：
    python3 examples/python/random_octomap_publisher.py
    python3 examples/python/random_octomap_publisher.py --max-depth 4 --hz 1
    python3 examples/python/random_octomap_publisher.py --rebuild   # 每帧重生成

另起一个终端：
    talos viz     # 双击 /octomap 添加；每个体素是实心彩色立方体
"""

import argparse
import random
import time
from typing import List, Tuple

import numpy as np

from talosos.messages import Header, Octomap, Time as TMsg
from talosos.runtime import Node, init, ok


Voxel = Tuple[float, float, float, float]   # cx, cy, cz, size


def generate_octree(cx: float, cy: float, cz: float, size: float,
                    max_depth: int, p_split: float, p_occupied: float,
                    depth: int = 0) -> List[Voxel]:
    """递归地构造一组叶子体素。返回 (cx, cy, cz, size) 列表。"""
    if depth >= max_depth:
        if random.random() < p_occupied:
            return [(cx, cy, cz, size)]
        return []

    if random.random() < p_split:
        half = size * 0.5
        quarter = size * 0.25
        out: List[Voxel] = []
        for dx in (-quarter, quarter):
            for dy in (-quarter, quarter):
                for dz in (-quarter, quarter):
                    out.extend(generate_octree(cx + dx, cy + dy, cz + dz,
                                                 half, max_depth,
                                                 p_split, p_occupied,
                                                 depth + 1))
        return out

    if random.random() < p_occupied:
        return [(cx, cy, cz, size)]
    return []


def encode_voxels(voxels: List[Voxel]) -> bytes:
    if not voxels:
        return b""
    arr = np.asarray(voxels, dtype=np.float32)   # (N, 4)
    return arr.tobytes()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--topic", default="/octomap")
    ap.add_argument("--frame-id", default="map")
    ap.add_argument("--root-size", type=float, default=8.0,
                      help="根节点边长（米，默认 8）")
    ap.add_argument("--max-depth", type=int, default=4,
                      help="八叉树最大深度（默认 4 = 最小体素 ~0.5m）")
    ap.add_argument("--p-split", type=float, default=0.55,
                      help="节点细分概率（默认 0.55）")
    ap.add_argument("--p-occupied", type=float, default=0.35,
                      help="未细分节点被标记占据的概率（默认 0.35）")
    ap.add_argument("--hz", type=float, default=1.0)
    ap.add_argument("--rebuild", action="store_true",
                      help="每帧重新随机生成（看 viz 实时刷新）")
    ap.add_argument("--seed", type=int, default=None,
                      help="随机种子（可复现）")
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        np.random.seed(args.seed)

    res = args.root_size / (2 ** args.max_depth)
    print(f"root-size={args.root_size} m, max-depth={args.max_depth}"
          f"  → 最小体素边长 ≈ {res:.3f} m")

    init()
    node = Node.create("octomap_pub")
    pub = node.advertise(args.topic, Octomap)

    def build():
        t0 = time.monotonic()
        voxels = generate_octree(
            cx=0.0, cy=0.0, cz=args.root_size * 0.5,  # Z 从 0 起抬
            size=args.root_size,
            max_depth=args.max_depth,
            p_split=args.p_split, p_occupied=args.p_occupied)
        return voxels, time.monotonic() - t0

    voxels, dt = build()
    print(f"generated {len(voxels)} voxels in {dt*1000:.1f} ms"
          + ("  (rebuild every tick)" if args.rebuild else ""))

    period = 1.0 / args.hz
    while ok():
        if args.rebuild:
            voxels, _ = build()
        now = time.time_ns()
        payload = encode_voxels(voxels)
        msg = Octomap(
            header=Header(frame_id=args.frame_id,
                            stamp=TMsg(sec=now // 1_000_000_000,
                                         nanosec=now % 1_000_000_000)),
            binary=False,
            id="talos_voxels_v1",
            resolution=float(res),
            data=payload,
        )
        pub.publish(msg)
        time.sleep(period)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
