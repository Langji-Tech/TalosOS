"""`talos viz` — 3D 场景实时可视化（RViz 风 · 单场景多图层）。

两种模式：

  * **Dashboard 模式**（无参数，默认）
        talos viz
    自动发现**可以 3D 可视化**的话题（PointCloud2 / LaserScan /
    PoseStamped / TransformStamped / Marker / MarkerArray）。**右侧是一个
    统一的 3D 场景**（不是多面板网格）—— 所有添加的话题都作为 `layer`
    叠加到同一个 GLViewWidget 里，共享相机、网格、原点轴。左侧话题行点
    **+** 加入场景、变成 **×** 后再点即可移除。

  * **单面板模式**（显式 topic + --type）
        talos viz /demo/cloud --type PointCloud2
        talos viz /tf         --type TFMessage        # TF 走文本帧树
    打开一个只有一个面板的窗口，适合脚本化或紧凑调试。

3D 面板走 `pyqtgraph + OpenGL` GPU 硬件渲染（turbo 配色、Shift+左键拖
平移、点大小滑块等）。
"""

import argparse
import os
import signal
import sys
import time
from collections import deque
from typing import Dict, List, Optional, Tuple


_RENDERER_BY_TYPE = {
    "CompressedImage": "qt", "Image": "qt",
    "LaserScan": "qt", "PointCloud2": "qt",
    "Marker": "qt", "MarkerArray": "qt",
    "PoseStamped": "qt", "TransformStamped": "qt",
    "TFMessage": "tf",
    "Imu": "qt", "TwistStamped": "qt",
    "Float32": "qt", "Float64": "qt", "Int32": "qt", "Int64": "qt",
    "String": "qt",
}

