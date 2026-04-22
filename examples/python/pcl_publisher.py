#!/usr/bin/env python3
"""PCL 点云文件发布器 —— 支持 .pcd / .ply / .xyz / .csv / .txt。

典型用法：

    # 最简单：加载 .pcd，发到 /demo/cloud，默认 5 Hz
    python3 examples/python/pcl_publisher.py --file cloud.pcd

    # 加载 .ply，降采样到 1/4，10 Hz 发布
    python3 examples/python/pcl_publisher.py --file model.ply \
        --downsample 4 --hz 10

    # 绕 Z 轴慢速自转（方便在 rqt 里观察 3D 结构）
    python3 examples/python/pcl_publisher.py --file scan.pcd --spin-hz 0.1

    # 另起终端打开 rqt 3D 面板
    talos rqt

无外部依赖 —— 自带 .pcd / .ply 头解析器，只用 numpy。`binary_compressed`
的 .pcd 不支持，请先用 `pcl_convert` 转成 `binary`。
"""

import argparse
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

from talosos.messages import Header, PointCloud2, PointField, Time
from talosos.runtime import Node, init, ok


# ---------------------------------------------------------------------------
# File loaders
# ---------------------------------------------------------------------------

_PCD_TYPE_MAP = {"F": "f", "I": "i", "U": "u"}


def _pcd_header(f):
    """逐行读 PCD header，直到 DATA 行；返回 (header_dict, data_fmt)。"""
    header = {}
    while True:
        raw = f.readline()
        if not raw:
            raise ValueError("unexpected EOF in PCD header")
        line = raw.decode("ascii", errors="replace").strip()
        if not line or line.startswith("#"):
            continue
        key, _, val = line.partition(" ")
        key = key.upper()
        if key == "DATA":
            return header, val.strip().lower()
        header[key] = val.strip()


def load_pcd(path: Path) -> np.ndarray:
    with open(path, "rb") as f:
        header, fmt = _pcd_header(f)
        fields  = header["FIELDS"].split()
        sizes   = [int(s) for s in header["SIZE"].split()]
        types   = header["TYPE"].split()
        counts  = [int(c) for c in header["COUNT"].split()]
        n       = int(header["POINTS"])

        np_struct = []
        for fname, sz, ty, cnt in zip(fields, sizes, types, counts):
            np_ty = f"<{_PCD_TYPE_MAP[ty]}{sz}"
            np_struct.append((fname, np_ty) if cnt == 1 else (fname, np_ty, cnt))

        if fmt == "ascii":
            arr = np.loadtxt(f, dtype=np.float32)
            if arr.ndim == 1:
                arr = arr.reshape(n, -1)
            ix, iy, iz = fields.index("x"), fields.index("y"), fields.index("z")
            return np.ascontiguousarray(arr[:, [ix, iy, iz]].astype(np.float32))

        if fmt == "binary":
            raw = f.read()
            arr = np.frombuffer(raw, dtype=np.dtype(np_struct), count=n)
            return np.column_stack([arr["x"], arr["y"], arr["z"]]).astype(np.float32)

        if fmt == "binary_compressed":
            raise NotImplementedError(
                "binary_compressed PCD 不支持。请用 `pcl_convert -format 1 in.pcd out.pcd` "
                "转成 binary，或用 --file 指向 .ply")

        raise ValueError(f"unknown PCD DATA format: {fmt}")


_PLY_TYPE_MAP = {
    "float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8",
    "uchar": "<u1", "uint8": "<u1", "char": "<i1", "int8": "<i1",
    "ushort": "<u2", "uint16": "<u2", "short": "<i2", "int16": "<i2",
    "uint": "<u4", "uint32": "<u4", "int": "<i4", "int32": "<i4",
}


def load_ply(path: Path) -> np.ndarray:
    with open(path, "rb") as f:
        fmt = None
        n_vert = 0
        props = []
        in_vertex = False
        while True:
            raw = f.readline()
            if not raw:
                raise ValueError("unexpected EOF in PLY header")
            line = raw.decode("ascii").strip()
            if line == "end_header":
                break
            if line.startswith("format"):
                fmt = line.split()[1]
            elif line.startswith("element vertex"):
                n_vert = int(line.split()[2]); in_vertex = True
            elif line.startswith("element"):
                in_vertex = False
            elif line.startswith("property") and in_vertex:
                parts = line.split()
                if parts[1] == "list":
                    continue
                props.append((parts[2], _PLY_TYPE_MAP[parts[1]]))

        if fmt == "ascii":
            arr = np.loadtxt(f, max_rows=n_vert)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            idx = {p[0]: i for i, p in enumerate(props)}
            return np.column_stack([arr[:, idx["x"]], arr[:, idx["y"]],
                                      arr[:, idx["z"]]]).astype(np.float32)

        big = fmt.startswith("binary_big_endian")
        if big:
            props = [(nm, dt.replace("<", ">")) for nm, dt in props]
        arr = np.fromfile(f, dtype=np.dtype(props), count=n_vert)
        return np.column_stack([arr["x"].astype(np.float32),
                                  arr["y"].astype(np.float32),
                                  arr["z"].astype(np.float32)])


