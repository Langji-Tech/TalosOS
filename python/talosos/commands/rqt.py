"""`talos rqt` — unified PyQt5 console.

Features:
  * 自动发现所有 /topic（调 `talos topic list`，每 2 秒刷新一次）
  * 根据 topic 名自动推测消息类型，可手动覆盖
  * 勾选 → 点 + 添加为可视化面板；也可双击话题行快速添加
  * 面板布局：
      - 图像类型 (Image / CompressedImage) 在顶部横向并排
      - 其它类型（Imu / Scan / Pose / Scalar / TF…）在下方网格，matplotlib Qt 后端
  * 每个面板独立的 talosos_tool topic-echo 订阅后台线程
  * 关闭面板 / 关闭窗口 → 所有订阅后端干净退出
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

import argparse
import io
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Topic type heuristic — 命中第一个匹配的正则即推荐
# ---------------------------------------------------------------------------

_TYPE_HEURISTICS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"/image/compressed|/compressed|_compressed"), "CompressedImage"),
    (re.compile(r"/image(_raw|_color|_mono|$)"),               "Image"),
    (re.compile(r"/image"),                                    "CompressedImage"),
    (re.compile(r"/scan"),                                     "LaserScan"),
    (re.compile(r"/points|/cloud"),                            "PointCloud2"),
    (re.compile(r"/octomap_full|/octomap_binary|/octomap"),    "Octomap"),
    (re.compile(r"/map(_updates|_server)?(/|$)|/grid|/occupancy"), "OccupancyGrid"),
    (re.compile(r"/marker(s)?(_array)?"),                      "MarkerArray"),
    (re.compile(r"/tf(_static)?($|/)"),                        "TFMessage"),
    (re.compile(r"/odom|/odometry"),                           "PoseStamped"),
    (re.compile(r"/pose"),                                     "PoseStamped"),
    (re.compile(r"/cmd_vel|/velocity|/twist"),                 "TwistStamped"),
    (re.compile(r"/imu"),                                      "Imu"),
    (re.compile(r"/voltage|/current|/temperature|/battery"),   "Float32"),
    (re.compile(r"/range|/distance|/humidity|/pressure"),      "Float32"),
]

_ALL_TYPES = [
    "CompressedImage", "Image", "LaserScan", "PointCloud2",
    "OccupancyGrid", "Octomap", "OctomapWithPose",
    "MarkerArray", "Marker", "TFMessage",
    "PoseStamped", "TransformStamped", "TwistStamped", "Imu",
    "Float64", "Float32", "Int64", "Int32", "String",
]

# 类型标签的主色，便于一眼区分
_TYPE_COLOR = {
    "CompressedImage": "#ffd56e", "Image":          "#ffd56e",
    "LaserScan":       "#6ee2ff",
    "PointCloud2":     "#6ee2ff",
    "OccupancyGrid":   "#ffb380", "Octomap":        "#ff9e6e",
    "OctomapWithPose": "#ff9e6e",
    "MarkerArray":     "#a0f0ff", "Marker":         "#a0f0ff",
    "TFMessage":       "#c8a0ff",
    "PoseStamped":     "#ff6e9e", "TransformStamped":"#ff6e9e",
    "TwistStamped":    "#ff6e9e",
    "Imu":             "#9ee7ff",
    "Float64":         "#8ef0b0", "Float32":        "#8ef0b0",
    "Int64":           "#8ef0b0", "Int32":          "#8ef0b0",
    "String":          "#eeeeee",
}


def guess_type(topic: str) -> str:
    for pat, tname in _TYPE_HEURISTICS:
        if pat.search(topic):
            return tname
    return "Float64"  # 保守默认


# ---------------------------------------------------------------------------
# Topic discovery — wraps `talos topic list`
# ---------------------------------------------------------------------------

def _talos_bin() -> str:
    exe = shutil.which("talos")
    if exe:
        return exe
    here = os.path.dirname(os.path.realpath(sys.argv[0]))
    cand = os.path.join(here, "talos")
    if os.path.isfile(cand):
        return cand
    return "talos"


def list_topics(timeout_ms: int = 400) -> List[Tuple[str, str]]:
    """`talos topic list --verbose` 解析为 [(topic, broadcast_type), ...]。

    broadcast_type 空字符串表示：发布端没广播类型（老版本 / 非 TalosOS publisher）。
    """
    try:
        proc = subprocess.run(
            [_talos_bin(), "topic", "list", "--verbose",
             "--timeout-ms", str(timeout_ms)],
            capture_output=True, text=True, timeout=3.0)
    except Exception:
        return []
    rows: Dict[str, str] = {}
    for line in proc.stdout.splitlines():
        line = line.rstrip()
        if not line or line.startswith("("):
            continue
        parts = line.split("\t")
        topic = parts[0]
        tname = parts[1] if len(parts) >= 2 and parts[1] not in ("-", "") else ""
        rows.setdefault(topic, tname)
    return sorted(rows.items())


# ---------------------------------------------------------------------------
# Per-panel background sampler
# ---------------------------------------------------------------------------

@dataclass
class _Latest:
    msg: Any = None
    seq: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


class TopicSampler:
    """后台订阅，最新消息存在锁下。

    优先走 **进程内 zenoh 订阅**（`talosos.runtime`，pybind11）——
    无 pipe、无 hex 编码、无子进程，从根本上避免帧在 64KB 内核管道里
    被阻塞丢失。当 runtime 扩展不可用（比如裸装没编 pybind11）时，回退
    到老的 `talosos_tool topic-echo` 子进程路径。
    """

    # 整个 rqt 会话共享一个 Node——每个 panel 新建一个 zenoh Session 太贵。
    _shared_node = None
    _node_lock = threading.Lock()
    _runtime_available: Optional[bool] = None

    def __init__(self, topic: str, type_name: str):
        self.topic = topic
        self.type_name = type_name
        self._stop = threading.Event()
        self._latest = _Latest()
        self._sub = None        # fast path (direct subscribe)
        self._thread = None     # slow path (subprocess)

    @classmethod
    def _have_runtime(cls) -> bool:
        if cls._runtime_available is None:
            try:
                from ..runtime import Node  # noqa: F401
                cls._runtime_available = True
            except Exception:
                cls._runtime_available = False
        return cls._runtime_available

    @classmethod
    def _node(cls):
        with cls._node_lock:
            if cls._shared_node is None:
                from ..runtime import Node, init
                try:
                    init()
                except Exception:
                    pass
                cls._shared_node = Node.create("talos_rqt_viewer")
        return cls._shared_node

    def start(self) -> None:
        from ..messages import REGISTRY
        type_cls = REGISTRY.get(self.type_name)

        # 直连优先：zenoh 回调 → 直接塞进最新值。无 pipe。
        if type_cls is not None and self._have_runtime():
            node = self._node()

            def on_msg(msg, _ts=self):
                if _ts._stop.is_set():
                    return
                with _ts._latest.lock:
                    _ts._latest.msg = msg
                    _ts._latest.seq += 1

            try:
                self._sub = node.subscribe(self.topic, type_cls, on_msg)
                return
            except Exception:
                pass  # 落回子进程路径

        # 回退：子进程 topic-echo
        from ..echo_stream import iter_samples
        from ..messages import decode, resolve_type
        try:
            resolve_type(self.type_name)
        except KeyError:
            return  # 不认识的类型就算了

        def run():
            try:
                for s in iter_samples(self.topic):
                    if self._stop.is_set():
                        return
                    try:
                        m = decode(self.type_name, s.payload)
                    except Exception:
                        continue
                    with self._latest.lock:
                        self._latest.msg = m
                        self._latest.seq += 1
            except Exception:
                pass

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        # Direct subscription stays registered on the shared Node until the
        # process exits — our _stop flag short-circuits callbacks, so no
        # further CPU cost.

    def latest(self) -> Tuple[Any, int]:
        with self._latest.lock:
            return self._latest.msg, self._latest.seq


# ---------------------------------------------------------------------------
# Visualization panels
# ---------------------------------------------------------------------------

def _qt():
    try:
        from PyQt5 import QtCore, QtGui, QtWidgets
        return QtCore, QtGui, QtWidgets
    except ImportError as ex:
        raise SystemExit(f"error: PyQt5 required for `talos rqt`: {ex}")


def _mpl():
    import matplotlib
    matplotlib.use("Qt5Agg")
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FC
    from matplotlib.figure import Figure
    return FC, Figure


# --- GL stack (pyqtgraph + PyOpenGL). Optional；没装时自动回退到 matplotlib。
try:
    import pyqtgraph as _pg  # noqa: F401
    import pyqtgraph.opengl as _gl
    _HAS_GL = True
except Exception:
    _gl = None
    _HAS_GL = False


#: 渲染节拍，毫秒。上限 30 FPS —— 再高也用不到，只会白烧 CPU。
#: 数据到达的实际帧率可以高于这个（sampler 在后台线程永远取最新），
#: 但 UI 绘制每 1/30 秒最多更新一次。
RENDER_TICK_MS = 33     # 1000/30 ≈ 33.3 → 33 ms ≈ 30.3 FPS


def _jet_colors(values, vmin=None, vmax=None):
    """v in [vmin, vmax] → RGBA (N,4) float32；用于点云 / 激光按距离上色。"""
    import numpy as np
    v = np.asarray(values, dtype=np.float32)
    if vmin is None: vmin = float(v.min()) if v.size else 0.0
    if vmax is None: vmax = float(v.max()) if v.size else 1.0
    rng = vmax - vmin if vmax > vmin else 1.0
    t = np.clip((v - vmin) / rng, 0.0, 1.0)
    r = np.clip(1.5 - 4 * np.abs(t - 0.75), 0, 1)
    g = np.clip(1.5 - 4 * np.abs(t - 0.50), 0, 1)
    b = np.clip(1.5 - 4 * np.abs(t - 0.25), 0, 1)
    a = np.ones_like(r)
    return np.column_stack([r, g, b, a]).astype(np.float32)


def _turbo_colors(values, vmin=None, vmax=None):
    """Google Turbo colormap（紫 → 蓝 → 青 → 绿 → 黄 → 红）多项式近似。
    比 jet 亮度均匀、色相连续，在深色背景上对比度明显更好 —— RViz 默认
    也用 turbo。"""
    import numpy as np
    v = np.asarray(values, dtype=np.float32)
    if vmin is None: vmin = float(v.min()) if v.size else 0.0
    if vmax is None: vmax = float(v.max()) if v.size else 1.0
    rng = vmax - vmin if vmax > vmin else 1.0
    t = np.clip((v - vmin) / rng, 0.0, 1.0)
    r = (0.13572138 + 4.61539260 * t - 42.66032258 * t**2
         + 132.13108234 * t**3 - 152.94239396 * t**4 + 59.28637943 * t**5)
    g = (0.09140261 + 2.19418839 * t + 4.84296658 * t**2
         - 14.18503333 * t**3 + 4.27729857 * t**4 + 2.82956604 * t**5)
    b = (0.10667330 + 12.64194608 * t - 60.58204836 * t**2
         + 110.36276771 * t**3 - 89.90310912 * t**4 + 27.34824973 * t**5)
    r = np.clip(r, 0, 1); g = np.clip(g, 0, 1); b = np.clip(b, 0, 1)
    a = np.ones_like(r)
    return np.column_stack([r, g, b, a]).astype(np.float32)


class BasePanel:
    """各 panel 的共同基类（非 QWidget — 持有一个 QWidget 作 `widget`）。"""

    type_names: Tuple[str, ...] = ()

    def __init__(self, topic: str, type_name: str):
        self.topic = topic
        self.type_name = type_name
        self.sampler = TopicSampler(topic, type_name)
        self.sampler.start()
        self._last_seq = -1

    def close_sampler(self) -> None:
        self.sampler.stop()

    def tick(self) -> None:
        raise NotImplementedError


# --- Image (CompressedImage + Image) ---

class ImagePanel(BasePanel):
    type_names = ("CompressedImage", "Image")

    def __init__(self, topic: str, type_name: str):
        super().__init__(topic, type_name)
        QtCore, QtGui, QtWidgets = _qt()
        self.widget = QtWidgets.QLabel()
        self.widget.setAlignment(QtCore.Qt.AlignCenter)
        self.widget.setMinimumSize(120, 80)
        self.widget.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Preferred)
        self.widget.setStyleSheet("background:#0b0b10; color:#7fdcff;")
        self.widget.setText(f"等待 {topic} …")
        self._fit_size: Tuple[int, int] = (0, 0)

    def _qimage(self, msg):
        from PyQt5 import QtGui
        data = bytes(msg.data)
        if self.type_name == "CompressedImage":
            img = QtGui.QImage()
            img.loadFromData(data)
            return img
        enc = msg.encoding.lower()
        if enc in ("mono8", "8uc1"):
            fmt = QtGui.QImage.Format_Grayscale8
            return QtGui.QImage(data, msg.width, msg.height,
                                 msg.step, fmt).copy()
        if enc in ("rgb8", "bgr8", "8uc3"):
            fmt = QtGui.QImage.Format_RGB888
            img = QtGui.QImage(data, msg.width, msg.height,
                                 msg.step, fmt).copy()
            if enc == "bgr8":
                img = img.rgbSwapped()
            return img
        if enc in ("rgba8", "bgra8", "8uc4"):
            fmt = QtGui.QImage.Format_RGBA8888
            img = QtGui.QImage(data, msg.width, msg.height,
                                 msg.step, fmt).copy()
            if enc == "bgra8":
                img = img.rgbSwapped()
            return img
        return None

    def tick(self) -> None:
        from PyQt5 import QtCore, QtGui
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq:
            return
        self._last_seq = seq
        qimg = self._qimage(msg)
        if qimg is None or qimg.isNull():
            return

        # Fit image into the CURRENT widget rect keeping aspect, then shrink
        # the label to exactly the scaled pixmap size — no dead bars around
        # the image. The containing QGroupBox adapts to the label's new size
        # in the horizontal row layout.
        avail = self.widget.size()
        if avail.width() < 40 or avail.height() < 40:
            # During first paint widget may not have a real size yet; fall
            # back to the image's native size capped to a reasonable panel.
            target_w = min(qimg.width(), 480)
            target_h = int(qimg.height() * target_w / max(1, qimg.width()))
        else:
            pm_tmp = QtGui.QPixmap(qimg.size())  # unused; just for ratio calc
            target_w, target_h = avail.width(), avail.height()

        # FastTransformation（最近邻）~10× 比 SmoothTransformation 快，对 25–30Hz
        # 视频流完全够用；Smooth 在 1080p 下会把 Qt 主线程打满，外观就是"卡顿"。
        pm = QtGui.QPixmap.fromImage(qimg).scaled(
            target_w, target_h,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.FastTransformation)
        self.widget.setPixmap(pm)
        # 只在目标尺寸真的大幅变化时才重设 min/max。每帧调这俩会让 Qt layout
        # 反复重算；两图并排时更会互相拉扯，直接导致卡顿。
        pw, ph = pm.width(), pm.height()
        fw, fh = self._fit_size
        if abs(pw - fw) > 8 or abs(ph - fh) > 8:
            self._fit_size = (pw, ph)
            self.widget.setMinimumSize(pw, ph)
            self.widget.setMaximumSize(pw * 4, ph * 4)
        try:
            now_ns = time.time_ns()
            sent_ns = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
            lat_ms = (now_ns - sent_ns) / 1e6
            self.widget.setToolTip(
                f"{self.topic}\n{qimg.width()}×{qimg.height()}\n"
                f"lat {lat_ms:.1f} ms · seq {seq}")
        except Exception:
            pass


# --- Matplotlib-based panels ---

class _MplPanel(BasePanel):
    def __init__(self, topic: str, type_name: str):
        super().__init__(topic, type_name)
        FC, Figure = _mpl()
        self.fig = Figure(figsize=(3.2, 2.4), facecolor="#0b0b10")
        self.canvas = FC(self.fig)
        self.widget = self.canvas
        self._setup_axes()

    def _setup_axes(self) -> None:
        raise NotImplementedError

    def _style_axes(self, ax, title=None):
        ax.set_facecolor("#0b0b10")
        for s in ax.spines.values(): s.set_color("#3a4b6b")
        ax.tick_params(colors="#9ee7ff", labelsize=7)
        if title is not None:
            ax.set_title(title, color="#e5f4ff", fontsize=8, loc="left")


class ScalarPanel(_MplPanel):
    """Float/Int 时序曲线。"""
    type_names = ("Float64", "Float32", "Int64", "Int32", "String")

    def __init__(self, topic, type_name, history=300):
        self._history = history
        super().__init__(topic, type_name)
        self._xs: deque = deque(maxlen=history)
        self._ys: deque = deque(maxlen=history)

    def _setup_axes(self) -> None:
        self.ax = self.fig.add_subplot(111)
        self._style_axes(self.ax, self.topic)
        self.line, = self.ax.plot([], [], color="#6ee2ff")

    def tick(self) -> None:
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq:
            return
        self._last_seq = seq
        try:
            v = float(msg.data)
        except Exception:
            return
        self._xs.append(seq); self._ys.append(v)
        self.line.set_data(list(self._xs), list(self._ys))
        self.ax.relim(); self.ax.autoscale_view()
        self.canvas.draw_idle()


class ImuPanel(_MplPanel):
    """3 子图：linear accel / angular vel / orientation.w。"""
    type_names = ("Imu",)

    def __init__(self, topic, type_name, history=300):
        self._history = history
        super().__init__(topic, type_name)
        self._seq: deque = deque(maxlen=history)
        self._buf: Dict[str, deque] = {k: deque(maxlen=history) for k in
            ("ax", "ay", "az", "gx", "gy", "gz", "w")}

    def _setup_axes(self) -> None:
        self.axes = self.fig.subplots(3, 1, sharex=True)
        titles = [f"{self.topic} linear accel", "angular vel", "orient.w"]
        for ax, t in zip(self.axes, titles):
            self._style_axes(ax, t)
        colors_xyz = ("#ff6e9e", "#6ee2ff", "#ffd56e")
        self.lines: Dict[str, Any] = {}
        for k, c in zip(("ax", "ay", "az"), colors_xyz):
            self.lines[k], = self.axes[0].plot([], [], color=c, linewidth=1)
        for k, c in zip(("gx", "gy", "gz"), colors_xyz):
            self.lines[k], = self.axes[1].plot([], [], color=c, linewidth=1)
        self.lines["w"], = self.axes[2].plot([], [], color="#a0f0ff", linewidth=1)
        self.fig.tight_layout()

    def tick(self) -> None:
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq:
            return
        self._last_seq = seq
        self._seq.append(seq)
        self._buf["ax"].append(msg.linear_acceleration.x)
        self._buf["ay"].append(msg.linear_acceleration.y)
        self._buf["az"].append(msg.linear_acceleration.z)
        self._buf["gx"].append(msg.angular_velocity.x)
        self._buf["gy"].append(msg.angular_velocity.y)
        self._buf["gz"].append(msg.angular_velocity.z)
        self._buf["w"].append(msg.orientation.w)
        xs = list(self._seq)
        for k, line in self.lines.items():
            line.set_data(xs, list(self._buf[k]))
        for a in self.axes:
            a.relim(); a.autoscale_view()
        self.canvas.draw_idle()


class TwistPanel(_MplPanel):
    type_names = ("TwistStamped",)

    def __init__(self, topic, type_name, history=300):
        self._history = history
        super().__init__(topic, type_name)
        self._seq: deque = deque(maxlen=history)
        self._buf: Dict[str, deque] = {k: deque(maxlen=history) for k in
            ("lx", "ly", "lz", "wx", "wy", "wz")}

    def _setup_axes(self) -> None:
        self.axes = self.fig.subplots(2, 1, sharex=True)
        titles = [f"{self.topic} linear", "angular"]
        for ax, t in zip(self.axes, titles):
            self._style_axes(ax, t)
        self.lines: Dict[str, Any] = {}
        colors = ("#ff6e9e", "#6ee2ff", "#ffd56e")
        for k, c in zip(("lx", "ly", "lz"), colors):
            self.lines[k], = self.axes[0].plot([], [], color=c, linewidth=1)
        for k, c in zip(("wx", "wy", "wz"), colors):
            self.lines[k], = self.axes[1].plot([], [], color=c, linewidth=1)
        self.fig.tight_layout()

    def tick(self) -> None:
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq:
            return
        self._last_seq = seq
        t = msg.twist
        self._seq.append(seq)
        self._buf["lx"].append(t.linear.x); self._buf["ly"].append(t.linear.y); self._buf["lz"].append(t.linear.z)
        self._buf["wx"].append(t.angular.x); self._buf["wy"].append(t.angular.y); self._buf["wz"].append(t.angular.z)
        xs = list(self._seq)
        for k, line in self.lines.items():
            line.set_data(xs, list(self._buf[k]))
        for a in self.axes:
            a.relim(); a.autoscale_view()
        self.canvas.draw_idle()


class ScanPanel(_MplPanel):
    type_names = ("LaserScan",)

    def _setup_axes(self) -> None:
        self.ax = self.fig.add_subplot(111, projection="polar")
        self._style_axes(self.ax, self.topic)
        self.sc = self.ax.scatter([], [], s=3, c="#6ee2ff")

    def tick(self) -> None:
        import numpy as np
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq or not msg.ranges:
            return
        self._last_seq = seq
        n = len(msg.ranges)
        angles = np.linspace(msg.angle_min,
                               msg.angle_min + msg.angle_increment * (n - 1), n)
        ranges = np.array(msg.ranges, dtype=float)
        ranges = np.where(np.isfinite(ranges), ranges, 0.0)
        self.sc.set_offsets(np.column_stack([angles, ranges]))
        self.ax.set_ylim(0, max(msg.range_max, float(ranges.max() + 0.1)))
        self.canvas.draw_idle()


class CloudPanel(_MplPanel):
    type_names = ("PointCloud2",)

    def _setup_axes(self) -> None:
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.ax.set_title(self.topic, color="#e5f4ff", fontsize=8)
        self.sc = self.ax.scatter([], [], [], s=1, c="#6ee2ff")

    def tick(self) -> None:
        import numpy as np
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq:
            return
        self._last_seq = seq
        fields = {f.name: f for f in msg.fields}
        if not all(k in fields for k in ("x", "y", "z")): return
        data = bytes(msg.data)
        n = len(data) // max(1, msg.point_step)
        if n == 0: return
        buf = np.frombuffer(data, dtype=np.uint8).reshape(n, msg.point_step)
        def view(name):
            off = fields[name].offset
            return np.frombuffer(buf[:, off:off + 4].tobytes(), dtype=np.float32)
        try:
            xyz = np.column_stack([view("x"), view("y"), view("z")])
        except Exception:
            return
        if len(xyz) > 5000:
            xyz = xyz[np.random.choice(len(xyz), 5000, replace=False)]
        xyz = xyz[np.isfinite(xyz).all(axis=1)]
        if len(xyz) == 0: return
        self.sc._offsets3d = (xyz[:, 0], xyz[:, 1], xyz[:, 2])
        lo = xyz.min(axis=0); hi = xyz.max(axis=0)
        self.ax.set_xlim(lo[0], hi[0]); self.ax.set_ylim(lo[1], hi[1])
        self.ax.set_zlim(lo[2], hi[2])
        self.canvas.draw_idle()


class PosePanel(_MplPanel):
    type_names = ("PoseStamped", "TransformStamped")

    def __init__(self, topic, type_name, trail=120):
        self._trail_cap = trail
        super().__init__(topic, type_name)
        self._trail: deque = deque(maxlen=trail)

    def _setup_axes(self) -> None:
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.ax.set_title(self.topic, color="#e5f4ff", fontsize=8)

    def tick(self) -> None:
        import numpy as np
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq:
            return
        self._last_seq = seq
        if self.type_name == "PoseStamped":
            p, q = msg.pose.position, msg.pose.orientation
        else:
            p, q = msg.transform.translation, msg.transform.rotation
        self._trail.append((p.x, p.y, p.z))
        arr = np.array(self._trail)
        self.ax.cla()
        self.ax.set_title(self.topic, color="#e5f4ff", fontsize=8)
        self.ax.plot(arr[:, 0], arr[:, 1], arr[:, 2], color="#6ee2ff")
        x, y, z, w = q.x, q.y, q.z, q.w
        R = np.array([
            [1 - 2*(y*y+z*z), 2*(x*y-z*w),     2*(x*z+y*w)],
            [2*(x*y+z*w),     1 - 2*(x*x+z*z), 2*(y*z-x*w)],
            [2*(x*z-y*w),     2*(y*z+x*w),     1 - 2*(x*x+y*y)],
        ])
        origin = np.array([p.x, p.y, p.z])
        for i, color in enumerate(("#ff6e9e", "#6ee2ff", "#ffd56e")):
            end = origin + R[:, i] * 0.2
            self.ax.plot(*zip(origin, end), color=color)
        self.canvas.draw_idle()


class TfPanel(BasePanel):
    type_names = ("TFMessage",)

    def __init__(self, topic, type_name):
        super().__init__(topic, type_name)
        _, QtGui, QtWidgets = _qt()
        self.widget = QtWidgets.QPlainTextEdit()
        self.widget.setReadOnly(True)
        self.widget.setFont(QtGui.QFont("monospace", 9))
        self.widget.setStyleSheet("background:#0b0b10; color:#9ee7ff;")
        self._edges: Dict[str, str] = {}

    def tick(self) -> None:
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq:
            return
        self._last_seq = seq
        for t in msg.transforms:
            self._edges[t.child_frame_id] = t.header.frame_id
        roots = set(self._edges.values()) - set(self._edges.keys())
        lines = [f"=== {self.topic}  tf tree ==="]
        def walk(node, depth):
            lines.append("  " * depth + node)
            for c, p in self._edges.items():
                if p == node: walk(c, depth + 1)
        for r in sorted(roots): walk(r, 0)
        self.widget.setPlainText("\n".join(lines))


class MarkerPanel(_MplPanel):
    type_names = ("MarkerArray", "Marker")

    def _setup_axes(self) -> None:
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.ax.set_title(self.topic, color="#e5f4ff", fontsize=8)

    def tick(self) -> None:
        import numpy as np
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq:
            return
        self._last_seq = seq
        markers = msg.markers if self.type_name == "MarkerArray" else [msg]
        self.ax.cla()
        self.ax.set_title(self.topic, color="#e5f4ff", fontsize=8)
        for m in markers:
            if m.points:
                pts = np.array([[p.x, p.y, p.z] for p in m.points])
            else:
                pts = np.array([[m.pose.position.x, m.pose.position.y,
                                   m.pose.position.z]])
            c = (m.color.r, m.color.g, m.color.b, max(0.3, m.color.a))
            if m.type in (4, 5) and len(pts) > 1:
                self.ax.plot(pts[:, 0], pts[:, 1], pts[:, 2], color=c)
            else:
                self.ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2],
                                  color=c, s=max(4, m.scale.x * 40.0))
        self.canvas.draw_idle()


# ---------------------------------------------------------------------------
# GL-accelerated 3D panels (pyqtgraph + OpenGL)
#
# 相比 matplotlib 的软件 3D，OpenGL 走 GPU，点云 / 激光 / 位姿的刷新率与
# 交互（鼠标拖拽环绕、滚轮缩放）都是 rqt/rviz 级别。无 pyqtgraph 时自动
# 回退到 matplotlib 版本。
# ---------------------------------------------------------------------------

def _make_gl_view_class():
    """Subclass GLViewWidget 加两条 rviz 级的便利交互：
       * Shift + 左键拖 = 平移（触控板无中键也能用）
       * Ctrl + 左键仍保留 pyqtgraph 原生的 pan
       * 中键 / 右键 / 滚轮 均沿用 pyqtgraph 默认
    """
    from PyQt5 import QtCore
    class _CustomGlView(_gl.GLViewWidget):
        def mousePressEvent(self, ev):
            self._talos_prev = ev.pos()
            super().mousePressEvent(ev)

        def mouseMoveEvent(self, ev):
            if (ev.buttons() & QtCore.Qt.LeftButton
                    and ev.modifiers() & QtCore.Qt.ShiftModifier):
                prev = getattr(self, "_talos_prev", ev.pos())
                dx = ev.pos().x() - prev.x()
                dy = ev.pos().y() - prev.y()
                self._talos_prev = ev.pos()
                self.pan(-dx, -dy, 0, relative="view-upright")
                # 仍然要同步 pyqtgraph 内部 mousePos，否则松开 Shift 继续拖动会跳
                try:
                    self.mousePos = ev.pos() if not hasattr(ev, "position") \
                        else ev.position()
                except Exception:
                    pass
                ev.accept(); return
            self._talos_prev = ev.pos()
            super().mouseMoveEvent(ev)
    return _CustomGlView


class _GlPanel(BasePanel):
    """GL 3D 面板基类：QWidget 容器 + 工具栏 + GLViewWidget + 网格 + 轴。

    暴露 `self.toolbar` (QHBoxLayout) 给子类在尾部追加控件（滑块 / 标签 等），
    追加时用 `self.toolbar.insertWidget(self.toolbar.count() - 1, w)` 把控件插到
    末尾 stretch 之前。
    """

    _VIEW_CLS = None  # 懒实例化，避免模块级导入时就触发 GL

    def __init__(self, topic: str, type_name: str,
                 grid_size: float = 10.0, distance: float = 12.0,
                 elevation: float = 30.0, azimuth: float = 45.0):
        super().__init__(topic, type_name)
        QtCore, QtGui, QtWidgets = _qt()

        container = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # Toolbar：重置视角 / 切换网格 / 切换原点轴
        bar_w = QtWidgets.QWidget()
        bar_w.setStyleSheet("background:#0b1f3a;")
        bar = QtWidgets.QHBoxLayout(bar_w)
        bar.setContentsMargins(6, 2, 6, 2); bar.setSpacing(4)

        def _tool(text, checkable=False, checked=True):
            b = QtWidgets.QToolButton()
            b.setText(text)
            b.setCheckable(checkable)
            b.setChecked(checked)
            b.setStyleSheet(
                "QToolButton { color:#9ee7ff; background:transparent;"
                " border:1px solid #1e3a68; border-radius:4px;"
                " padding:2px 8px; }"
                "QToolButton:checked { background:#1e3a68; color:#6ee2ff; }"
                "QToolButton:hover   { border-color:#6ee2ff; }")
            return b

        self._reset_btn = _tool("重置视角")
        self._grid_btn  = _tool("网格", checkable=True, checked=True)
        self._axis_btn  = _tool("原点轴", checkable=True, checked=True)
        self._reset_btn.setToolTip("回到默认相机方位")
        self._grid_btn.setToolTip("显示 / 隐藏 Z=0 网格")
        self._axis_btn.setToolTip("显示 / 隐藏原点 XYZ 轴（红绿蓝）")
        self._reset_btn.clicked.connect(self._reset_view)
        self._grid_btn.toggled.connect(self._toggle_grid)
        self._axis_btn.toggled.connect(self._toggle_axis)
        bar.addWidget(self._reset_btn)
        bar.addWidget(self._grid_btn)
        bar.addWidget(self._axis_btn)
        bar.addStretch()
        self.toolbar = bar
        vbox.addWidget(bar_w)

        # 3D view —— 自定义子类支持 Shift+Left = pan
        if _GlPanel._VIEW_CLS is None:
            _GlPanel._VIEW_CLS = _make_gl_view_class()
        self.view = _GlPanel._VIEW_CLS()
        # 深色但带蓝的背景，比纯黑更柔和，同时让暖色点更突出
        self.view.setBackgroundColor(QtGui.QColor(6, 13, 24))
        self.view.opts["distance"]  = distance
        self.view.opts["elevation"] = elevation
        self.view.opts["azimuth"]   = azimuth
        self._default_opts = {k: self.view.opts[k] for k in
                              ("distance", "elevation", "azimuth", "center")
                              if k in self.view.opts}

        # Grid（Z=0 平面，亮蓝色半透明 —— 够显眼又不抢戏）
        self.grid = _gl.GLGridItem()
        self.grid.setSize(grid_size, grid_size)
        self.grid.setSpacing(1, 1)
        try:
            self.grid.setColor((90, 130, 180, 170))
        except Exception:
            pass
        self.view.addItem(self.grid)

        # 原点坐标轴（X=红 Y=绿 Z=蓝）
        self.axis = _gl.GLAxisItem()
        self.axis.setSize(1.0, 1.0, 1.0)
        self.view.addItem(self.axis)

        vbox.addWidget(self.view, stretch=1)
        self.widget = container

    def _reset_view(self) -> None:
        for k, v in self._default_opts.items():
            self.view.opts[k] = v
        self.view.update()

    def _toggle_grid(self, on: bool) -> None:
        self.grid.setVisible(on)

    def _toggle_axis(self, on: bool) -> None:
        self.axis.setVisible(on)


class GlCloudPanel(_GlPanel):
    type_names = ("PointCloud2",)

    def __init__(self, topic, type_name):
        super().__init__(topic, type_name, grid_size=20.0, distance=15.0)
        QtCore, QtGui, QtWidgets = _qt()
        import numpy as np
        self._point_size = 6.0   # 像素，比 matplotlib 3D 的软散点大且清晰

        self.scatter = _gl.GLScatterPlotItem(
            pos=np.zeros((0, 3), dtype="f4"),
            color=(1.0, 0.85, 0.3, 1.0),   # 默认亮黄，当数据只有一帧时仍可见
            size=self._point_size, pxMode=True)
        self.view.addItem(self.scatter)

        # 点大小滑块（1–15 像素）
        size_label = QtWidgets.QLabel("点大小")
        size_label.setStyleSheet("color:#9ee7ff; padding:0 4px;")
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        slider.setMinimum(1); slider.setMaximum(15)
        slider.setValue(int(self._point_size))
        slider.setFixedWidth(120)
        slider.valueChanged.connect(self._on_size_change)

        # 实时点数指示
        self._count_label = QtWidgets.QLabel("0 pts")
        self._count_label.setStyleSheet(
            "color:#6ee2ff; background:#0d2746; border:1px solid #1e3a68;"
            " border-radius:4px; padding:2px 8px; font-weight:600;")

        # 按顺序把三个控件插到尾部 stretch 之前
        tail = self.toolbar.count() - 1
        self.toolbar.insertWidget(tail, size_label); tail += 1
        self.toolbar.insertWidget(tail, slider);     tail += 1
        self.toolbar.insertWidget(tail, self._count_label)

    def _on_size_change(self, v: int) -> None:
        self._point_size = float(v)
        cur = self.scatter.pos
        if cur is not None and len(cur) > 0:
            self.scatter.setData(size=self._point_size)

    def tick(self) -> None:
        import numpy as np
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq:
            return
        self._last_seq = seq
        fields = {f.name: f for f in msg.fields}
        if not all(k in fields for k in ("x", "y", "z")):
            return
        data = bytes(msg.data)
        n = len(data) // max(1, msg.point_step)
        if n == 0:
            return
        buf = np.frombuffer(data, dtype=np.uint8).reshape(n, msg.point_step)

        def viewf(name):
            off = fields[name].offset
            return np.frombuffer(buf[:, off:off + 4].tobytes(), dtype=np.float32)

        try:
            xyz = np.column_stack([viewf("x"), viewf("y"), viewf("z")])
        except Exception:
            return
        xyz = xyz[np.isfinite(xyz).all(axis=1)]
        if len(xyz) == 0:
            return
        # GPU 可以轻松千万点级别，但 CDR 解码与 setData 开销才是瓶颈 ——
        # 这里兜底降采样到 200k 保证 Qt 主线程不卡。
        raw_n = len(xyz)
        if raw_n > 200_000:
            idx = np.random.choice(raw_n, 200_000, replace=False)
            xyz = xyz[idx]
        colors = _turbo_colors(xyz[:, 2])
        self.scatter.setData(pos=xyz, color=colors, size=self._point_size)
        if raw_n > 200_000:
            self._count_label.setText(
                f"{raw_n/1000:.1f}k pts (显 200k)")
        elif raw_n >= 1000:
            self._count_label.setText(f"{raw_n/1000:.1f}k pts")
        else:
            self._count_label.setText(f"{raw_n} pts")


class GlScanPanel(_GlPanel):
    type_names = ("LaserScan",)

    def __init__(self, topic, type_name):
        super().__init__(topic, type_name, grid_size=10.0,
                          distance=10.0, elevation=85.0, azimuth=0.0)
        import numpy as np
        self.scatter = _gl.GLScatterPlotItem(
            pos=np.zeros((0, 3), dtype="f4"),
            color=(1.0, 0.9, 0.3, 1.0), size=5.0, pxMode=True)
        self.rays = _gl.GLLinePlotItem(
            pos=np.zeros((0, 3), dtype="f4"),
            color=(0.35, 0.65, 1.0, 0.25), width=1.0,
            antialias=True, mode="lines")
        self.view.addItem(self.rays)
        self.view.addItem(self.scatter)

    def tick(self) -> None:
        import numpy as np
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq or not msg.ranges:
            return
        self._last_seq = seq
        n = len(msg.ranges)
        angles = np.linspace(msg.angle_min,
                               msg.angle_min + msg.angle_increment * (n - 1), n,
                               dtype=np.float32)
        ranges = np.array(msg.ranges, dtype=np.float32)
        valid = (np.isfinite(ranges)
                 & (ranges > float(msg.range_min))
                 & (ranges < float(msg.range_max)))
        if not valid.any():
            return
        xs = (ranges * np.cos(angles))[valid]
        ys = (ranges * np.sin(angles))[valid]
        zs = np.zeros_like(xs, dtype=np.float32)
        pts = np.column_stack([xs, ys, zs]).astype(np.float32)

        # 每条射线：origin → endpoint（半透明，便于看出扫描扇形结构）
        origin = np.zeros_like(pts)
        ray_segs = np.empty((2 * len(pts), 3), dtype=np.float32)
        ray_segs[0::2] = origin; ray_segs[1::2] = pts

        colors = _turbo_colors(ranges[valid],
                                vmin=float(msg.range_min),
                                vmax=float(msg.range_max))
        self.scatter.setData(pos=pts, color=colors, size=5.0)
        self.rays.setData(pos=ray_segs)


class GlPosePanel(_GlPanel):
    type_names = ("PoseStamped", "TransformStamped")

    def __init__(self, topic, type_name, trail=500):
        super().__init__(topic, type_name, grid_size=10.0, distance=8.0)
        import numpy as np
        self._trail_cap = trail
        self._trail: deque = deque(maxlen=trail)
        self.trail_line = _gl.GLLinePlotItem(
            pos=np.zeros((0, 3), dtype="f4"),
            color=(0.4, 0.9, 1.0, 0.85), width=2.0, antialias=True)
        # 当前位姿：三段 RGB 轴
        self.ax_x = _gl.GLLinePlotItem(pos=np.zeros((2, 3), dtype="f4"),
                                         color=(1.0, 0.25, 0.3, 1.0),
                                         width=3.0, antialias=True)
        self.ax_y = _gl.GLLinePlotItem(pos=np.zeros((2, 3), dtype="f4"),
                                         color=(0.3, 1.0, 0.35, 1.0),
                                         width=3.0, antialias=True)
        self.ax_z = _gl.GLLinePlotItem(pos=np.zeros((2, 3), dtype="f4"),
                                         color=(0.35, 0.55, 1.0, 1.0),
                                         width=3.0, antialias=True)
        for it in (self.trail_line, self.ax_x, self.ax_y, self.ax_z):
            self.view.addItem(it)

    def tick(self) -> None:
        import numpy as np
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq:
            return
        self._last_seq = seq
        if self.type_name == "PoseStamped":
            p, q = msg.pose.position, msg.pose.orientation
        else:
            p, q = msg.transform.translation, msg.transform.rotation
        origin = np.array([p.x, p.y, p.z], dtype=np.float32)
        self._trail.append(origin)
        self.trail_line.setData(pos=np.asarray(self._trail, dtype=np.float32))

        x, y, z, w = q.x, q.y, q.z, q.w
        R = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w),     2 * (x * z + y * w)],
            [2 * (x * y + z * w),     1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w),     2 * (y * z + x * w),     1 - 2 * (x * x + y * y)],
        ], dtype=np.float32)
        L = 0.5
        self.ax_x.setData(pos=np.vstack([origin, origin + R[:, 0] * L]))
        self.ax_y.setData(pos=np.vstack([origin, origin + R[:, 1] * L]))
        self.ax_z.setData(pos=np.vstack([origin, origin + R[:, 2] * L]))


class GlMarkerPanel(_GlPanel):
    type_names = ("MarkerArray", "Marker")

    _TYPE_ARROW      = 0
    _TYPE_CUBE       = 1
    _TYPE_SPHERE     = 2
    _TYPE_CYLINDER   = 3
    _TYPE_LINE_STRIP = 4
    _TYPE_LINE_LIST  = 5
    _TYPE_CUBE_LIST  = 6
    _TYPE_SPHERE_LIST= 7
    _TYPE_POINTS     = 8

    def __init__(self, topic, type_name):
        super().__init__(topic, type_name, grid_size=10.0, distance=10.0)
        self._items: List[Any] = []

    def tick(self) -> None:
        import numpy as np
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq:
            return
        self._last_seq = seq

        # 全量清空再重建 —— Marker 数据普遍很小，开销忽略。
        for it in self._items:
            try: self.view.removeItem(it)
            except Exception: pass
        self._items = []

        markers = msg.markers if self.type_name == "MarkerArray" else [msg]
        for m in markers:
            color = (float(m.color.r), float(m.color.g), float(m.color.b),
                     max(0.35, float(m.color.a)))
            if m.points:
                pts = np.array([[p.x, p.y, p.z] for p in m.points],
                                 dtype=np.float32)
            else:
                p = m.pose.position
                pts = np.array([[p.x, p.y, p.z]], dtype=np.float32)

            if m.type in (self._TYPE_LINE_STRIP, self._TYPE_LINE_LIST) and len(pts) >= 2:
                mode = "line_strip" if m.type == self._TYPE_LINE_STRIP else "lines"
                it = _gl.GLLinePlotItem(pos=pts, color=color, width=2.0,
                                          antialias=True, mode=mode)
            elif m.type in (self._TYPE_POINTS, self._TYPE_SPHERE_LIST,
                             self._TYPE_CUBE_LIST):
                size = max(3.0, float(m.scale.x) * 30.0)
                it = _gl.GLScatterPlotItem(pos=pts, color=color, size=size,
                                             pxMode=True)
            else:
                size = max(6.0, float(m.scale.x) * 40.0)
                it = _gl.GLScatterPlotItem(pos=pts, color=color, size=size,
                                             pxMode=True)
            self.view.addItem(it)
            self._items.append(it)


_PANEL_REGISTRY: Dict[str, type] = {}
if _HAS_GL:
    _REG_SET = (ImagePanel, ScalarPanel, ImuPanel, TwistPanel,
                GlScanPanel, GlCloudPanel, GlPosePanel, TfPanel, GlMarkerPanel)
else:
    _REG_SET = (ImagePanel, ScalarPanel, ImuPanel, TwistPanel,
                ScanPanel, CloudPanel, PosePanel, TfPanel, MarkerPanel)
for _cls in _REG_SET:
    for _tn in _cls.type_names:
        _PANEL_REGISTRY[_tn] = _cls


def create_panel(topic: str, type_name: str):
    cls = _PANEL_REGISTRY.get(type_name)
    if cls is None:
        cls = ScalarPanel
        type_name = "Float64"
    panel = cls(topic, type_name)
    return panel, issubclass(cls, ImagePanel)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

def register(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--refresh", type=float, default=2.0,
                          help="Topic list refresh interval in seconds (default 2)")
    parser.set_defaults(func=_do_rqt)


# 样式中完全不用 px 字号 —— 由 app.setFont(QFont(pt)) 统一控制 pt 大小，
# Qt 按屏幕 DPI 自动放大，HiDPI 不会糊。
_STYLESHEET = """
QMainWindow, QDialog { background:#071222; color:#e5f4ff; }
QLabel, QCheckBox, QPushButton, QTableWidget, QHeaderView::section,
QComboBox, QToolButton, QPlainTextEdit, QLineEdit, QGroupBox, QMenu {
    color:#e5f4ff; background:transparent;
}
QPushButton, QToolButton, QComboBox, QLineEdit {
    background:#0b1f3a; border:1px solid #1e3a68;
    border-radius:6px; padding:8px 14px;
}
QPushButton:hover, QToolButton:hover { border-color:#6ee2ff; color:#6ee2ff; }

QTableWidget { background:#0b1f3a; gridline-color:#1e3a68; border:1px solid #1e3a68; }
QTableWidget::item { padding:10px; }
QHeaderView::section { background:#0d2746; padding:10px; border:0; color:#9ee7ff; font-weight:700; }
QTableView::item:selected { background:#1e3a68; }

QGroupBox { border:1px solid #1e3a68; border-radius:8px; margin-top:18px; font-weight:600; }
QGroupBox::title {
    subcontrol-origin:margin; left:14px; padding:0 8px;
    color:#6ee2ff; font-weight:700;
}

QMenu { background:#0b1f3a; border:1px solid #1e3a68; padding:4px; }
QMenu::item { padding:8px 22px; }
QMenu::item:selected { background:#1e3a68; color:#6ee2ff; }
"""


def _do_rqt(args) -> int:
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    QtCore, QtGui, QtWidgets = _qt()

    # HiDPI: 告诉 Qt 按屏幕 DPR 自动放大 + 让字体用 pt（pt 会按 DPI 缩放）
    for attr in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        if hasattr(QtCore.Qt, attr):
            QtWidgets.QApplication.setAttribute(getattr(QtCore.Qt, attr), True)
    try:
        QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
            QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass

    app = QtWidgets.QApplication(sys.argv[:1])

    # 全局字号走 pt（12 pt ≈ 16 px @ 96 DPI；HiDPI 上自动放大）
    base_pt = float(os.environ.get("TALOS_RQT_FONT_PT", "12"))
    font = app.font()
    font.setPointSizeF(base_pt)
    app.setFont(font)

    app.setStyleSheet(_STYLESHEET)

    win = _MainWindow(refresh_sec=args.refresh)
    win.show()
    rc = app.exec_()
    win.close_all_panels()
    return int(rc)


def _MainWindow(refresh_sec: float,
                 type_filter: Optional[Tuple[str, ...]] = None,
                 window_title: str = "TalosOS rqt",
                 list_title: str = "已发现话题",
                 intro: Optional[str] = None):
    """构造 dashboard 主窗。

    参数：
      type_filter    只允许这些类型出现在话题列表里（匹配广播 / 启发式后的
                     最终类型）。None 表示不过滤，显示所有。
      window_title   Qt 窗口标题
      list_title     左侧话题列表的标题
      intro          左下提示文字（覆盖默认"单击 + 或双击话题行……"）
    """
    QtCore, QtGui, QtWidgets = _qt()

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle(window_title)
            self.resize(1400, 900)
            self._panels: List[Tuple[QtWidgets.QWidget, Any, bool]] = []
            self._type_filter = (set(type_filter)
                                   if type_filter is not None else None)

            central = QtWidgets.QWidget()
            root = QtWidgets.QHBoxLayout(central)
            self.setCentralWidget(central)

            # ---------- LEFT: topic discovery ----------
            left = QtWidgets.QFrame()
            left.setMinimumWidth(520)    # 容得下长话题名 + 类型药丸 + [+]
            left.setMaximumWidth(680)
            left_lay = QtWidgets.QVBoxLayout(left)
            left_lay.setSpacing(8)

            title = QtWidgets.QLabel(list_title)
            title.setStyleSheet(
                "color:#6ee2ff; font-weight:700; font-size:18px;")
            self._refresh_btn = QtWidgets.QToolButton()
            self._refresh_btn.setText("⟳ 刷新")
            self._refresh_btn.clicked.connect(self._refresh_topics)
            top_bar = QtWidgets.QHBoxLayout()
            top_bar.addWidget(title); top_bar.addStretch()
            top_bar.addWidget(self._refresh_btn)
            left_lay.addLayout(top_bar)

            # 3 列：话题 / 类型标签 / + 按钮
            self._table = QtWidgets.QTableWidget(0, 3)
            self._table.setHorizontalHeaderLabels(
                ["话题", "自动识别类型", ""])
            self._table.horizontalHeader().setSectionResizeMode(
                0, QtWidgets.QHeaderView.Stretch)
            self._table.horizontalHeader().setSectionResizeMode(
                1, QtWidgets.QHeaderView.ResizeToContents)
            self._table.horizontalHeader().setSectionResizeMode(
                2, QtWidgets.QHeaderView.ResizeToContents)
            self._table.verticalHeader().setVisible(False)
            self._table.setSelectionBehavior(
                QtWidgets.QAbstractItemView.SelectRows)
            self._table.setSelectionMode(
                QtWidgets.QAbstractItemView.NoSelection)
            # 左键双击话题名 / 点 [+] 按钮都直接加面板；右键类型标签弹菜单改类型
            self._table.cellDoubleClicked.connect(self._row_double_clicked)
            self._table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            self._table.customContextMenuRequested.connect(self._row_ctx_menu)
            self._table.verticalHeader().setDefaultSectionSize(52)  # 让药丸+按钮有呼吸空间
            left_lay.addWidget(self._table, stretch=1)

            self._clear_btn = QtWidgets.QPushButton("清空所有面板")
            self._clear_btn.clicked.connect(self.close_all_panels)
            btn_row = QtWidgets.QHBoxLayout()
            btn_row.addWidget(self._clear_btn)
            left_lay.addLayout(btn_row)

            default_intro = (
                "单击 + 或双击话题行，按识别出的类型直接添加面板。\n"
                "右键话题行可以把类型改成别的再添加。\n"
                "图像类会并排铺在右上方，其它类型进入右下网格。")
            hint = QtWidgets.QLabel(intro if intro is not None else default_intro)
            hint.setStyleSheet("color:#7c9ac9; font-size:13px;")
            hint.setWordWrap(True)
            left_lay.addWidget(hint)

            # 空状态提示（话题列表筛空时显示；由 _refresh_topics 切换可见）
            self._empty_hint = QtWidgets.QLabel()
            self._empty_hint.setAlignment(QtCore.Qt.AlignCenter)
            self._empty_hint.setStyleSheet(
                "color:#7c9ac9; padding:14px; font-style:italic;")
            self._empty_hint.setWordWrap(True)
            self._empty_hint.setVisible(False)
            left_lay.addWidget(self._empty_hint)

            root.addWidget(left)

            # ---------- RIGHT: panels ----------
            right = QtWidgets.QFrame()
            right_lay = QtWidgets.QVBoxLayout(right)

            self._image_row = QtWidgets.QFrame()
            self._image_row_lay = QtWidgets.QHBoxLayout(self._image_row)
            self._image_row_lay.setContentsMargins(0, 0, 0, 0)
            self._image_row_lay.setSpacing(6)
            self._img_placeholder = QtWidgets.QLabel(
                "（勾选图像话题后 + 添加，它们会并排显示在这里）")
            self._img_placeholder.setStyleSheet("color:#456; padding:20px;")
            self._img_placeholder.setAlignment(QtCore.Qt.AlignCenter)
            self._image_row_lay.addWidget(self._img_placeholder)
            right_lay.addWidget(self._image_row, stretch=1)

            self._grid_host = QtWidgets.QFrame()
            self._grid = QtWidgets.QGridLayout(self._grid_host)
            self._grid.setSpacing(6)
            right_lay.addWidget(self._grid_host, stretch=2)

            root.addWidget(right, stretch=1)

            # ---------- timers ----------
            self._refresh_timer = QtCore.QTimer()
            self._refresh_timer.timeout.connect(self._refresh_topics)
            self._refresh_timer.start(int(refresh_sec * 1000))
            self._tick_timer = QtCore.QTimer()
            self._tick_timer.timeout.connect(self._tick_panels)
            self._tick_timer.start(RENDER_TICK_MS)   # ~30 FPS

            self._refresh_topics()

        # ---- topic discovery ----
        def _refresh_topics(self) -> None:
            # 用户手动改过的类型要保留
            existing: Dict[str, str] = {}
            for r in range(self._table.rowCount()):
                topic_item = self._table.item(r, 0)
                tag = self._table.cellWidget(r, 1)
                if topic_item is not None and tag is not None:
                    existing[topic_item.text()] = tag.property("type_name")

            entries = list_topics()   # [(topic, broadcast_type)]

            # 先把每条 entry 解析成 (topic, type_name, source)，然后在
            # type_filter 指定时过滤掉不感兴趣的类型。
            resolved: List[Tuple[str, str, str]] = []
            for topic, broadcast_type in entries:
                if topic in existing:
                    tn, src = existing[topic], "user"
                elif broadcast_type:
                    tn, src = broadcast_type, "broadcast"
                else:
                    tn, src = guess_type(topic), "guess"
                if self._type_filter is not None and tn not in self._type_filter:
                    continue
                resolved.append((topic, tn, src))

            self._table.setRowCount(len(resolved))
            for r, (topic, type_name, source) in enumerate(resolved):
                topic_it = QtWidgets.QTableWidgetItem(topic)
                topic_it.setToolTip(topic)
                self._table.setItem(r, 0, topic_it)
                self._table.setCellWidget(
                    r, 1, self._make_type_tag(type_name, source))
                self._table.setCellWidget(r, 2, self._make_add_button(r))

            # 空状态文案
            if not resolved:
                if self._type_filter is not None:
                    self._empty_hint.setText(
                        "未发现匹配的话题。\n\n"
                        "需要以下类型之一：\n" +
                        "、".join(sorted(self._type_filter)))
                else:
                    self._empty_hint.setText(
                        "暂无话题。确认 publisher 已启动、与订阅端在同一局域网。")
                self._empty_hint.setVisible(True)
            else:
                self._empty_hint.setVisible(False)

        def _make_type_tag(self, type_name: str, source: str = "broadcast"):
            lbl = QtWidgets.QLabel(type_name)
            lbl.setProperty("typeTag", True)
            lbl.setProperty("type_name", type_name)
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            color = _TYPE_COLOR.get(type_name, "#9ee7ff")
            border = "1px dashed" if source == "guess" else "1px solid"
            # 显式把字号固定为 app 基准 pt ×1.0 并加粗 —— 不靠继承，
            # 避免 QTableWidget cellWidget 下字号被 Qt 默认小值覆盖。
            f = QtGui.QFont()
            f.setPointSizeF(float(os.environ.get("TALOS_RQT_FONT_PT", "12")))
            f.setBold(True)
            lbl.setFont(f)
            lbl.setMinimumWidth(160)      # 避免被 ResizeToContents 压成小条
            lbl.setStyleSheet(
                f"background:#0d2746; border:{border} #1e3a68;"
                f"border-radius:12px; padding:6px 16px;"
                f"color:{color};")
            lbl.setToolTip({
                "broadcast": f"{type_name}  ← publisher 自己广播",
                "user":      f"{type_name}  ← 你手动改过",
                "guess":     f"{type_name}  ← 按话题名推测，可能不准（右键改）",
            }.get(source, type_name))
            return lbl

        def _make_add_button(self, row: int):
            btn = QtWidgets.QToolButton()
            btn.setText("+")
            btn.setToolTip("按当前类型立即添加到面板区")
            btn.setFixedSize(44, 38)
            f = QtGui.QFont()
            f.setPointSizeF(float(os.environ.get("TALOS_RQT_FONT_PT", "12")) + 6)
            f.setBold(True)
            btn.setFont(f)
            btn.setStyleSheet(
                "QToolButton { background:#1e3a68; border:1px solid #6ee2ff;"
                " color:#6ee2ff; border-radius:6px; padding:0; }"
                "QToolButton:hover { background:#2d5a9c; color:#e5f4ff; }")
            btn.clicked.connect(lambda _=False, r=row: self._add_row(r))
            return btn

        # ---- panel lifecycle ----
        def _add_row(self, row: int) -> None:
            topic = self._table.item(row, 0).text()
            tag = self._table.cellWidget(row, 1)
            type_name = tag.property("type_name") if tag else guess_type(topic)
            self._add_panel(topic, type_name)

        def _row_double_clicked(self, row: int, _col: int) -> None:
            self._add_row(row)

        def _row_ctx_menu(self, pos) -> None:
            idx = self._table.indexAt(pos)
            if not idx.isValid():
                return
            row = idx.row()
            menu = QtWidgets.QMenu(self)
            topic = self._table.item(row, 0).text()
            menu.addAction(QtWidgets.QAction(topic, menu,
                                               enabled=False))
            menu.addSeparator()
            # 添加（用当前标签的类型）
            act_add = menu.addAction("以当前类型 + 添加")
            act_add.triggered.connect(lambda: self._add_row(row))
            menu.addSeparator()
            menu.addAction(QtWidgets.QAction("—— 改成别的类型 ——",
                                              menu, enabled=False))
            # 列出所有候选类型；勾中的是当前
            tag = self._table.cellWidget(row, 1)
            current = tag.property("type_name") if tag else ""
            for t in _ALL_TYPES:
                a = menu.addAction(f"{'✓ ' if t == current else '   '}{t}")
                a.triggered.connect(
                    lambda _=False, _r=row, _t=t: self._change_type(_r, _t))
            menu.exec_(self._table.viewport().mapToGlobal(pos))

        def _change_type(self, row: int, new_type: str) -> None:
            self._table.setCellWidget(row, 1, self._make_type_tag(new_type))

        def _add_panel(self, topic: str, type_name: str) -> None:
            for _h, p, _i in self._panels:
                if p.topic == topic and p.type_name == type_name:
                    return
            try:
                panel, is_image = create_panel(topic, type_name)
            except Exception as ex:
                QtWidgets.QMessageBox.warning(self, "创建面板失败", str(ex))
                return

            host = QtWidgets.QGroupBox(f"{topic}  [{type_name}]")
            host_lay = QtWidgets.QVBoxLayout(host)
            host_lay.setContentsMargins(6, 18, 6, 6)

            close_btn = QtWidgets.QToolButton()
            close_btn.setText("×")
            close_btn.setFixedSize(22, 22)
            close_btn.clicked.connect(lambda: self._remove_panel(host))
            header = QtWidgets.QHBoxLayout()
            header.addStretch(); header.addWidget(close_btn)
            host_lay.addLayout(header)
            host_lay.addWidget(panel.widget, stretch=1)

            if is_image:
                if self._img_placeholder is not None:
                    self._image_row_lay.removeWidget(self._img_placeholder)
                    self._img_placeholder.deleteLater()
                    self._img_placeholder = None
                self._image_row_lay.addWidget(host)
            else:
                n = sum(1 for _h, _p, i in self._panels if not i)
                row, col = divmod(n, 2)
                self._grid.addWidget(host, row, col)

            self._panels.append((host, panel, is_image))

        def _remove_panel(self, host) -> None:
            for i, (h, p, img) in enumerate(self._panels):
                if h is host:
                    p.close_sampler()
                    if img:
                        self._image_row_lay.removeWidget(h)
                    else:
                        self._grid.removeWidget(h)
                    h.setParent(None); h.deleteLater()
                    self._panels.pop(i)
                    self._rebuild_grid()
                    self._restore_image_placeholder_if_empty()
                    break

        def _rebuild_grid(self) -> None:
            non_image_hosts = [h for h, _p, img in self._panels if not img]
            while self._grid.count():
                item = self._grid.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
            for i, h in enumerate(non_image_hosts):
                self._grid.addWidget(h, i // 2, i % 2)

        def _restore_image_placeholder_if_empty(self) -> None:
            if any(img for _h, _p, img in self._panels):
                return
            if self._img_placeholder is None:
                self._img_placeholder = QtWidgets.QLabel(
                    "（勾选图像话题后 + 添加，它们会并排显示在这里）")
                self._img_placeholder.setStyleSheet("color:#456; padding:20px;")
                self._img_placeholder.setAlignment(QtCore.Qt.AlignCenter)
                self._image_row_lay.addWidget(self._img_placeholder)

        def close_all_panels(self) -> None:
            for _h, p, _i in self._panels:
                p.close_sampler()
            for h, _p, _i in list(self._panels):
                h.setParent(None); h.deleteLater()
            self._panels.clear()
            self._rebuild_grid()
            while self._image_row_lay.count():
                w = self._image_row_lay.takeAt(0).widget()
                if w is not None: w.setParent(None)
            self._img_placeholder = None
            self._restore_image_placeholder_if_empty()

        def _tick_panels(self) -> None:
            for _h, p, _i in self._panels:
                try:
                    p.tick()
                except Exception:
                    pass

        def closeEvent(self, ev) -> None:
            self.close_all_panels()
            super().closeEvent(ev)

    return MainWindow()