#: Dashboard 只列 3D 能画的类型（= _LAYER_BY_TYPE 的 key）
_3D_TYPES = (
    "PointCloud2", "LaserScan",
    "PoseStamped", "TransformStamped",
    "Marker", "MarkerArray",
    "OccupancyGrid", "Octomap", "OctomapWithPose",
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def register(p: argparse.ArgumentParser) -> None:
    p.add_argument("topic", nargs="?", default=None,
                    help="话题路径；留空则打开 3D dashboard")
    p.add_argument("--type", dest="msg_type", default=None,
                    help="消息类型；与 topic 同时提供走单面板模式")
    p.add_argument("--title", default=None, help="窗口标题")
    p.add_argument("--refresh", type=float, default=2.0,
                    help="dashboard 话题列表刷新间隔秒（默认 2）")
    p.add_argument("--renderer", default="auto",
                    choices=["auto", "qt", "tf",
                              "image", "scan", "cloud", "marker", "pose"],
                    help="auto / qt / tf")
    p.add_argument("--history", type=int, default=None,
                    help="（legacy）pose trail 长度；现用图层默认 500")
    p.add_argument("--max-points", type=int, default=None,
                    help="（legacy）PointCloud2 抽样上限；现用图层默认 200k")
    p.set_defaults(func=_do_viz)


def _do_viz(args) -> int:
    if not args.topic or not args.msg_type:
        if args.topic and not args.msg_type:
            print("提示：缺少 --type，切换到 dashboard 模式", file=sys.stderr)
        return _run_dashboard(args)

    from ..messages import resolve_type
    try:
        resolve_type(args.msg_type)
    except KeyError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2

    renderer = args.renderer
    if renderer == "auto":
        renderer = _RENDERER_BY_TYPE.get(args.msg_type, "qt")
    if renderer in ("image", "scan", "cloud", "marker", "pose"):
        renderer = "qt"

    if renderer == "tf":
        return _run_tf_text(args)
    return _run_qt_viz(args)


# ---------------------------------------------------------------------------
# Layer —— 共享 GLViewWidget 的"RViz 图层"
# ---------------------------------------------------------------------------

def _gl():
    import pyqtgraph.opengl as gl
    return gl


class _Layer:
    """单话题图层，渲染到共享 GLViewWidget。"""

    def __init__(self, topic: str, type_name: str, scene: "_UnifiedScene"):
        from .rqt import TopicSampler
        self.topic = topic
        self.type_name = type_name
        self.scene = scene
        self.sampler = TopicSampler(topic, type_name)
        self.sampler.start()
        self._last_seq = -1
        self._items: List = []
        self._visible = True
        self.point_count = 0

    def stop(self) -> None:
        self.sampler.stop()
        for it in list(self._items):
            self._remove_item(it)
        self._items = []

    def _add_item(self, it) -> None:
        self.scene.view.addItem(it)
        self._items.append(it)

    def _remove_item(self, it) -> None:
        try:
            self.scene.view.removeItem(it)
        except Exception:
            pass
        if it in self._items:
            self._items.remove(it)

    def set_visible(self, on: bool) -> None:
        self._visible = on
        for it in self._items:
            it.setVisible(on)

    def tick(self) -> None:
        raise NotImplementedError


class _CloudLayer(_Layer):
    def __init__(self, topic, type_name, scene):
        super().__init__(topic, type_name, scene)
        import numpy as np
        self.scatter = _gl().GLScatterPlotItem(
            pos=np.zeros((0, 3), dtype="f4"),
            color=(1.0, 0.85, 0.3, 1.0),
            size=scene.point_size, pxMode=True)
        self._add_item(self.scatter)

    def update_point_size(self, size: float) -> None:
        self.scatter.setData(size=float(size))

    def tick(self) -> None:
        if not self._visible: return
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
        raw_n = len(xyz)
        self.point_count = raw_n
        if raw_n == 0:
            return
        if raw_n > 200_000:
            idx = np.random.choice(raw_n, 200_000, replace=False)
            xyz = xyz[idx]
        from .rqt import _turbo_colors
        colors = _turbo_colors(xyz[:, 2])
        self.scatter.setData(pos=xyz, color=colors, size=self.scene.point_size)


class _ScanLayer(_Layer):
    def __init__(self, topic, type_name, scene):
        super().__init__(topic, type_name, scene)
        import numpy as np
        self.scatter = _gl().GLScatterPlotItem(
            pos=np.zeros((0, 3), dtype="f4"),
            color=(1.0, 0.9, 0.3, 1.0), size=5.0, pxMode=True)
        self.rays = _gl().GLLinePlotItem(
            pos=np.zeros((0, 3), dtype="f4"),
            color=(0.35, 0.65, 1.0, 0.25), width=1.0,
            antialias=True, mode="lines")
        self._add_item(self.rays)
        self._add_item(self.scatter)

    def tick(self) -> None:
        if not self._visible: return
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
        origin = np.zeros_like(pts)
        ray_segs = np.empty((2 * len(pts), 3), dtype=np.float32)
        ray_segs[0::2] = origin; ray_segs[1::2] = pts
        from .rqt import _turbo_colors
        colors = _turbo_colors(ranges[valid],
                                vmin=float(msg.range_min),
                                vmax=float(msg.range_max))
        self.scatter.setData(pos=pts, color=colors, size=5.0)
        self.rays.setData(pos=ray_segs)
        self.point_count = len(pts)


class _PoseLayer(_Layer):
    def __init__(self, topic, type_name, scene):
        super().__init__(topic, type_name, scene)
        import numpy as np
        self._trail: deque = deque(maxlen=500)
        self.trail_line = _gl().GLLinePlotItem(
            pos=np.zeros((0, 3), dtype="f4"),
            color=(0.4, 0.9, 1.0, 0.85), width=2.0, antialias=True)
        self.ax_x = _gl().GLLinePlotItem(pos=np.zeros((2, 3), dtype="f4"),
                                           color=(1.0, 0.25, 0.3, 1.0), width=3.0, antialias=True)
        self.ax_y = _gl().GLLinePlotItem(pos=np.zeros((2, 3), dtype="f4"),
                                           color=(0.3, 1.0, 0.35, 1.0), width=3.0, antialias=True)
        self.ax_z = _gl().GLLinePlotItem(pos=np.zeros((2, 3), dtype="f4"),
                                           color=(0.35, 0.55, 1.0, 1.0), width=3.0, antialias=True)
        for it in (self.trail_line, self.ax_x, self.ax_y, self.ax_z):
            self._add_item(it)

    def tick(self) -> None:
        if not self._visible: return
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
            [1 - 2*(y*y+z*z), 2*(x*y-z*w),     2*(x*z+y*w)],
            [2*(x*y+z*w),     1 - 2*(x*x+z*z), 2*(y*z-x*w)],
            [2*(x*z-y*w),     2*(y*z+x*w),     1 - 2*(x*x+y*y)],
        ], dtype=np.float32)
        L = 0.5
        self.ax_x.setData(pos=np.vstack([origin, origin + R[:, 0] * L]))
        self.ax_y.setData(pos=np.vstack([origin, origin + R[:, 1] * L]))
        self.ax_z.setData(pos=np.vstack([origin, origin + R[:, 2] * L]))