def load_xyz(path: Path) -> np.ndarray:
    data = np.loadtxt(str(path), comments="#")
    if data.ndim == 1:
        data = data.reshape(1, -1)
    if data.shape[1] < 3:
        raise ValueError(f"{path}: 需要至少 3 列，实际 {data.shape[1]}")
    return data[:, :3].astype(np.float32)


def load_cloud(path: Path) -> np.ndarray:
    ext = path.suffix.lower()
    if ext == ".pcd": return load_pcd(path)
    if ext == ".ply": return load_ply(path)
    if ext in (".xyz", ".txt", ".csv"): return load_xyz(path)
    raise ValueError(
        f"不支持的后缀 {ext}；接受 .pcd / .ply / .xyz / .txt / .csv")


# ---------------------------------------------------------------------------
# PointCloud2 构造
# ---------------------------------------------------------------------------

_FIELDS_XYZ = [
    PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
    PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
    PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
]


def make_cloud_msg(pts: np.ndarray, frame_id: str) -> PointCloud2:
    pts = np.ascontiguousarray(pts.astype("<f4"))
    data = pts.tobytes()
    now = time.time_ns()
    return PointCloud2(
        header=Header(frame_id=frame_id,
                        stamp=Time(sec=now // 1_000_000_000,
                                     nanosec=now % 1_000_000_000)),
        height=1,
        width=len(pts),
        fields=_FIELDS_XYZ,
        is_bigendian=False,
        point_step=12,
        row_step=12 * len(pts),
        data=data,
        is_dense=bool(np.isfinite(pts).all()),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def human(n: int) -> str:
    for unit in ("", "k", "M"):
        if n < 1000: return f"{n:.1f}{unit}"
        n /= 1000
    return f"{n:.1f}G"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Load a PCL/PLY/XYZ point cloud and publish as PointCloud2.")
    ap.add_argument("--file", "-f", required=True,
                      help=".pcd / .ply / .xyz / .txt / .csv")
    ap.add_argument("--topic", "-t", default="/demo/cloud")
    ap.add_argument("--frame-id", default="world")
    ap.add_argument("--hz", type=float, default=5.0)
    ap.add_argument("--downsample", type=int, default=1,
                      help="每 N 个点取一个（默认 1 = 全量）")
    ap.add_argument("--max-points", type=int, default=0,
                      help="均匀随机抽到最多 N 个点（0 = 不限制）")
    ap.add_argument("--recenter", action="store_true",
                      help="把点云重心平移到原点")
    ap.add_argument("--spin-hz", type=float, default=0.0,
                      help="非 0 时绕 Z 轴自转，便于观察 3D 结构")
    ap.add_argument("--once", action="store_true",
                      help="只发一次然后退出（用于检查编解码）")
    args = ap.parse_args()

    path = Path(args.file).expanduser()
    if not path.exists():
        print(f"error: {path} 不存在", file=sys.stderr); return 2

    t0 = time.monotonic()
    pts = load_cloud(path)
    t_load = time.monotonic() - t0
    print(f"loaded {human(len(pts))} pts from {path.name} in {t_load*1000:.0f} ms")

    if args.downsample > 1:
        pts = pts[::args.downsample]
        print(f"  downsample 1/{args.downsample} -> {human(len(pts))} pts")
    if args.max_points and len(pts) > args.max_points:
        idx = np.random.choice(len(pts), args.max_points, replace=False)
        pts = pts[idx]
        print(f"  subsample to {human(args.max_points)} pts")
    if args.recenter:
        pts = pts - pts.mean(axis=0, keepdims=True)
        print(f"  recentered to origin")
    bbox_min = pts.min(axis=0); bbox_max = pts.max(axis=0)
    print(f"  bbox  min=({bbox_min[0]:.2f},{bbox_min[1]:.2f},{bbox_min[2]:.2f})"
          f"  max=({bbox_max[0]:.2f},{bbox_max[1]:.2f},{bbox_max[2]:.2f})")

    init()
    node = Node.create("pcl_pub")
    pub = node.advertise(args.topic, PointCloud2)
    print(f"publishing -> {pub.key} @ {args.hz} Hz"
          + (f", spin {args.spin_hz} Hz" if args.spin_hz else ""))

    if args.once:
        pub.publish(make_cloud_msg(pts, args.frame_id))
        time.sleep(0.3)   # liveliness + CDR 发送
        return 0

    period = 1.0 / args.hz
    omega = 2.0 * math.pi * args.spin_hz
    t_start = time.monotonic()
    frames = 0
    while ok():
        if omega != 0.0:
            a = omega * (time.monotonic() - t_start)
            c, s = math.cos(a), math.sin(a)
            R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float32)
            out = pts @ R.T
        else:
            out = pts
        pub.publish(make_cloud_msg(out, args.frame_id))
        frames += 1
        time.sleep(period)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
