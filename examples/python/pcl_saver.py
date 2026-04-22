#!/usr/bin/env python3
"""PointCloud2 订阅并保存为 .pcd / .ply 文件 —— `pcl_publisher.py` 的反向。

从指定话题订阅 PointCloud2，按文件后缀自动选 PCD / PLY 格式、binary 或
ascii 写盘。默认只存第一帧然后退出；`--count N` 连续存 N 帧（文件名带编号），
`--continuous` 持续覆写同一文件（用于实时落盘）。

典型用法：

    # 单帧
    python3 examples/python/pcl_saver.py --topic /demo/cloud --out one.pcd

    # 存 20 帧：one_000.pcd one_001.pcd …
    python3 examples/python/pcl_saver.py -t /demo/cloud -o one.pcd --count 20

    # 持续覆写（最新帧始终在 live.ply）
    python3 examples/python/pcl_saver.py -t /demo/cloud -o live.ply --continuous

    # 指定 ascii（默认是 binary，体积最小）
    python3 examples/python/pcl_saver.py -t /demo/cloud -o text.pcd --ascii

无外部依赖，只用 numpy + talosos。
"""

import argparse
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np

from talosos.messages import PointCloud2
from talosos.runtime import Node, init, ok


# ---------------------------------------------------------------------------
# PointCloud2 → numpy
# ---------------------------------------------------------------------------

def pointcloud2_to_xyz(msg: PointCloud2) -> Optional[np.ndarray]:
    """提取 (N, 3) float32 xyz。无 x/y/z 字段或数据为空则返回 None。"""
    fields = {f.name: f for f in msg.fields}
    if not all(k in fields for k in ("x", "y", "z")):
        return None
    data = bytes(msg.data)
    n = len(data) // max(1, msg.point_step)
    if n == 0:
        return None
    buf = np.frombuffer(data, dtype=np.uint8).reshape(n, msg.point_step)

    def viewf(name):
        off = fields[name].offset
        return np.frombuffer(buf[:, off:off + 4].tobytes(), dtype=np.float32)

    xyz = np.column_stack([viewf("x"), viewf("y"), viewf("z")])
    return xyz[np.isfinite(xyz).all(axis=1)]


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_pcd(path: Path, xyz: np.ndarray, ascii_mode: bool = False) -> None:
    n = len(xyz)
    fmt = "ascii" if ascii_mode else "binary"
    header = (
        "# .PCD v0.7 - written by talosos/pcl_saver.py\n"
        "VERSION 0.7\n"
        "FIELDS x y z\n"
        "SIZE 4 4 4\n"
        "TYPE F F F\n"
        "COUNT 1 1 1\n"
        f"WIDTH {n}\n"
        "HEIGHT 1\n"
        "VIEWPOINT 0 0 0 1 0 0 0\n"
        f"POINTS {n}\n"
        f"DATA {fmt}\n"
    )
    with open(path, "wb") as f:
        f.write(header.encode("ascii"))
        if ascii_mode:
            np.savetxt(f, xyz.astype(np.float32), fmt="%.6f")
        else:
            f.write(np.ascontiguousarray(xyz.astype("<f4")).tobytes())


def write_ply(path: Path, xyz: np.ndarray, ascii_mode: bool = False) -> None:
    n = len(xyz)
    fmt = "ascii 1.0" if ascii_mode else "binary_little_endian 1.0"
    header = (
        "ply\n"
        f"format {fmt}\n"
        "comment written by talosos/pcl_saver.py\n"
        f"element vertex {n}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "end_header\n"
    )
    with open(path, "wb") as f:
        f.write(header.encode("ascii"))
        if ascii_mode:
            np.savetxt(f, xyz.astype(np.float32), fmt="%.6f")
        else:
            f.write(np.ascontiguousarray(xyz.astype("<f4")).tobytes())


def save(path: Path, xyz: np.ndarray, ascii_mode: bool) -> None:
    ext = path.suffix.lower()
    if ext == ".pcd":   write_pcd(path, xyz, ascii_mode)
    elif ext == ".ply": write_ply(path, xyz, ascii_mode)
    else:
        raise ValueError(f"不支持的后缀 {ext}；用 .pcd 或 .ply")


def human(n: int) -> str:
    for u in ("", "k", "M"):
        if n < 1000: return f"{n:.1f}{u}"
        n /= 1000
    return f"{n:.1f}G"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--topic", "-t", required=True, help="PointCloud2 话题路径")
    ap.add_argument("--out", "-o", required=True,
                      help="输出文件（.pcd 或 .ply）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--once", action="store_true",
                    help="存一帧立即退出（默认行为）")
    g.add_argument("--count", type=int, default=None,
                    help="存 N 帧，文件名自动加 _000/_001/... 后缀")
    g.add_argument("--continuous", action="store_true",
                    help="持续覆写同一文件（最新帧总是 --out）")
    ap.add_argument("--ascii", action="store_true",
                      help="ASCII 模式（体积大 5-7 倍，默认 binary）")
    ap.add_argument("--timeout", type=float, default=30.0,
                      help="单帧模式下的超时秒数（默认 30）")
    args = ap.parse_args()

    out = Path(args.out).expanduser()
    if out.suffix.lower() not in (".pcd", ".ply"):
        print(f"error: 输出后缀必须是 .pcd 或 .ply，got {out.suffix}",
              file=sys.stderr)
        return 2

    init()
    node = Node.create("pcl_saver")

    got_event = threading.Event()
    lock = threading.Lock()
    state = {"n_frames": 0}

    target_count = (args.count if args.count is not None
                      else (None if args.continuous else 1))

    def on_msg(msg: PointCloud2) -> None:
        xyz = pointcloud2_to_xyz(msg)
        if xyz is None:
            print("warning: 跳过一帧 —— 缺少 x/y/z 字段或数据为空",
                  file=sys.stderr)
            return
        with lock:
            idx = state["n_frames"]
            if args.continuous:
                path = out
            elif args.count is not None:
                stem = out.stem
                suffix = out.suffix
                path = out.with_name(f"{stem}_{idx:03d}{suffix}")
            else:
                path = out
            try:
                save(path, xyz, args.ascii)
            except Exception as ex:
                print(f"error: 写 {path}: {ex}", file=sys.stderr)
                got_event.set()
                return
            state["n_frames"] += 1
            print(f"[{idx+1}{('/'+str(target_count)) if target_count else ''}] "
                  f"wrote {human(len(xyz))} pts -> {path}")
            if target_count is not None and state["n_frames"] >= target_count:
                got_event.set()

    sub = node.subscribe(args.topic, PointCloud2, on_msg)
    mode = ("continuous" if args.continuous
            else f"count={args.count}" if args.count is not None
            else "once")
    print(f"subscribed {args.topic}  →  {out}  ({mode},"
          f" {'ascii' if args.ascii else 'binary'})")

    if args.continuous:
        # 持续模式：等 Ctrl+C
        try:
            while ok():
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
    else:
        # 等待首帧 / N 帧
        t0 = time.monotonic()
        while ok() and not got_event.is_set():
            if time.monotonic() - t0 > args.timeout:
                print(f"error: {args.timeout}s 内没收到 {args.topic} 的消息，"
                      f"确认 publisher 在跑", file=sys.stderr)
                return 1
            time.sleep(0.05)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