class _MarkerLayer(_Layer):
    def tick(self) -> None:
        if not self._visible: return
        import numpy as np
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq:
            return
        self._last_seq = seq
        # 重建
        for it in list(self._items):
            self._remove_item(it)
        markers = msg.markers if self.type_name == "MarkerArray" else [msg]
        for m in markers:
            color = (float(m.color.r), float(m.color.g), float(m.color.b),
                     max(0.35, float(m.color.a)))
            if m.points:
                pts = np.array([[p.x, p.y, p.z] for p in m.points], dtype=np.float32)
            else:
                p = m.pose.position
                pts = np.array([[p.x, p.y, p.z]], dtype=np.float32)
            if m.type in (4, 5) and len(pts) >= 2:
                mode = "line_strip" if m.type == 4 else "lines"
                it = _gl().GLLinePlotItem(pos=pts, color=color, width=2.0,
                                            antialias=True, mode=mode)
            elif m.type in (6, 7, 8):
                it = _gl().GLScatterPlotItem(pos=pts, color=color,
                    size=max(3.0, float(m.scale.x) * 30.0), pxMode=True)
            else:
                it = _gl().GLScatterPlotItem(pos=pts, color=color,
                    size=max(6.0, float(m.scale.x) * 40.0), pxMode=True)
            self._add_item(it)


class _GridLayer(_Layer):
    """OccupancyGrid → XOY 平面图像（RViz 的 Map 显示）。"""

    def __init__(self, topic, type_name, scene):
        super().__init__(topic, type_name, scene)
        self._img_item = None

    def tick(self) -> None:
        if not self._visible: return
        import numpy as np
        gl = _gl()
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq:
            return
        self._last_seq = seq

        info = msg.info
        w, h, res = int(info.width), int(info.height), float(info.resolution)
        if w <= 0 or h <= 0 or res <= 0:
            return
        raw = np.frombuffer(bytes(msg.data), dtype=np.int8)
        if raw.size != w * h:
            return
        grid = raw.reshape(h, w)                # ROS 约定：row-major，行 = y

        # RGBA 像素（注意 GLImageItem 索引是 (X, Y) → 用转置后的 w×h）
        rgba = np.zeros((w, h, 4), dtype=np.ubyte)
        gT = grid.T                              # (w, h)，与 rgba 对齐
        unknown = gT == -1
        occupied = gT > 50
        free = (~unknown) & (~occupied)
        rgba[unknown] = (60, 70, 95, 170)        # 深蓝灰半透明 = 未知
        rgba[free]    = (220, 225, 235, 210)     # 近白 = 自由空间
        if occupied.any():
            occ_vals = gT[occupied].astype(np.float32) / 100.0
            shade = ((1.0 - occ_vals) * 60 + 15).astype(np.ubyte)
            rgba[occupied, 0] = shade
            rgba[occupied, 1] = shade
            rgba[occupied, 2] = shade
            rgba[occupied, 3] = 240

        # 重建 GLImageItem（简单可靠；每帧重建的代价在几 MB 贴图下 < 1ms）
        if self._img_item is not None:
            self._remove_item(self._img_item)
        self._img_item = gl.GLImageItem(data=rgba)
        # 原生：1 像素 = 1 单位；按 resolution 放缩到米，再平移到 origin
        self._img_item.scale(res, res, 1.0)
        self._img_item.translate(
            float(info.origin.position.x),
            float(info.origin.position.y),
            float(info.origin.position.z) - 0.002)  # 避免与 Z=0 网格 z-fight
        self._add_item(self._img_item)
        self.point_count = int(occupied.sum())


_CUBE_UNIT_V = None
_CUBE_UNIT_F = None


def _cube_unit():
    """延迟构造单位立方体顶点 / 三角形索引（供 OctomapLayer 批量实例化）。"""
    global _CUBE_UNIT_V, _CUBE_UNIT_F
    if _CUBE_UNIT_V is not None:
        return _CUBE_UNIT_V, _CUBE_UNIT_F
    import numpy as np
    _CUBE_UNIT_V = np.array([
        [-0.5, -0.5, -0.5], [ 0.5, -0.5, -0.5],
        [ 0.5,  0.5, -0.5], [-0.5,  0.5, -0.5],
        [-0.5, -0.5,  0.5], [ 0.5, -0.5,  0.5],
        [ 0.5,  0.5,  0.5], [-0.5,  0.5,  0.5],
    ], dtype=np.float32)
    _CUBE_UNIT_F = np.array([
        [0, 1, 2], [0, 2, 3],   # -Z
        [4, 6, 5], [4, 7, 6],   # +Z
        [0, 4, 5], [0, 5, 1],   # -Y
        [1, 5, 6], [1, 6, 2],   # +X
        [2, 6, 7], [2, 7, 3],   # +Y
        [3, 7, 4], [3, 4, 0],   # -X
    ], dtype=np.uint32)
    return _CUBE_UNIT_V, _CUBE_UNIT_F


class _OctomapLayer(_Layer):
    """Octomap → 真正的 3D 立方体体素（GLMeshItem 批量）。

    兼容两种 `octomap_msgs/Octomap.data` 载荷：
      1. `id == "talos_voxels_v1"`：我们自己的 demo 格式 —— 连续
         `float32(x) float32(y) float32(z) float32(size)` 记录，每 16 字节。
      2. 其它 id：当前未实现真正的 OctoMap 二叉树解码，跳过渲染。

    每次 tick 重建 mesh。几千体素以下手感丝滑；更大地图建议发 PointCloud2。
    """

    _MY_FORMAT = "talos_voxels_v1"

    def __init__(self, topic, type_name, scene):
        super().__init__(topic, type_name, scene)
        self._mesh_item = None

    def tick(self) -> None:
        if not self._visible: return
        import numpy as np
        gl = _gl()
        msg, seq = self.sampler.latest()
        if msg is None or seq == self._last_seq:
            return
        self._last_seq = seq

        oc = msg.octomap if self.type_name == "OctomapWithPose" else msg
        origin_offset = np.zeros(3, dtype=np.float32)
        if self.type_name == "OctomapWithPose":
            p = msg.origin.position
            origin_offset = np.array([p.x, p.y, p.z], dtype=np.float32)

        if oc.id != self._MY_FORMAT:
            self.point_count = 0
            return

        raw = bytes(oc.data)
        n = len(raw) // 16
        if n == 0:
            if self._mesh_item is not None:
                self._remove_item(self._mesh_item)
                self._mesh_item = None
            self.point_count = 0
            return
        arr = np.frombuffer(raw, dtype=np.float32, count=n * 4).reshape(n, 4)
        centers = arr[:, :3] + origin_offset
        sizes = arr[:, 3].reshape(n, 1, 1)
        self.point_count = n

        # 批量构造所有立方体的顶点与三角形
        unit_v, unit_f = _cube_unit()
        verts = (unit_v[None, :, :] * sizes) + centers[:, None, :]
        verts = verts.reshape(-1, 3).astype(np.float32)

        base = (np.arange(n, dtype=np.uint32) * 8)[:, None, None]
        faces = (unit_f[None, :, :] + base).reshape(-1, 3)

        # 颜色：按 Z 给 turbo，每个体素 12 个面
        from .rqt import _turbo_colors
        colors_per_voxel = _turbo_colors(centers[:, 2])
        face_colors = np.repeat(colors_per_voxel, 12, axis=0).astype(np.float32)

        if self._mesh_item is not None:
            self._remove_item(self._mesh_item)
        self._mesh_item = gl.GLMeshItem(
            vertexes=verts, faces=faces, faceColors=face_colors,
            smooth=False, drawEdges=True,
            edgeColor=(0.05, 0.08, 0.12, 0.6),
            shader="shaded", glOptions="opaque")
        self._add_item(self._mesh_item)


_LAYER_BY_TYPE = {
    "PointCloud2":       _CloudLayer,
    "LaserScan":         _ScanLayer,
    "PoseStamped":       _PoseLayer,
    "TransformStamped":  _PoseLayer,
    "Marker":            _MarkerLayer,
    "MarkerArray":       _MarkerLayer,
    "OccupancyGrid":     _GridLayer,
    "Octomap":           _OctomapLayer,
    "OctomapWithPose":   _OctomapLayer,
}


# ---------------------------------------------------------------------------
# _UnifiedScene —— 右侧那一个大 3D view
# ---------------------------------------------------------------------------

def _UnifiedSceneClass():
    from PyQt5 import QtCore, QtGui, QtWidgets
    from .rqt import _make_gl_view_class
    gl = _gl()

    class _UnifiedScene(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.point_size: float = 6.0
            self._layers: List[_Layer] = []

            vbox = QtWidgets.QVBoxLayout(self)
            vbox.setContentsMargins(0, 0, 0, 0); vbox.setSpacing(0)

            # --- toolbar ---
            bar_w = QtWidgets.QWidget()
            bar_w.setStyleSheet("background:#0b1f3a;")
            bar = QtWidgets.QHBoxLayout(bar_w)
            bar.setContentsMargins(8, 4, 8, 4); bar.setSpacing(6)

            def _tool(text, checkable=False, checked=True, tooltip=None):
                b = QtWidgets.QToolButton()
                b.setText(text); b.setCheckable(checkable); b.setChecked(checked)
                if tooltip: b.setToolTip(tooltip)
                b.setStyleSheet(
                    "QToolButton { color:#9ee7ff; background:transparent;"
                    " border:1px solid #1e3a68; border-radius:4px;"
                    " padding:3px 12px; }"
                    "QToolButton:checked { background:#1e3a68; color:#6ee2ff; }"
                    "QToolButton:hover   { border-color:#6ee2ff; }")
                return b

            self._reset_btn = _tool("重置视角", tooltip="相机回到默认方位")
            self._grid_btn  = _tool("网格", checkable=True, tooltip="显示/隐藏 Z=0 网格")
            self._axis_btn  = _tool("原点轴", checkable=True, tooltip="显示/隐藏原点 XYZ 轴")
            self._reset_btn.clicked.connect(self._reset_view)
            self._grid_btn.toggled.connect(lambda on: self.grid.setVisible(on))
            self._axis_btn.toggled.connect(lambda on: self.axis.setVisible(on))
            bar.addWidget(self._reset_btn)
            bar.addWidget(self._grid_btn)
            bar.addWidget(self._axis_btn)

            sep = QtWidgets.QFrame(); sep.setFrameShape(QtWidgets.QFrame.VLine)
            sep.setStyleSheet("color:#1e3a68;")
            bar.addWidget(sep)

            size_label = QtWidgets.QLabel("点大小")
            size_label.setStyleSheet("color:#9ee7ff; padding:0 4px;")
            bar.addWidget(size_label)
            self._size_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            self._size_slider.setMinimum(1); self._size_slider.setMaximum(15)
            self._size_slider.setValue(int(self.point_size))
            self._size_slider.setFixedWidth(140)
            self._size_slider.valueChanged.connect(self._on_size_change)
            bar.addWidget(self._size_slider)

            bar.addStretch()

            self._status = QtWidgets.QLabel("0 层 · 0 pts")
            self._status.setStyleSheet(
                "color:#6ee2ff; background:#0d2746; border:1px solid #1e3a68;"
                " border-radius:4px; padding:3px 12px; font-weight:600;")
            bar.addWidget(self._status)

            vbox.addWidget(bar_w)

            # --- 3D view ---
            ViewCls = _make_gl_view_class()
            self.view = ViewCls()
            self.view.setBackgroundColor(QtGui.QColor(6, 13, 24))
            self.view.opts["distance"] = 15.0
            self.view.opts["elevation"] = 30.0
            self.view.opts["azimuth"] = 45.0
            self._default_opts = {k: self.view.opts[k] for k in
                                  ("distance", "elevation", "azimuth", "center")
                                  if k in self.view.opts}

            self.grid = gl.GLGridItem()
            self.grid.setSize(30.0, 30.0); self.grid.setSpacing(1, 1)
            try: self.grid.setColor((90, 130, 180, 170))
            except Exception: pass
            self.view.addItem(self.grid)

            self.axis = gl.GLAxisItem()
            self.axis.setSize(1.0, 1.0, 1.0)
            self.view.addItem(self.axis)

            vbox.addWidget(self.view, stretch=1)

        # ---- public API ----
        def add_layer(self, topic, type_name) -> Optional[_Layer]:
            cls = _LAYER_BY_TYPE.get(type_name)
            if cls is None: return None
            layer = cls(topic, type_name, self)
            self._layers.append(layer)
            self._update_status()
            return layer

        def remove_layer(self, layer: _Layer) -> None:
            if layer not in self._layers: return
            layer.stop()
            self._layers.remove(layer)
            self._update_status()

        def remove_all(self) -> None:
            for l in list(self._layers):
                l.stop()
            self._layers.clear()
            self._update_status()

        def tick(self) -> None:
            for l in self._layers:
                try: l.tick()
                except Exception: pass
            self._update_status()

        # ---- internals ----
        def _reset_view(self):
            for k, v in self._default_opts.items():
                self.view.opts[k] = v
            self.view.update()

        def _on_size_change(self, v):
            self.point_size = float(v)
            for l in self._layers:
                if hasattr(l, "update_point_size"):
                    l.update_point_size(self.point_size)

        def _update_status(self):
            n = len(self._layers)
            total = sum(getattr(l, "point_count", 0) for l in self._layers)
            pts_s = (f"{total/1000:.1f}k pts" if total >= 1000 else f"{total} pts")
            self._status.setText(f"{n} 层 · {pts_s}")

    return _UnifiedScene


# Cached (lazy) so import-time cost stays zero when viz is not used
_UnifiedScene = None


def _get_unified_scene_class():
    global _UnifiedScene
    if _UnifiedScene is None:
        _UnifiedScene = _UnifiedSceneClass()
    return _UnifiedScene


# ---------------------------------------------------------------------------
# Dashboard 主窗
# ---------------------------------------------------------------------------

def _VizDashboardClass():
    from PyQt5 import QtCore, QtGui, QtWidgets
    from .rqt import list_topics, guess_type, _TYPE_COLOR, RENDER_TICK_MS

    Scene = _get_unified_scene_class()

    class _VizDashboard(QtWidgets.QMainWindow):
        def __init__(self, refresh_sec=2.0, type_filter=None,
                      window_title="TalosOS viz"):
            super().__init__()
            self.setWindowTitle(window_title)
            self.resize(1500, 920)
            self._type_filter = set(type_filter) if type_filter else None
            self._layer_by_topic: Dict[str, _Layer] = {}

            central = QtWidgets.QWidget()
            root = QtWidgets.QHBoxLayout(central)
            root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
            self.setCentralWidget(central)

            # --- LEFT ---
            left = QtWidgets.QFrame()
            left.setMinimumWidth(440); left.setMaximumWidth(560)
            left_lay = QtWidgets.QVBoxLayout(left)
            left_lay.setContentsMargins(10, 10, 10, 10); left_lay.setSpacing(8)

            title_lbl = QtWidgets.QLabel("可 3D 可视化的话题")
            title_lbl.setStyleSheet("color:#6ee2ff; font-weight:700; font-size:18px;")
            refresh_btn = QtWidgets.QToolButton()
            refresh_btn.setText("⟳ 刷新")
            refresh_btn.clicked.connect(self._refresh_topics)
            top_bar = QtWidgets.QHBoxLayout()
            top_bar.addWidget(title_lbl); top_bar.addStretch()
            top_bar.addWidget(refresh_btn)
            left_lay.addLayout(top_bar)

            self._table = QtWidgets.QTableWidget(0, 3)
            self._table.setHorizontalHeaderLabels(["话题", "类型", ""])
            self._table.horizontalHeader().setSectionResizeMode(
                0, QtWidgets.QHeaderView.Stretch)
            self._table.horizontalHeader().setSectionResizeMode(
                1, QtWidgets.QHeaderView.ResizeToContents)
            self._table.horizontalHeader().setSectionResizeMode(
                2, QtWidgets.QHeaderView.ResizeToContents)
            self._table.verticalHeader().setVisible(False)
            self._table.setSelectionMode(
                QtWidgets.QAbstractItemView.NoSelection)
            self._table.cellDoubleClicked.connect(
                lambda r, _c: self._toggle_row(r))
            self._table.verticalHeader().setDefaultSectionSize(52)
            left_lay.addWidget(self._table, stretch=1)

            clear_btn = QtWidgets.QPushButton("清空所有图层")
            clear_btn.clicked.connect(self._clear_all)
            left_lay.addWidget(clear_btn)

            hint = QtWidgets.QLabel(
                "单击 + 或双击话题行把它加入右侧 3D 场景；变成 × 后再点即可移除。\n"
                "所有图层共用同一个相机：左键拖环绕、Shift+左键拖平移、滚轮缩放。")
            hint.setStyleSheet("color:#7c9ac9; font-size:13px;")
            hint.setWordWrap(True)
            left_lay.addWidget(hint)

            self._empty_hint = QtWidgets.QLabel()
            self._empty_hint.setAlignment(QtCore.Qt.AlignCenter)
            self._empty_hint.setStyleSheet(
                "color:#7c9ac9; padding:14px; font-style:italic;")
            self._empty_hint.setWordWrap(True)
            self._empty_hint.setVisible(False)
            left_lay.addWidget(self._empty_hint)

            root.addWidget(left)

            # --- RIGHT: single 3D scene filling the rest ---
            self.scene = Scene()
            root.addWidget(self.scene, stretch=1)

            # --- timers ---
            self._refresh_timer = QtCore.QTimer()
            self._refresh_timer.timeout.connect(self._refresh_topics)
            self._refresh_timer.start(int(refresh_sec * 1000))
            self._tick_timer = QtCore.QTimer()
            self._tick_timer.timeout.connect(self.scene.tick)
            self._tick_timer.start(RENDER_TICK_MS)   # ~30 FPS

            self._refresh_topics()

        # ---- topic discovery + filter ----
        def _refresh_topics(self):
            entries = list_topics()
            resolved = []
            for topic, broadcast_type in entries:
                if broadcast_type:
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
                self._table.setCellWidget(r, 1, self._make_type_tag(type_name, source))
                active = topic in self._layer_by_topic
                self._table.setCellWidget(r, 2, self._make_toggle_button(r, active))

            if not resolved:
                if self._type_filter is not None:
                    self._empty_hint.setText(
                        "未发现匹配的话题。\n\n需要以下类型之一：\n"
                        + "、".join(sorted(self._type_filter)))
                else:
                    self._empty_hint.setText("暂无话题。")
                self._empty_hint.setVisible(True)
            else:
                self._empty_hint.setVisible(False)

        def _make_type_tag(self, type_name, source="broadcast"):
            lbl = QtWidgets.QLabel(type_name)
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            color = _TYPE_COLOR.get(type_name, "#9ee7ff")
            border = "1px dashed" if source == "guess" else "1px solid"
            f = QtGui.QFont()
            f.setPointSizeF(float(os.environ.get("TALOS_RQT_FONT_PT", "12")))
            f.setBold(True)
            lbl.setFont(f)
            lbl.setMinimumWidth(160)
            lbl.setStyleSheet(
                f"background:#0d2746; border:{border} #1e3a68; border-radius:12px;"
                f" padding:6px 16px; color:{color};")
            lbl.setToolTip({
                "broadcast": f"{type_name}  ← publisher 广播",
                "guess":     f"{type_name}  ← 按话题名推测",
            }.get(source, type_name))
            return lbl

        def _make_toggle_button(self, row, active):
            btn = QtWidgets.QToolButton()
            btn.setText("×" if active else "+")
            btn.setFixedSize(44, 38)
            f = QtGui.QFont()
            f.setPointSizeF(float(os.environ.get("TALOS_RQT_FONT_PT", "12")) + 6)
            f.setBold(True)
            btn.setFont(f)
            if active:
                btn.setStyleSheet(
                    "QToolButton { background:#5a1a20; border:1px solid #ff6e9e;"
                    " color:#ff9eb4; border-radius:6px; padding:0; }"
                    "QToolButton:hover { background:#7a2a30; color:#ffffff; }")
                btn.setToolTip("从 3D 场景移除此图层")
            else:
                btn.setStyleSheet(
                    "QToolButton { background:#1e3a68; border:1px solid #6ee2ff;"
                    " color:#6ee2ff; border-radius:6px; padding:0; }"
                    "QToolButton:hover { background:#2d5a9c; color:#e5f4ff; }")
                btn.setToolTip("添加到 3D 场景作为图层")
            btn.clicked.connect(lambda _=False, r=row: self._toggle_row(r))
            return btn

        def _toggle_row(self, row):
            topic_it = self._table.item(row, 0)
            if not topic_it: return
            topic = topic_it.text()
            tag = self._table.cellWidget(row, 1)
            type_name = tag.text() if tag else ""

            existing = self._layer_by_topic.get(topic)
            if existing is not None:
                self.scene.remove_layer(existing)
                del self._layer_by_topic[topic]
            else:
                layer = self.scene.add_layer(topic, type_name)
                if layer is None:
                    QtWidgets.QMessageBox.warning(
                        self, "无法添加",
                        f"类型 {type_name} 当前不支持 3D 图层。")
                    return
                self._layer_by_topic[topic] = layer
            self._table.setCellWidget(
                row, 2, self._make_toggle_button(
                    row, topic in self._layer_by_topic))

        def _clear_all(self):
            self.scene.remove_all()
            self._layer_by_topic.clear()
            for r in range(self._table.rowCount()):
                self._table.setCellWidget(r, 2, self._make_toggle_button(r, False))

        def closeEvent(self, ev):
            try:
                self._clear_all()
            except Exception:
                pass
            super().closeEvent(ev)

    return _VizDashboard


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def _run_dashboard(args) -> int:
    try:
        from PyQt5 import QtCore, QtWidgets
    except ImportError as ex:
        print(f"error: PyQt5 required: {ex}", file=sys.stderr)
        return 2
    from .rqt import _STYLESHEET, _HAS_GL

    if not _HAS_GL:
        print("error: talos viz dashboard 需要 pyqtgraph + PyOpenGL。"
              "请执行 `pip install --user pyqtgraph PyOpenGL`。",
              file=sys.stderr)
        return 2

    for attr in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        if hasattr(QtCore.Qt, attr):
            QtWidgets.QApplication.setAttribute(getattr(QtCore.Qt, attr), True)
    try:
        QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
            QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QtWidgets.QApplication.instance() \
        or QtWidgets.QApplication(sys.argv[:1])
    base_pt = float(os.environ.get("TALOS_RQT_FONT_PT", "12"))
    font = app.font(); font.setPointSizeF(base_pt); app.setFont(font)
    app.setStyleSheet(_STYLESHEET)

    DashboardCls = _VizDashboardClass()
    win = DashboardCls(refresh_sec=args.refresh,
                        type_filter=_3D_TYPES,
                        window_title=(args.title or "TalosOS viz — 3D 场景"))
    # 让 Qt 主循环定期唤醒以响应 SIGINT
    keepalive = QtCore.QTimer()
    keepalive.timeout.connect(lambda: None)
    keepalive.start(200)

    win.show()
    return int(app.exec_())


def _run_qt_viz(args) -> int:
    try:
        from PyQt5 import QtCore, QtGui, QtWidgets
    except ImportError as ex:
        print(f"error: PyQt5 required: {ex}", file=sys.stderr)
        return 2
    from .rqt import create_panel, _STYLESHEET, _HAS_GL, RENDER_TICK_MS

    for attr in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        if hasattr(QtCore.Qt, attr):
            QtWidgets.QApplication.setAttribute(getattr(QtCore.Qt, attr), True)
    try:
        QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
            QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass

    app = QtWidgets.QApplication.instance() \
        or QtWidgets.QApplication(sys.argv[:1])
    base_pt = float(os.environ.get("TALOS_RQT_FONT_PT", "12"))
    font = app.font(); font.setPointSizeF(base_pt); app.setFont(font)
    app.setStyleSheet(_STYLESHEET)

    try:
        panel, _is_image = create_panel(args.topic, args.msg_type)
    except Exception as ex:
        print(f"error: 无法为 {args.msg_type} 创建面板: {ex}", file=sys.stderr)
        return 2

    win = QtWidgets.QMainWindow()
    win.setWindowTitle(args.title
                         or f"talos viz  {args.topic}  [{args.msg_type}]")
    win.resize(1100, 820)

    central = QtWidgets.QWidget()
    v = QtWidgets.QVBoxLayout(central)
    v.setContentsMargins(10, 10, 10, 10); v.setSpacing(6)
    backend_tag = "GPU (OpenGL)" if _HAS_GL else "CPU (matplotlib)"
    header = QtWidgets.QLabel(
        f"<span style='color:#6ee2ff; font-weight:700;'>{args.topic}</span>"
        f"&nbsp;&nbsp;<span style='color:#9ee7ff;'>[{args.msg_type}]</span>"
        f"&nbsp;&nbsp;<span style='color:#7c9ac9; font-size:10pt;'>"
        f"renderer: {backend_tag}</span>")
    header.setTextFormat(QtCore.Qt.RichText)
    header.setStyleSheet("font-size: 13pt; padding: 2px 4px;")
    v.addWidget(header)
    v.addWidget(panel.widget, stretch=1)
    win.setCentralWidget(central)

    tick_timer = QtCore.QTimer()
    tick_timer.timeout.connect(panel.tick)
    tick_timer.start(RENDER_TICK_MS)   # ~30 FPS

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    keepalive = QtCore.QTimer()
    keepalive.timeout.connect(lambda: None)
    keepalive.start(200)

    def _cleanup():
        try:
            tick_timer.stop(); keepalive.stop()
            panel.close_sampler()
        except Exception:
            pass
    app.aboutToQuit.connect(_cleanup)

    win.show()
    return int(app.exec_())


def _run_tf_text(args) -> int:
    from ..echo_stream import iter_samples
    from ..messages import decode

    edges: dict = {}; stamps: dict = {}

    def render():
        roots = set(edges.values()) - set(edges.keys())
        print("\n--- tf tree ---")
        for root in sorted(roots):
            _print_tf_tree(root, edges, stamps, 0)
        print()

    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    last_render = 0.0
    for sample in iter_samples(args.topic):
        try:
            msg = decode(args.msg_type, sample.payload)
        except Exception as ex:
            print(f"decode error: {ex}", file=sys.stderr)
            continue
        if args.msg_type == "TransformStamped":
            items = [msg]
        elif args.msg_type == "TFMessage":
            items = msg.transforms
        else:
            items = []
        for t in items:
            edges[t.child_frame_id] = t.header.frame_id
            try:
                stamps[t.child_frame_id] = (
                    t.header.stamp.seconds() if hasattr(t.header.stamp, "seconds")
                    else t.header.stamp.sec + t.header.stamp.nanosec * 1e-9)
            except Exception:
                stamps[t.child_frame_id] = 0.0
        now = time.time()
        if now - last_render > 1.0:
            render(); last_render = now
    return 0


def _print_tf_tree(node, edges, stamps, depth):
    tag = f"  (t={stamps.get(node, 0):.3f})" if node in stamps else ""
    print("  " * depth + node + tag)
    for child, parent in edges.items():
        if parent == node:
            _print_tf_tree(child, edges, stamps, depth + 1)
